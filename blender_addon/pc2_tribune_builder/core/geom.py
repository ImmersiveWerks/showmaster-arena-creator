"""Procedural tribune generator (pure Python, no bpy).

All coordinates are Blender world coordinates (x, y, z up, metres).

Layout model
------------
The tribune is described by its FRONT LINE, a polyline in the XY plane. Walking along the front line
from its start to its end, the rows lie on the LEFT side ("back" direction), the show area on the
RIGHT side. A straight tribune runs along +X, its rows go towards +Y and the audience looks towards -Y.

Every point of the tribune is addressed with two numbers:
  s = distance along the front line (0 .. L), negative / beyond L = side paths
  t = depth behind the front line (negative = in front: walkway and show area)
The mapping (s, t) -> world uses mitred offsets, so angled corners and arcs work for all rows.
Navmesh, structure, seats and outline are all built on the same (s, t) grid, therefore the navmesh
always shares complete edges between neighbouring walkable areas (no tiny portals).
"""
import math

# ------------------------------------------------------------------ small vector helpers (2D)


def _sub(a, b): return (a[0] - b[0], a[1] - b[1])
def _add(a, b): return (a[0] + b[0], a[1] + b[1])
def _mul(a, s): return (a[0] * s, a[1] * s)
def _dot(a, b): return a[0] * b[0] + a[1] * b[1]
def _cross(a, b): return a[0] * b[1] - a[1] * b[0]
def _len(a): return math.hypot(a[0], a[1])


def _norm(a):
    l = _len(a)
    return (a[0] / l, a[1] / l) if l > 1e-12 else (0.0, 0.0)


def _left(d): return (-d[1], d[0])


DEFAULTS = dict(
    # footprint: list of segments. kind "straight": length; kind "arc": radius + angle.
    # "turn" (degrees) is applied at the start of the segment. Positive angles bend the tribune
    # AROUND the show area (the rows get longer at the back), negative angles bend it the other way.
    segments=[{"kind": "straight", "length": 16.0, "turn": 0.0}],
    rows=5,
    row_depth=1.25,
    first_row_depth=1.6,    # the first row is deeper (more room in front of the seats)
    row_rise=0.35,
    first_row_height=0.35,
    # seat model (filled from the seat mesh bounds)
    seat_width=0.51,
    seat_depth=0.55,
    seat_gap=0.06,          # free space between two seats
    seat_back_gap=0.05,     # seat back to the back edge of its row (negative: the seat hangs over the next step,
                            # like wall-mounted stadium seats)
    seat_bottom=0.5,        # lowest point of the seat above its floor (for the overhang check)
    seat_height=-0.04,      # seats this much higher (+) or lower (-) than the seat model
    clearance=0.2,          # seat front to the walking lane
    sit=(0.0, -0.076, 0.546),   # sit point in seat-local coordinates (seat origin = floor, centre; looks to -Y)
    # aisles / stairs
    aisle_width=1.2,
    aisle_left=True,
    aisle_right=True,
    aisle_center_count=0,
    aisle_corners=True,
    aisle_custom=[],        # extra aisle centres, metres from the start of the front line
    corner_threshold=20.0,  # turns larger than this (degrees) count as corners
    max_step=0.2,           # visual stair step height
    # areas around the tribune (all part of the ride)
    stage_depth=0.0,
    front_walk=1.5,
    side_walk=1.5,
    back_walk=1.2,
    # entrance / exit edges of the outline
    entrance_left=True,
    entrance_right=True,
    entrance_front=False,
    entrance_back=False,
    entrance_length=6.0,    # side entrances start at the front corner and are this long (0 = whole side)
    booth="back",           # back / left / right
    # railings
    rail_back=True,
    rail_sides=True,
    rail_front=False,       # railing along the front edge of the first row (open at the stairs)
    front_path=True,        # walkway along the front that connects the bottoms of the stairs
    access_left="NONE",     # side access to the first row: NONE, RAMP or STAIRS (left end)
    access_right="NONE",    # same at the right end
    access_width=1.2,       # width of the side access
    access_slope=0.12,      # ramp gradient (0.12 = 12 %)
    stair_bottom=None,      # per stair (sorted along the tribune): True = down to the ground, False = from row 1
    rail_height=1.0,
    rail_post_spacing=1.5,  # vertical posts of the railings every ... m
    rail_hand=0.06,         # handrail thickness
    rail_post_size=0.05,    # post thickness
    rail_mid=True,          # middle rail
    rail_mid_size=0.03,
    rail_mid_height=0.5,    # height of the middle rail above the step
    rail_infill=False,      # thin vertical bars between the posts (single double-sided faces)
    rail_infill_spacing=0.12,
    rail_infill_width=0.02,
    rail_infill_bottom=0.1,  # infill bars from ... (height above the step)
    rail_infill_top=1.0,     # ... to (limited to just below the handrail)
    arc_step=7.5,           # degrees per arc piece
)


class GenError(Exception):
    pass


def seat_local_z(V, seat_height, bottom):
    """Seat template vertices for a seat placed with seat_height (the seat origin is lifted by seat_height).
    Only the seat itself moves: the feet stay on the floor and the legs get shorter / longer, so the
    floor anchors stay visible. V: numpy array (n, 3); bottom: lowest point of the seat shell."""
    import numpy as np
    zoff = float(seat_height or 0.0)
    if abs(zoff) < 1e-9:
        return V
    zb = max(0.05, float(bottom or 0.0))
    V = np.array(V, dtype=float, copy=True)
    z = V[:, 2]
    V[:, 2] = z + zoff * (np.minimum(1.0, np.maximum(z, 0.0) / zb) - 1.0)
    return V


def seat_template_for(tmpl, params):
    """tmpl with the parts adjusted to the seat height of the generator params (see seat_local_z)"""
    zoff = float((params or {}).get("seat_height", 0.0) or 0.0)
    if abs(zoff) < 1e-9:
        return tmpl
    parts = [(n, seat_local_z(V, zoff, tmpl.get("bottom", 0.0)), f, sm) for n, V, f, sm in tmpl["parts"]]
    return dict(tmpl, parts=parts)


# ------------------------------------------------------------------ front line


def front_line(segments, arc_step=7.5):
    """Returns the polyline points (unit: m) and the turn angle (deg) at each interior vertex.
    Positive turns bend the tribune around the show area = clockwise (to the right)."""
    pts = [(0.0, 0.0)]
    heading = 0.0       # radians, 0 = +X
    first = True
    for seg in segments:
        turn = float(seg.get("turn", 0.0))
        if not first:
            heading -= math.radians(turn)
        first = False
        if seg.get("kind", "straight") == "arc":
            r = max(0.5, float(seg.get("radius", 10.0)))
            ang = float(seg.get("angle", 45.0))
            n = max(1, int(math.ceil(abs(ang) / arc_step)))
            da = math.radians(ang) / n
            chord = 2 * r * math.sin(abs(da) / 2)
            heading -= da / 2
            for _ in range(n):
                p = pts[-1]
                pts.append((p[0] + chord * math.cos(heading), p[1] + chord * math.sin(heading)))
                heading -= da
            heading += da / 2
        else:
            l = float(seg.get("length", 10.0))
            if l <= 0.01:
                continue
            p = pts[-1]
            pts.append((p[0] + l * math.cos(heading), p[1] + l * math.sin(heading)))
    if len(pts) < 2:
        raise GenError("The front line needs at least one segment with a length.")
    # merge points that are (almost) identical
    out = [pts[0]]
    for p in pts[1:]:
        if _len(_sub(p, out[-1])) > 1e-4:
            out.append(p)
    return out


def room_front_line(room, depth):
    """Front line of a tribune whose BACK stands on a chain of walls.
    room: {"chain": [(x, y), ...] wall points with the room on the RIGHT side of the walking direction,
           "start_in": (x, y) unit vector from chain[0] into the room along the neighbour wall (or None),
           "end_in": same for chain[-1]}
    Returns the front-line points and the offset vectors of both ends (they run along the neighbour walls)."""
    B = [tuple(q) for q in room["chain"]]
    if len(B) < 2:
        raise GenError("Mark at least one wall edge of the room as tribune wall (Mark Sharp).")
    n = len(B)
    d = [_norm(_sub(B[i + 1], B[i])) for i in range(n - 1)]
    nrm = [_left(x) for x in d]          # towards the wall side (outside of the room)
    M = []
    for i in range(n):
        if i == 0 or i == n - 1:
            nn = nrm[0] if i == 0 else nrm[-1]
            e = room.get("start_in" if i == 0 else "end_in")
            m = nn
            if e is not None:
                v = (-e[0], -e[1])                 # from the room towards the wall corner
                c = _dot(v, nn)
                if c > 0.25:                       # neighbour wall not too flat: follow its angle
                    m = _mul(v, 1.0 / c)
            M.append(m)
        else:
            na, nb = nrm[i - 1], nrm[i]
            c = 1.0 + _dot(na, nb)
            if c < 0.15:
                raise GenError("Two tribune walls meet at too sharp an angle.")
            M.append(_mul(_add(na, nb), 1.0 / c))
    front = [(B[i][0] - M[i][0] * depth, B[i][1] - M[i][1] * depth) for i in range(n)]
    for i in range(n - 1):
        if _dot(_sub(front[i + 1], front[i]), d[i]) <= 0.05:
            raise GenError("The tribune is too deep for this room: a wall is too short for so many rows.")
    return front, {0: M[0], n - 1: M[-1]}


def _point_in_poly(x, y, poly, tol=0.0):
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi:
            inside = not inside
        j = i
    if inside or tol <= 0:
        return inside
    for i in range(n):          # on (or very near) an edge counts as inside
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        dx, dy = bx - ax, by - ay
        l2 = dx * dx + dy * dy
        u = 0.0 if l2 < 1e-12 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / l2))
        if math.hypot(x - ax - dx * u, y - ay - dy * u) <= tol:
            return True
    return False


class Frame:
    """Mitred (s, t) -> world mapping along the front line."""

    def __init__(self, pts, overrides=None):
        self.P = pts
        n = len(pts)
        self.d = [_norm(_sub(pts[i + 1], pts[i])) for i in range(n - 1)]
        self.S = [0.0]
        for i in range(n - 1):
            self.S.append(self.S[-1] + _len(_sub(pts[i + 1], pts[i])))
        self.L = self.S[-1]
        self.M = []
        self.turn = [0.0] * n     # degrees, positive = bends around the show area (clockwise)
        for i in range(n):
            if i == 0:
                self.M.append(_left(self.d[0]))
            elif i == n - 1:
                self.M.append(_left(self.d[-1]))
            else:
                na, nb = _left(self.d[i - 1]), _left(self.d[i])
                c = 1.0 + _dot(na, nb)
                if c < 0.15:
                    raise GenError("A corner is too sharp (more than about 135 degrees).")
                self.M.append(_mul(_add(na, nb), 1.0 / c))
                self.turn[i] = -math.degrees(math.atan2(_cross(self.d[i - 1], self.d[i]), _dot(self.d[i - 1], self.d[i])))
        # in the show area (in front of t_switch) the plain geometric offsets are used: the stair overrides
        # only matter for the tribune itself, and would make the show area fold at short pieces
        self.Mf = list(self.M)
        self.Mf[0] = (overrides or {}).get(0, self.M[0])
        self.Mf[-1] = (overrides or {}).get(n - 1, self.M[-1])
        self.t_switch = -1e9
        for i, m in (overrides or {}).items():
            self.M[i] = m

    def offset_at(self, s):
        """offset direction at s (depth 1), scaled so that rows keep their depth"""
        k = self.seg_of(s)
        if abs(s - self.S[k]) < 1e-6:
            return self.M[k]
        if abs(s - self.S[k + 1]) < 1e-6:
            return self.M[k + 1]
        l = self.S[k + 1] - self.S[k]
        u = (s - self.S[k]) / l if l > 1e-12 else 0.0
        m = _add(self.M[k], _mul(_sub(self.M[k + 1], self.M[k]), u))
        dn = _dot(m, _left(self.d[k]))
        return _mul(m, 1.0 / dn) if dn > 1e-6 else m

    def seg_of(self, s):
        S = self.S
        if s <= 0:
            return 0
        if s >= self.L:
            return len(S) - 2
        lo, hi = 0, len(S) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if S[mid] <= s:
                lo = mid
            else:
                hi = mid
        return lo

    def at(self, s, t, k=None):
        """World XY of (s, t). k forces the segment (for points exactly on a vertex)."""
        if s < 0:
            return _add(_add(self.P[0], _mul(self.d[0], s)), _mul(self.M[0], t))
        if s > self.L:
            return _add(_add(self.P[-1], _mul(self.d[-1], s - self.L)), _mul(self.M[-1], t))
        if k is None:
            k = self.seg_of(s)
        l = self.S[k + 1] - self.S[k]
        u = (s - self.S[k]) / l if l > 1e-12 else 0.0
        base = _add(self.P[k], _mul(_sub(self.P[k + 1], self.P[k]), u))
        m = _add(self.M[k], _mul(_sub(self.M[k + 1], self.M[k]), u))
        if t < self.t_switch:
            mf = _add(self.Mf[k], _mul(_sub(self.Mf[k + 1], self.Mf[k]), u))
            return _add(_add(base, _mul(m, self.t_switch)), _mul(mf, t - self.t_switch))
        return _add(base, _mul(m, t))

    def tangent(self, s, t):
        e = 1e-3
        k = self.seg_of(s)
        lo = max(self.S[k], s - e) if 0 <= s <= self.L else s - e
        hi = min(self.S[k + 1], s + e) if 0 <= s <= self.L else s + e
        if hi - lo < 1e-9:
            return self.d[k]
        return _norm(_sub(self.at(hi, t, k), self.at(lo, t, k)))

    def check(self, t_max):
        """Inner rows must not fold over at concave corners."""
        for k in range(len(self.P) - 1):
            for t in (t_max, 0.0):
                a, b = self.at(self.S[k], t, k), self.at(self.S[k + 1], t, k)
                if _dot(_sub(b, a), self.d[k]) <= 0.05:
                    raise GenError("A corner bends towards the rows and the rows are too deep for it. "
                                   "Use a smaller angle, a longer segment or fewer rows.")


# ------------------------------------------------------------------ main generator


def _triangulate(P):
    """ear clipping of a simple polygon (any orientation); keeps every point. Returns counter-clockwise triangles."""
    n = len(P)
    if n < 3:
        return []
    area = sum(P[i][0] * P[(i + 1) % n][1] - P[(i + 1) % n][0] * P[i][1] for i in range(n))
    idx = list(range(n)) if area > 0 else list(range(n))[::-1]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def inside(pt, a, b, c):
        return cross(a, b, pt) >= -1e-12 and cross(b, c, pt) >= -1e-12 and cross(c, a, pt) >= -1e-12
    out = []
    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        m = len(idx)
        best = None
        for j in range(m):
            i0, i1, i2 = idx[j - 1], idx[j], idx[(j + 1) % m]
            a, b, c = P[i0], P[i1], P[i2]
            ar = cross(a, b, c)
            if ar <= 1e-10:
                continue
            ok = True
            for k in idx:
                if k in (i0, i1, i2):
                    continue
                q = P[k]
                if inside(q, a, b, c) and not (q == a or q == b or q == c):
                    ok = False
                    break
            if ok:
                # prefer the fattest ear (fewer slivers)
                la = max((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2, (c[0] - b[0]) ** 2 + (c[1] - b[1]) ** 2,
                         (a[0] - c[0]) ** 2 + (a[1] - c[1]) ** 2)
                score = ar / max(la, 1e-12)
                if best is None or score > best[0]:
                    best = (score, j)
        if best is None:
            break
        j = best[1]
        out.append((idx[j - 1], idx[j], idx[(j + 1) % len(idx)]))
        idx.pop(j)
    if len(idx) == 3:
        a, b, c = P[idx[0]], P[idx[1]], P[idx[2]]
        if cross(a, b, c) > 1e-10:
            out.append(tuple(idx))
    return out


def _intervals_merge(iv):
    iv = sorted(iv)
    out = []
    for a, b in iv:
        if out and a <= out[-1][1] + 1e-6:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def generate(params=None):
    p = dict(DEFAULTS)
    if params:
        p.update({k: v for k, v in params.items() if v is not None})
    warn = []

    N = int(p["rows"])
    D = float(p["row_depth"])
    R = float(p["row_rise"])
    h1 = float(p["first_row_height"])
    if N < 1:
        raise GenError("At least one row is needed.")
    sw, sd = float(p["seat_width"]), float(p["seat_depth"])
    pitch = sw + float(p["seat_gap"])
    S = D - float(p["seat_back_gap"]) - sd - float(p["clearance"])     # walking lane depth
    if S < 0.4 - 1e-6:
        raise GenError("The rows are too shallow for the seats: the walking lane in front of the seats is %.2f m, "
                       "it needs at least 0.40 m. Increase the row depth to %.2f m or more."
                       % (S, D + (0.4 - S)))
    if float(p["seat_back_gap"]) < -0.01 and N > 1 and float(p["seat_bottom"]) + float(p.get("seat_height", 0.0)) < R + 0.05:
        warn.append("The seats hang over the next step but are too low for it (seat bottom %.2f m, rise %.2f m). "
                    "Use a seat back gap of 0 or more." % (float(p["seat_bottom"]), R))
    if S < 0.55:
        warn.append("Walking lane only %.2f m wide: guests walk in single file." % S)
    D1 = float(p.get("first_row_depth") or D)
    S1 = S + (D1 - D)                       # walking lane of the first row
    if S1 < 0.4 - 1e-6:
        raise GenError("The first row is too shallow: increase its depth to %.2f m or more." % (D1 + (0.4 - S1)))
    T0 = [0.0] + [D1 + (i - 1) * D for i in range(1, N)]          # front edge of every row
    DR = [D1] + [D] * (N - 1)                                       # depth of every row
    SR = [S1] + [S] * (N - 1)                                       # walking lane of every row

    def row_of(t):
        if t < D1 - 1e-9:
            return 0
        return min(N - 1, 1 + int((t - D1 + 1e-9) // D))
    H = [h1 + i * R for i in range(N)]
    zone = D - S
    if N > 1 and R / zone > 0.85:
        warn.append("The aisle stairs are steep (%.0f %%). Guests may refuse them; use a smaller rise or deeper rows."
                    % (100 * R / zone))
    P_front = 0.0
    if h1 > 0.01:
        # the stairs in front of the first row are as long as the stairs between two rows, so the stair
        # pattern (and the railing posts) repeat every row depth
        P_front = zone if zone >= h1 * 0.9 else max(0.6, h1 * 1.6)

    # the last row is deeper: seats that hang over the back edge must stay in front of the back railing
    E = max(0.0, -float(p["seat_back_gap"])) + 0.15
    T_back = T0[-1] + DR[-1] + E
    room = p.get("room")
    staff = max(0.0, float(p.get("staff_path", 1.2)))
    if room:
        p["back_walk"] = max(float(p["back_walk"]), staff)     # staff path along the back wall
        pts, end_over = room_front_line(room, T_back + max(0.0, float(p["back_walk"])))
        F = Frame(pts, end_over)
    else:
        pts = front_line(p["segments"], float(p["arc_step"]))
        F = Frame(pts)
    L = F.L
    F.check(T_back + max(0.0, float(p["back_walk"])))

    # ---------------------------------------------------- aisles (intervals of s)
    A = float(p["aisle_width"])
    thr = float(p["corner_threshold"])
    corners = [i for i in range(1, len(pts) - 1) if abs(F.turn[i]) > thr]
    # ends of the tribune; in a room a staff path (measured square to the wall) stays free at both walls
    sA, sB = 0.0, L
    if room and staff > 0:
        for end in (0, 1):
            m = _norm(F.M[0] if end == 0 else F.M[-1])
            dd = F.d[0] if end == 0 else F.d[-1]
            sn = abs(_cross(dd, m))
            w = staff / max(sn, 0.3)
            if end == 0:
                sA = w
            else:
                sB = L - w
        if sB - sA < 2.0:
            raise GenError("The wall is too short for a tribune with %.1f m staff path on both sides." % staff)
    aisles = []
    if A > 0.3:
        if p["aisle_left"]:
            aisles.append((sA, sA + A))
        if p["aisle_right"]:
            aisles.append((sB - A, sB))
        n = int(p["aisle_center_count"])
        for j in range(n):
            c = sA + (sB - sA) * (j + 1) / (n + 1)
            aisles.append((c - A / 2, c + A / 2))
        if p["aisle_corners"]:
            for i in corners:
                # measured along the front line; the stair itself is A wide everywhere (see below)
                half = A / 2 / max(0.3, math.cos(math.radians(abs(F.turn[i])) / 2))
                aisles.append((F.S[i] - half, F.S[i] + half))
        for c in p["aisle_custom"] or []:
            c = float(c)
            aisles.append((c - A / 2, c + A / 2))
    aisles = [(max(sA, a), min(sB, b)) for a, b in aisles if b > sA and a < sB]
    aisles = _intervals_merge([iv for iv in aisles if iv[1] - iv[0] > 0.2])
    if not aisles:
        raise GenError("No stairs: switch on at least one aisle so guests can reach the rows.")

    def in_aisle(s):
        return any(a - 1e-6 <= s <= b + 1e-6 for a, b in aisles)

    # every stair becomes a straight band of constant width:
    #  - front-line points inside a stair are removed (the stair front is one straight line, no kink)
    #  - both stair edges get the offset direction of the stair's middle (parallel edges, no widening)
    keep = [s for s in F.S if not any(a + 1e-4 < s < b - 1e-4 for a, b in aisles)]
    marks = sorted(set([x for iv in aisles for x in iv] + keep + [sA, sB]))
    merged = []
    for s in marks:
        if merged and abs(s - merged[-1]) < 1e-4:
            continue
        merged.append(s)
    pts2 = [F.at(s, 0.0) for s in merged]
    pos = {s: i for i, s in enumerate(merged)}

    def idx(x):
        return min(range(len(merged)), key=lambda i: abs(merged[i] - x))
    over = {}
    old_aisles = list(aisles)
    end0, end1 = F.M[0], F.M[-1]          # end directions (perpendicular, or along the neighbour walls)
    over[0] = end0
    over[len(pts2) - 1] = end1
    if sA > 1e-6:
        over[idx(sA)] = end0           # the staff path keeps its width all the way back
    if sB < L - 1e-6:
        over[idx(sB)] = end1
    for a, b in old_aisles:
        ia, ib = idx(a), idx(b)
        # both stair edges get the same offset vector; it keeps the row depth of the seat blocks on BOTH
        # sides (m . n = 1), so the rows stay parallel and the stair edges are parallel too
        nl = _left(_norm(_sub(pts2[ia], pts2[ia - 1]))) if ia > 0 else None
        nr = _left(_norm(_sub(pts2[ib + 1], pts2[ib]))) if ib < len(pts2) - 1 else None
        if nl is None and nr is None:
            m = end0
        elif nl is None:
            m = end0
        elif nr is None:
            m = end1
        else:
            c = 1.0 + _dot(nl, nr)
            m = _mul(_add(nl, nr), 1.0 / max(c, 0.15))
        if abs(a - sA) < 1e-6 and sA > 1e-6:
            m = end0                   # stairs beside a staff path run along the wall
        if abs(b - sB) < 1e-6 and sB < L - 1e-6:
            m = end1
        over[ia] = m
        over[ib] = m
    F = Frame(pts2, over)
    L = F.L
    aisles = [(F.S[idx(a)], F.S[idx(b)]) for a, b in old_aisles]
    sA, sB = F.S[idx(sA)], F.S[idx(sB)]
    F.check(T_back + max(0.0, float(p["back_walk"])))
    corners = [i for i in range(1, len(F.P) - 1) if abs(F.turn[i]) > thr]

    # ---------------------------------------------------- stairs: down to the ground or from the first row
    front_path = bool(p.get("front_path", True))
    want = list(p.get("stair_bottom") or [])
    stairs = []
    for i_, (a_, b_) in enumerate(sorted(aisles)):
        left_end, right_end = a_ <= sA + 1e-6, b_ >= sB - 1e-6
        pos = "LEFT" if left_end else ("RIGHT" if right_end else "MIDDLE")
        forced = (not front_path) and not (left_end or right_end)
        bottom = (want[i_] if i_ < len(want) else True) and not forced
        stairs.append({"a": a_, "b": b_, "pos": pos, "bottom": bool(bottom), "forced": forced,
                       "wanted": bool(want[i_] if i_ < len(want) else True)})
    if P_front <= 0:
        for st_ in stairs:
            st_["bottom"] = True        # the first row is on the ground: nothing to choose

    def has_stub(sm):
        for st_ in stairs:
            if st_["a"] - 1e-6 <= sm <= st_["b"] + 1e-6:
                return st_["bottom"]
        return True
    if any(st_["forced"] and st_["wanted"] for st_ in stairs) and P_front > 0:
        warn.append("Without the front walkway the middle stairs start at the first row.")

    # ---------------------------------------------------- s-columns
    Ws, Wf, Wb, St = (max(0.0, float(p[k])) for k in ("side_walk", "front_walk", "back_walk", "stage_depth"))
    if room:
        Ws = 0.0        # the ends stand against the neighbour walls
    # side access (ramp or stairs) from the ground up to the first row, continuing the front line outwards
    GAP_R = 0.4                 # free strip around the access, like around the stairs
    acc = {}
    w_acc = min(max(0.6, float(p.get("access_width", 1.2))), S1 - 0.05)
    for side_, key_ in (("L", "access_left"), ("R", "access_right")):
        mode_ = str(p.get(key_) or "NONE").upper()
        if mode_ == "NONE" or h1 < 0.05:
            continue
        if room:
            warn.append("A side access is not possible in a room (the staff path is there).")
            continue
        if mode_ == "STAIRS":
            n_ = max(1, int(math.floor(h1 / p["max_step"] + 0.5 + 1e-9)))
            run = n_ * 0.32
        else:
            n_ = 0
            run = h1 / max(0.03, float(p.get("access_slope", 0.12)))
        Lr = run + GAP_R            # the last GAP_R is level (the strip where it meets the first row)
        # the staff walkway beside the tribune moves out to the foot of the access (no walkway in the corner
        # between access and tribune); without a side walkway there is a 1 m landing at the foot
        RUNOUT = 1.5                # level ground in front of the foot before the staff walkway starts
        sg = -1.0 if side_ == "L" else 1.0
        s_top = sA if side_ == "L" else sB
        s_bot = s_top + sg * Lr
        s_pad = s_bot + sg * RUNOUT                     # end of the run-out, start of the staff walkway
        s_out = s_pad + sg * Ws if Ws > 0 else s_pad
        acc[side_] = {"mode": mode_, "n": n_, "run": run, "Lr": Lr, "top": s_top, "bot": s_bot, "pad": s_pad,
                      "out": s_out}

    def acc_h(side_, sv_, nav=True):
        """height of the access at s (level on the last GAP_R before the first row)"""
        a_ = acc[side_]
        d_ = abs(sv_ - a_["bot"])
        if d_ >= a_["run"]:
            return h1
        if a_["mode"] == "STAIRS" and not nav:
            return h1 * min(a_["n"], int(d_ / (a_["run"] / a_["n"]) + 1e-9) + 1) / a_["n"] if d_ > 1e-9 else h1 / a_["n"]
        return h1 * d_ / a_["run"]

    def acc_of(m):
        for side_, a_ in acc.items():
            lo_, hi_ = sorted((a_["bot"], a_["top"]))
            if lo_ - 1e-6 <= m <= hi_ + 1e-6:
                return side_, "ramp"
            lo2, hi2 = sorted((a_["pad"], a_["bot"]))
            if lo2 - 1e-6 <= m <= hi2 + 1e-6:
                return side_, "pad"
            lo3, hi3 = sorted((a_["out"], a_["pad"]))
            if lo3 - 1e-6 <= m <= hi3 + 1e-6:
                return side_, "walk"
        return None, None

    sb = set([0.0, L] + list(F.S))
    for a, b in aisles:
        sb.update((a, b))
    if Ws > 0:
        if "L" not in acc:
            sb.add(-Ws)
        if "R" not in acc:
            sb.add(L + Ws)
    for a_ in acc.values():
        sb.update((a_["bot"], a_["pad"], a_["out"]))
    sb = sorted(sb)
    # merge breaks closer than 2 cm
    tmp = [sb[0]]
    for s in sb[1:]:
        if s - tmp[-1] > 0.02:
            tmp.append(s)
        else:
            tmp[-1] = s if s in F.S else tmp[-1]
    sb = tmp
    cols = []
    for a, b in zip(sb, sb[1:]):
        m = (a + b) / 2
        if acc_of(m)[1] == "ramp" and (b <= sA + 1e-6 or a >= sB - 1e-6):
            kind = "ramp"
        elif acc_of(m)[1] == "pad":
            kind = "pad"                            # level run-out in front of the foot of the access
        elif acc_of(m)[1] == "walk":
            kind = "side"                           # the staff walkway, moved out beyond the run-out
        elif b <= sA + 1e-6:
            kind = "side"
        elif a >= sB - 1e-6:
            kind = "side"
        elif in_aisle(m):
            kind = "aisle"
        else:
            kind = "seat"
        k = F.seg_of(m) if 0 <= m <= L else None
        cols.append((a, b, kind, k))

    # navmesh columns: where two column kinds meet (seats | stair | ground beside the tribune) a thin strip
    # GAP wide is put between them. It is only walkable where both sides have the same height, so the
    # game never links walkways of different heights that only touch seen from above (guests would walk
    # through the side of a stair or through a step)
    GAP = 0.4           # the game links walkways that are closer than about this
    # the bays between the front stairs stay free: guests walk along the front walkway and up the stair
    GAP_F = P_front if P_front > 0.1 else 0.0
    GAP_B = min(GAP, 0.4 * Wb) if Wb > 0.25 else 0.0
    rank = {"aisle": 0, "seat": 1, "side": 2, "ramp": 2, "pad": 2}   # strip taken from the higher rank (never the stair)
    # stairs: only a lane in the middle is walkable on the steps, the full width only on the landings.
    # The game walks the shortest line through the navmesh; on a wide stair that line runs diagonally across
    # the steps (it looks like walking onto the stair from the side). A lane keeps guests straight on the stair.
    work = []
    for a, b, kind, k in cols:
        w_ = b - a
        lane = min(max(0.6, 0.5 * w_), w_)
        if kind == "aisle" and w_ - lane > 0.3:
            c0, c1 = (a + b - lane) / 2, (a + b + lane) / 2
            work += [[a, c0, "aisle_side", k, None], [c0, c1, "aisle", k, None], [c1, b, "aisle_side", k, None]]
        else:
            work.append([a, b, kind, k, None])
    rank["aisle_side"] = 0
    fam = lambda kd: "aisle" if kd.startswith("aisle") else ("side" if kd in ("ramp", "pad") else kd)
    gaps = []
    for i in range(len(work) - 1):
        L_, R_ = work[i], work[i + 1]
        if fam(L_[2]) == fam(R_[2]):
            continue
        take = L_ if rank[L_[2]] >= rank[R_[2]] else R_
        w = min(GAP, (take[1] - take[0]) * 0.3)
        if w < 0.02:
            continue
        if take is L_:
            gaps.append([L_[1] - w, L_[1], "gap", L_[3], (L_[2], R_[2])])
            L_[1] -= w
        else:
            gaps.append([R_[0], R_[0] + w, "gap", R_[3], (L_[2], R_[2])])
            R_[0] += w
    ncols = sorted(work + gaps, key=lambda c: c[0])
    # safety distance to the railings: guests walking right along a railing slide through it in the game
    RM = 0.25 if float(p["rail_height"]) > 0 else 0.0
    if RM > 0 and p["rail_sides"]:
        cut = []
        for c in ncols:
            a, b, kind, k, nb = c
            pieces = [(a, b)]
            for x in (sA + RM, sB - RM):
                pieces = [q for pc in pieces for q in ([(pc[0], x), (x, pc[1])] if pc[0] + 1e-6 < x < pc[1] - 1e-6 else [pc])]
            for u, v in pieces:
                mid_ = (u + v) / 2
                if kind not in ("side", "ramp", "pad") and (sA - 1e-6 <= mid_ <= sA + RM or sB - RM <= mid_ <= sB + 1e-6):
                    cut.append([u, v, "edge", k, (kind, "L" if mid_ < (sA + sB) / 2 else "R", nb)])
                else:
                    cut.append([u, v, kind, k, nb])
        ncols = cut
    ncols = [c for c in ncols if c[1] - c[0] > 1e-6]
    nsb = sorted(set([c[0] for c in ncols] + [c[1] for c in ncols]))

    # ---------------------------------------------------- t-breaks and height profiles
    t_front = -(P_front + Wf + St)
    F.t_switch = -P_front - 1e-9

    # ---------------------------------------------------- show area: one polygon in front of the tribune
    # (front edge of the tribune + both ends extended + a straight closing edge). Unlike offsetting the front
    # line it never folds over itself, and for U shapes and arenas it fills the inside.
    t_sw = -P_front

    def _seg_x(p1, p2, p3, p4):
        d1, d2 = _sub(p2, p1), _sub(p4, p3)
        den = _cross(d1, d2)
        if abs(den) < 1e-12:
            return False
        u = _cross(_sub(p3, p1), d2) / den
        v = _cross(_sub(p3, p1), d1) / den
        return 1e-6 < u < 1 - 1e-6 and 1e-6 < v < 1 - 1e-6

    top_line = [F.at(s, t_sw) for s in nsb]

    def front_curve(t, return_ok=False):
        """outer edge of the show area at depth t: the tribune's front edge moved forward by (t_sw - t), following
        its shape; pieces that would turn over (short stair chords on the inside of a bend) drop out."""
        dist = t_sw - t
        P0 = [top_line[0]] + [q for q in top_line[1:]]
        # lines: (point, direction); first and last are the end rays of the show area
        segs = []
        for i in range(len(P0) - 1):
            dv = _sub(P0[i + 1], P0[i])
            if _len(dv) < 1e-6:
                continue
            dn = _norm(dv)
            nn = (dn[1], -dn[0])            # towards the show area (right of the walking direction)
            segs.append((_add(P0[i], _mul(nn, dist)), dn, _len(dv)))
        start = _add(P0[0], _mul(F.M[0], -dist))
        end = _add(P0[-1], _mul(F.M[-1], -dist))

        def meet(l1, l2):
            (p1, d1, _l1), (p2, d2, _l2) = l1, l2
            den = _cross(d1, d2)
            if abs(den) < 1e-9:
                return None
            u = _cross(_sub(p2, p1), d2) / den
            return _add(p1, _mul(d1, u))
        valid = True
        n_all = len(segs)
        for _guard in range(n_all + 2):
            verts = [start]
            for a_, b_ in zip(segs, segs[1:]):
                q = meet(a_, b_)
                verts.append(q if q is not None else b_[0])
            verts.append(end)
            bad = None
            for i, (pt, dn, ln0) in enumerate(segs):
                if _dot(_sub(verts[i + 1], verts[i]), dn) < -1e-6:
                    bad = i
                    break
            if bad is None:
                break
            # only short pieces may drop out (stair chords, arc pieces); a real side or an end piece
            # disappearing means the show area is too deep for this shape
            if segs[bad][2] > 1.6 or bad == 0 or bad == len(segs) - 1 or len(segs) <= 2:
                valid = False
                break
            segs.pop(bad)
        if return_ok:
            return verts, valid
        return verts

    def show_ok(t):
        fc, valid = front_curve(t, True)
        if not valid:
            return False
        ring = top_line + fc[::-1]
        n = len(ring)
        for i in range(n):
            for j in range(i + 2, n):
                if i == 0 and j == n - 1:
                    continue
                if _seg_x(ring[i], ring[(i + 1) % n], ring[j], ring[(j + 1) % n]):
                    return False
        if room and room.get("poly"):
            for q in fc + top_line:
                if not _point_in_poly(q[0], q[1], room["poly"], 0.05):
                    return False
        return True
    if not front_path:
        t_front = t_sw
    t_ok = t_front
    while front_path and t_ok < t_sw - 0.5 and not show_ok(t_ok):
        t_ok = min(t_ok + 0.1, t_sw - 0.5)
    if t_ok != t_front:
        why = "to fit into the room" if room else "so it does not overlap the tribune"
        warn.append("The show area was shortened to %.1f m %s." % (max(0.0, -t_ok - P_front - Wf), why))
        t_front = t_ok
    if front_path and t_front > -0.5:
        t_front = -0.5
        warn.append("No walkway in front of the tribune; a 0.5 m strip was added.")
    tb = {t_front, 0.0, T_back}
    if P_front > 0:
        tb.add(-P_front)
        if GAP_F > 0:
            tb.add(-GAP_F)      # strip in front of the first row: not walkable (row 1 is higher)
    if GAP_B > 0:
        tb.add(T_back + GAP_B)  # strip behind the last row: not walkable (the back walk is lower)
    if acc:
        tb.update((w_acc, w_acc + GAP_R, -GAP_R))
        if RM > 0:
            tb.update((RM, w_acc - RM))
    if RM > 0 and p.get("rail_front"):
        tb.add(RM)
    if RM > 0 and p["rail_back"]:
        tb.add(T_back - RM)     # the stair landing at the top keeps away from the back railing
    for i in range(N):
        tb.update((T0[i], T0[i] + SR[i], T0[i] + DR[i] if i < N - 1 else T_back))
    if Wb > 0:
        tb.add(T_back + Wb)
    el0 = float(p["entrance_length"])
    if 0.1 < el0 and t_front + el0 < max(tb) - 0.1:
        tb.add(t_front + el0)       # navmesh edge exactly where the side entrance ends
    tb = sorted(tb)
    t_end = tb[-1]

    def nav_h(kind, t):
        """walkable height at depth t for a column kind, None = not walkable"""
        if kind == "side":
            return 0.0
        if t < -1e-6:
            if kind == "aisle" and P_front > 0 and t > -P_front - 1e-6:
                return h1 * (t + P_front) / P_front
            return 0.0
        if t > T_back + 1e-6:
            return 0.0
        i = row_of(t + 1e-6)
        t0, Si = T0[i], SR[i]
        if kind == "seat":
            return H[i] if t <= t0 + Si + 1e-6 else None
        # aisle
        if t <= t0 + Si + 1e-6 or i == N - 1:
            return H[i]
        return H[i] + R * (t - t0 - Si) / zone

    def cell_walk(kind, ta, tb_):
        m = (ta + tb_) / 2
        if kind == "seat" and GAP_F > 0 and -GAP_F - 1e-6 <= ta and tb_ <= 1e-6:
            return False
        if kind in ("seat", "aisle") and GAP_B > 0 and T_back - 1e-6 <= ta and tb_ <= T_back + GAP_B + 1e-6:
            return False
        if kind == "seat" and 0 <= m <= T_back:
            i = row_of(m)
            return m <= T0[i] + SR[i]
        if kind != "side" and ta >= T_back - 1e-6 and Wb <= 0:
            return False
        return True

    # ---------------------------------------------------- navmesh
    nverts, nindex, ntris = [], {}, []

    def nv(xy, z):
        key = (round(xy[0], 3), round(xy[1], 3), round(z, 3))
        if key not in nindex:
            nindex[key] = len(nverts)
            nverts.append(key)
        return nindex[key]

    # corner stairs that start at the first row: their front edge follows the sharp corner of the first row
    # (the straight stair band would cut across it)
    front_dents = {}
    for a, b in aisles:
        if a <= sA + 1e-6 or b >= sB - 1e-6 or (has_stub((a + b) / 2) and P_front > 0):
            continue
        ia = min(range(len(F.S)), key=lambda i: abs(F.S[i] - a))
        ib = min(range(len(F.S)), key=lambda i: abs(F.S[i] - b))
        if ia < 1 or ib > len(F.S) - 2 or abs(F.turn[ia]) < 0.5 or abs(F.turn[ib]) < 0.5:
            continue
        dp, dn = F.d[ia - 1], F.d[ib]
        P, Q = F.at(a, 0.0), F.at(b, 0.0)
        den = _cross(dp, dn)
        if abs(den) < 1e-9:
            continue
        X = _add(P, _mul(dp, _cross(_sub(Q, P), dn) / den))
        mid = _mul(_add(P, Q), 0.5)
        mvec = _sub(F.at((a + b) / 2, 1.0), F.at((a + b) / 2, 0.0))
        if _dot(_sub(X, mid), mvec) > 1e-3 and _len(_sub(X, mid)) < 3.0:
            front_dents[(round(a, 4), round(b, 4))] = (dp, dn, X)

    # navmesh: nothing in front of that corner (depth of the corner behind the straight stair edge)
    dent_nav = []
    for (a_k, b_k), (dp_, dn_, X_) in front_dents.items():
        mid_ = F.at((a_k + b_k) / 2, 0.0)
        mv_ = _sub(F.at((a_k + b_k) / 2, 1.0), mid_)
        t_x = _dot(_sub(X_, mid_), mv_) / max(1e-9, _dot(mv_, mv_))
        dent_nav.append((a_k, b_k, t_x + (RM if p.get("rail_front") else 0.05)))

    def fence_at(sm):
        """is there a front railing at s (it is open at stairs that go down to the ground)"""
        if not p.get("rail_front") or sm < sA or sm > sB:
            return False
        for a_, b_ in aisles:
            if a_ - 1e-6 <= sm <= b_ + 1e-6 and (has_stub((a_ + b_) / 2) or P_front <= 0):
                return False
        return True
    tb = sorted(set(tb + [d_[2] for d_ in dent_nav if 0 < d_[2] < T_back]))
    w_lo, w_hi = (RM, w_acc - RM) if RM > 0 else (0.0, w_acc)     # walkable width of the side access

    def cell_z(kind, ta, tc):
        if kind == "edge":
            return None
        if kind == "ramp":
            if ta >= w_lo - 1e-6 and tc <= w_hi + 1e-6:
                return h1, h1          # the access meets the first row at its level
            if (Wb > 0 and ta >= T_back + GAP_B - 1e-6) or tc <= -GAP_R + 1e-6:
                return 0.0, 0.0        # ground in front of / behind the access
            return None
        if kind == "aisle_side":
            # beside the stair lane: walkable only where the stair is flat (landings), never on steps
            z_ = cell_z("aisle", ta, tc)
            if z_ is None or ta < -1e-6 or abs(z_[0] - z_[1]) > 1e-4:
                return None
            return z_
        if not cell_walk(kind, ta, tc):
            return None
        # height per corner: evaluate inside the cell to stay on the right side of steps; where the surface
        # is continuous (a cut through a slope) both neighbouring cells get exactly the same value
        def hz(t, side):
            v1 = nav_h(kind, t + side * 1e-4)
            v2 = nav_h(kind, t - side * 1e-4)
            if v1 is not None and v2 is not None and abs(v1 - v2) < 0.01:
                return (v1 + v2) / 2
            return v1
        za = hz(ta, 1) if kind != "seat" else nav_h(kind, (ta + tc) / 2)
        zc = hz(tc, -1) if kind != "seat" else za
        if za is None or zc is None:
            return None
        return za, zc

    for a, b, kind0, k, nb0_ in ncols:
        for ta, tc in zip(tb, tb[1:]):
            kind, nb = kind0, nb0_
            if tc <= t_sw + 1e-6:
                continue        # the show area is one polygon (below)
            if kind in ("aisle", "aisle_side") and ta < -1e-6 and not has_stub((a + b) / 2):
                continue        # this stair starts at the first row
            if kind == "edge":
                # strip along a side railing: only where a side access arrives
                okind, sk, nb0 = nb
                if not ((sk in acc and ta >= w_lo - 1e-6 and tc <= w_hi + 1e-6) or ta >= T_back - 1e-6):
                    continue    # (behind the tribune the side railing has ended)
                kind, nb = okind, nb0
            if RM > 0 and p.get("rail_front") and ta >= -1e-6 and tc <= RM + 1e-6 and \
                    (fence_at((a + b) / 2) or kind in ("aisle_side", "gap")):
                continue        # keep away from the front railing (and from its end posts at the stairs)
            if RM > 0 and p["rail_back"] and ta >= T_back - RM - 1e-6 and tc <= T_back + 1e-6 and sA <= (a + b) / 2 <= sB:
                continue        # keep away from the back railing
            if any(d_[0] - 1e-6 <= (a + b) / 2 <= d_[1] + 1e-6 and ta >= -1e-6 and tc <= d_[2] + 1e-6
                   for d_ in dent_nav):
                continue        # in front of the sharp corner of a corner stair (no floor there)
            if kind in ("ramp", "pad"):
                side_ = acc_of((a + b) / 2)[0]
                if kind == "ramp" and (ta < w_lo - 1e-6 and tc > -1e-6 or tc > w_hi + 1e-6 and ta < w_acc - 1e-6) \
                        and ta >= -1e-6 and tc <= w_acc + 1e-6:
                    continue    # keep away from the railings of the access
                if ta >= -1e-6 and tc <= w_acc + 1e-6:
                    if kind == "ramp":
                        za_, zb_ = acc_h(side_, a), acc_h(side_, b)
                    else:
                        za_ = zb_ = 0.0
                elif kind == "pad" and tc <= w_acc + 1e-6:
                    za_ = zb_ = 0.0     # the landing at the foot reaches the walkway in front
                elif kind == "ramp" and tc <= -GAP_R + 1e-6:
                    za_ = zb_ = 0.0     # ground in front of the access (free strip next to it)
                elif Wb > 0 and ta >= T_back + GAP_B - 1e-6:
                    za_ = zb_ = 0.0     # the back walkway continues to the moved side walkway
                else:
                    continue
                i00, i10 = nv(F.at(a, ta, k), za_), nv(F.at(b, ta, k), zb_)
                i01, i11 = nv(F.at(a, tc, k), za_), nv(F.at(b, tc, k), zb_)
                ntris.append((i00, i10, i11))
                ntris.append((i00, i11, i01))
                continue
            if kind == "gap":
                z1, z2 = cell_z(nb[0], ta, tc), cell_z(nb[1], ta, tc)
                if z1 is None or z2 is None or abs(z1[0] - z2[0]) > 1e-3 or abs(z1[1] - z2[1]) > 1e-3:
                    continue
                za, zc = z1
            else:
                z_ = cell_z(kind, ta, tc)
                if z_ is None:
                    continue
                za, zc = z_
            # the side columns and the areas in front/behind are ground; rows of seat columns are flat
            p00, p10 = F.at(a, ta, k), F.at(b, ta, k)
            p01, p11 = F.at(a, tc, k), F.at(b, tc, k)
            i00, i10, i01, i11 = nv(p00, za), nv(p10, za), nv(p01, zc), nv(p11, zc)
            # counter-clockwise seen from above
            ntris.append((i00, i10, i11))
            ntris.append((i00, i11, i01))
    # show area polygon, sharing every point of the tribune's front edge (no T-junctions)
    s_lo, s_hi = (min([-Ws] + [a_["out"] for a_ in acc.values()]), max([L + Ws] + [a_["out"] for a_ in acc.values()]))
    PAD = max(1.0, Wf)
    pad_l = (not front_path) and P_front > 0 and bool(stairs) and stairs[0]["pos"] == "LEFT" and stairs[0]["bottom"]
    pad_r = (not front_path) and P_front > 0 and bool(stairs) and stairs[-1]["pos"] == "RIGHT" and stairs[-1]["bottom"]
    if front_path:
        fcurve = front_curve(t_front)
    else:
        # no walkway: the front edge of the tribune, with a landing in front of each end stair that goes down
        # to the ground (it joins the walkway beside the tribune)
        tP = t_sw - PAD
        seq = [(s_lo, tP), (stairs[0]["b"], tP)] if pad_l else []
        lo_s = stairs[0]["b"] if pad_l else s_lo - 1.0
        hi_s = stairs[-1]["a"] if pad_r else s_hi + 1.0
        seq += [(x, t_sw) for x in nsb if lo_s - 1e-6 <= x <= hi_s + 1e-6]
        if pad_r:
            seq += [(stairs[-1]["a"], tP), (s_hi, tP)]
        fcurve = [F.at(x, t) for x, t in seq]

        def pad(u0, u1):
            xs_ = [x for x in nsb if u0 - 1e-6 <= x <= u1 + 1e-6]
            for u, v in zip(xs_, xs_[1:]):
                i0, i1 = nv(F.at(u, t_sw), 0.0), nv(F.at(v, t_sw), 0.0)
                i2, i3 = nv(F.at(v, tP), 0.0), nv(F.at(u, tP), 0.0)
                for tri in ((i0, i1, i2), (i0, i2, i3)):
                    P_ = [nverts[x] for x in tri]
                    ar = (P_[1][0] - P_[0][0]) * (P_[2][1] - P_[0][1]) - (P_[1][1] - P_[0][1]) * (P_[2][0] - P_[0][0])
                    if abs(ar) > 1e-9:
                        ntris.append(tri if ar > 0 else (tri[0], tri[2], tri[1]))
        if pad_l:
            pad(s_lo, stairs[0]["b"])
        if pad_r:
            pad(stairs[-1]["a"], s_hi)
    q0, q1 = fcurve[0], fcurve[-1]
    # bands like the rows: the walkway, then the show area in strips of about 2 m, each band following the
    # tribune; neighbouring bands share their edge points
    depths = set()
    if Wf > 0.05:
        depths.add(t_sw - Wf)
    el_ = float(p["entrance_length"])
    if 0.1 < el_ and t_front + el_ < t_sw - 0.05:
        depths.add(t_front + el_)                      # where a side entrance ends
    span = t_sw - Wf - t_front
    nst = int(math.ceil(span / 2.0 - 1e-6)) if span > 0.05 else 0
    for j in range(1, nst):
        depths.add(t_sw - Wf - span * j / nst)
    depths = sorted([d_ for d_ in depths if t_front + 0.05 < d_ < t_sw - 0.05], reverse=True)
    curves = [top_line] + [front_curve(d_) for d_ in depths] + [fcurve]

    def zipper(A, B):
        """triangles between two neighbouring band edges; falls back to ear clipping if strips would overlap"""
        ia = [nv(q, 0.0) for q in A]
        ib = [nv(q, 0.0) for q in B]

        def cum(ids):
            c = [0.0]
            for u_, v_ in zip(ids, ids[1:]):
                c.append(c[-1] + math.hypot(nverts[v_][0] - nverts[u_][0], nverts[v_][1] - nverts[u_][1]))
            tot = c[-1] or 1.0
            return [x / tot for x in c]

        def area2(tri):
            P_ = [nverts[x] for x in tri]
            return (P_[1][0] - P_[0][0]) * (P_[2][1] - P_[0][1]) - (P_[1][1] - P_[0][1]) * (P_[2][0] - P_[0][0])
        ua, ub = cum(ia), cum(ib)
        out = []
        i = j = 0
        while i < len(ia) - 1 or j < len(ib) - 1:
            if j >= len(ib) - 1 or (i < len(ia) - 1 and ua[i + 1] <= ub[j + 1]):
                tri = (ia[i], ia[i + 1], ib[j])
                i += 1
            else:
                tri = (ia[i], ib[j + 1], ib[j])
                j += 1
            if len(set(tri)) < 3 or abs(area2(tri)) < 1e-9:
                continue
            out.append(tri)
        # the band polygon: A forwards, B backwards
        ring = []
        for x in ia + ib[::-1]:
            if not ring or ring[-1] != x:
                ring.append(x)
        if len(ring) > 1 and ring[0] == ring[-1]:
            ring.pop()
        ring_area = abs(sum(nverts[ring[k]][0] * nverts[ring[(k + 1) % len(ring)]][1]
                            - nverts[ring[(k + 1) % len(ring)]][0] * nverts[ring[k]][1] for k in range(len(ring))))
        tri_area = sum(abs(area2(t_)) for t_ in out)
        same_side = all(area2(t_) > 0 for t_ in out) or all(area2(t_) < 0 for t_ in out)
        if not same_side or tri_area > ring_area * 1.0001 + 1e-6:
            out = [tuple(ring[x] for x in t_) for t_ in _triangulate([nverts[x][:2] for x in ring])]
        for t_ in out:
            ntris.append(t_ if area2(t_) > 0 else (t_[0], t_[2], t_[1]))
    if front_path:
        for A_, B_ in zip(curves, curves[1:]):
            zipper(A_, B_)
    if len(nverts) > 60000:
        raise GenError("The navmesh is too big. Use fewer arc pieces or a smaller tribune.")

    # ---------------------------------------------------- visual profile (steps)
    def step_profile(kind, stub=True):
        """list of (t_start, t_end, height) pieces with height > 0, sorted, covering the tribune"""
        out = []
        if kind == "side":
            return out
        if kind == "aisle" and P_front > 0 and stub:
            n = max(1, int(math.floor(h1 / p["max_step"] + 0.5 + 1e-9)))
            for j in range(n):
                out.append((-P_front + j * P_front / n, -P_front + (j + 1) * P_front / n, h1 * (j + 1) / n))
        for i in range(N):
            t0, Si = T0[i], SR[i]
            if i == N - 1:
                out.append((t0, T_back, H[i]))
                continue
            if kind == "seat":
                out.append((t0, t0 + DR[i], H[i]))
                continue
            out.append((t0, t0 + Si, H[i]))
            n = max(1, int(math.floor(R / p["max_step"] + 0.5 + 1e-9)))
            for j in range(n):
                ts = t0 + Si + j * zone / n
                out.append((ts, t0 + Si + (j + 1) * zone / n, H[i] + R * (j + 1) / n))
        return [o for o in out if o[2] > 1e-4]

    def h_at(profile, t):
        for a, b, h in profile:
            if a - 1e-9 <= t < b - 1e-9:
                return h
        return 0.0

    sv, sindex, sfaces, smat = [], {}, [], []

    def vv(xy, z):
        key = (round(xy[0], 4), round(xy[1], 4), round(z, 4))
        if key not in sindex:
            sindex[key] = len(sv)
            sv.append(key)
        return sindex[key]

    def quad(a, b, c, d, mat):
        f = (a, b, c, d)
        if len(set(f)) < 3:
            return
        sfaces.append(f)
        smat.append(mat)

    profiles = {}
    for a, b, kind, k in cols:
        if kind in ("side", "ramp", "pad"):
            continue
        pr = step_profile(kind, has_stub((a + b) / 2))
        profiles[(a, b)] = (pr, kind)
        mat = 1 if kind == "aisle" else 0
        dent = front_dents.get((round(a, 4), round(b, 4))) if kind == "aisle" else None
        for ta, tc, h in pr:
            m = mat
            p00, p10, p01, p11 = F.at(a, ta, k), F.at(b, ta, k), F.at(a, tc, k), F.at(b, tc, k)
            if dent and abs(ta) < 1e-9:
                X = dent[2]
                sfaces.append((vv(p00, h), vv(X, h), vv(p10, h), vv(p11, h), vv(p01, h)))
                smat.append(m)
                continue
            quad(vv(p00, h), vv(p10, h), vv(p11, h), vv(p01, h), m)
        # risers across the column width (where the height changes along t)
        ts = sorted(set([x for seg in pr for x in seg[:2]]))
        for t in ts:
            hb, hf = h_at(pr, t - 1e-6), h_at(pr, t + 1e-6)
            if abs(hb - hf) < 1e-4:
                continue
            pa, pb = F.at(a, t, k), F.at(b, t, k)
            lo, hi = min(hb, hf), max(hb, hf)
            if dent and abs(t) < 1e-9 and hf > hb:
                X = dent[2]          # front of the first landing: two faces through the sharp corner
                quad(vv(X, lo), vv(X, hi), vv(pa, hi), vv(pa, lo), mat)
                quad(vv(pb, lo), vv(pb, hi), vv(X, hi), vv(X, lo), mat)
                continue
            if hf > hb:     # rising when walking backwards: face looks to the front (-t)
                quad(vv(pb, lo), vv(pb, hi), vv(pa, hi), vv(pa, lo), mat if kind == "aisle" else 0)
            else:
                quad(vv(pa, lo), vv(pa, hi), vv(pb, hi), vv(pb, lo), 0)
    # side faces between neighbouring columns (and the ground at both ends)
    keys = sorted(profiles.keys())
    bounds = sorted(set([k[0] for k in keys] + [k[1] for k in keys]))
    for s in bounds:
        left = next(((pr, kd) for (a, b), (pr, kd) in profiles.items() if abs(b - s) < 1e-6), ([], "side"))
        right = next(((pr, kd) for (a, b), (pr, kd) in profiles.items() if abs(a - s) < 1e-6), ([], "side"))
        ts = sorted(set([x for seg in left[0] + right[0] for x in seg[:2]]))
        k = F.seg_of(min(max(s, 0.0), L) - 1e-6) if s > 0 else 0
        k2 = F.seg_of(min(max(s, 0.0), L) + 1e-6)
        for ta, tc in zip(ts, ts[1:]):
            m = (ta + tc) / 2
            hl, hr = h_at(left[0], m), h_at(right[0], m)
            if abs(hl - hr) < 1e-4:
                continue
            pa, pc = F.at(s, ta, k2), F.at(s, tc, k2)
            lo, hi = min(hl, hr), max(hl, hr)
            mat = 1 if (left[1] == "aisle" and hl > hr) or (right[1] == "aisle" and hr > hl) else 0
            if hl > hr:   # higher on the left (smaller s): face looks to +s
                quad(vv(pa, lo), vv(pc, lo), vv(pc, hi), vv(pa, hi), mat)
            else:
                quad(vv(pc, lo), vv(pa, lo), vv(pa, hi), vv(pc, hi), mat)

    # ---------------------------------------------------- sharp outer corners at corner stairs
    # A stair across a corner is a straight band, so the tribune edge runs straight (bevelled) across it.
    # The stair stays as it is; the missing corner pieces of the back edge (and of the front edge where the
    # stair does not go down to the ground) are added, so the outer corners are sharp again.
    def _meet(P, dp, Q, dn):
        den = _cross(dp, dn)
        if abs(den) < 1e-9:
            return None
        u = _cross(_sub(Q, P), dn) / den
        return _add(P, _mul(dp, u))
    corner_cuts = []
    for a, b in aisles:
        if a <= sA + 1e-6 or b >= sB - 1e-6:
            continue
        ia = min(range(len(F.S)), key=lambda i: abs(F.S[i] - a))
        ib = min(range(len(F.S)), key=lambda i: abs(F.S[i] - b))
        if ia < 1 or ib > len(F.S) - 2 or abs(F.turn[ia]) < 0.5 or abs(F.turn[ib]) < 0.5:
            continue
        corner_cuts.append((a, b, F.d[ia - 1], F.d[ib]))

    def corner_point(a, b, dp, dn, t):
        """sharp corner of the edge at depth t, or None if the straight edge is already the outer one"""
        P, Q = F.at(a, t), F.at(b, t)
        X = _meet(P, dp, Q, dn)
        if X is None:
            return None
        mid = _mul(_add(P, Q), 0.5)
        m = _sub(F.at((a + b) / 2, t + 1.0), F.at((a + b) / 2, t))
        out = _dot(_sub(X, mid), m)
        if t > 0 and out <= 1e-3:
            return None
        if t <= 0 and out >= -1e-3:
            return None
        if _len(_sub(X, mid)) > 3.0:
            return None
        return X

    def wedge(P, X, Q, h):
        """level corner piece P-X-Q at height h with walls down to the ground"""
        i0, i1, i2 = vv(P, h), vv(X, h), vv(Q, h)
        n_ = _cross(_sub(X, P), _sub(Q, P))
        sfaces.append((i0, i1, i2) if n_ > 0 else (i0, i2, i1))
        smat.append(0)
        for U, W in ((P, X), (X, Q)):
            c_ = _mul(_add(_add(P, X), Q), 1.0 / 3.0)
            mid_ = _mul(_add(U, W), 0.5)
            outv = _sub(mid_, c_)
            e_ = _sub(W, U)
            # wall U-W, normal pointing away from the piece
            if _cross(e_, outv) < 0:
                quad(vv(U, 0.0), vv(W, 0.0), vv(W, h), vv(U, h), 0)
            else:
                quad(vv(W, 0.0), vv(U, 0.0), vv(U, h), vv(W, h), 0)
    back_corners = {}
    for a, b, dp, dn in corner_cuts:
        Xb = corner_point(a, b, dp, dn, T_back)
        if Xb is not None:
            wedge(F.at(a, T_back), Xb, F.at(b, T_back), H[-1])
            back_corners[(round(a, 4), round(b, 4))] = (dp, dn)
        if not has_stub((a + b) / 2) or P_front <= 0:
            X0 = corner_point(a, b, dp, dn, 0.0)
            if X0 is not None:
                wedge(F.at(a, 0.0), X0, F.at(b, 0.0), H[0])

    # ---------------------------------------------------- railings
    rail_v, rail_f, rail_m = [], [], []      # rail_m: 0 = metal, 1 = infill (double-sided)
    hand = max(0.01, float(p["rail_hand"]))
    psize = max(0.01, float(p["rail_post_size"]))
    mid_on, msize = bool(p["rail_mid"]), max(0.005, float(p["rail_mid_size"]))
    infill, isp, iw = bool(p["rail_infill"]), max(0.04, float(p["rail_infill_spacing"])), max(0.003, float(p["rail_infill_width"]))
    rh = float(p["rail_height"])

    def box_between(a3, b3, w, hgt):
        """bar from a3 to b3 (3D), square cross section; a bit longer at both ends so joints close"""
        ax, ay, az = a3
        bx, by, bz = b3
        ln = math.sqrt((bx - ax) ** 2 + (by - ay) ** 2 + (bz - az) ** 2)
        if ln > 1e-9:
            e = w / 2 / ln
            ax, ay, az, bx, by, bz = (ax - (bx - ax) * e, ay - (by - ay) * e, az - (bz - az) * e,
                                      bx + (bx - ax) * e, by + (by - ay) * e, bz + (bz - az) * e)
        d = _norm((bx - ax, by - ay))
        if d == (0.0, 0.0):
            d = (1.0, 0.0)
        n = _mul(_left(d), w / 2)
        base = len(rail_v)
        for (x, y, z) in ((ax, ay, az), (bx, by, bz)):
            for sx, sz in ((-1, 0), (1, 0), (1, 1), (-1, 1)):
                rail_v.append((x + n[0] * sx, y + n[1] * sx, z - hgt / 2 + hgt * sz))
        f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
        for q in f:
            rail_f.append(tuple(base + i for i in q))
            rail_m.append(0)

    def post(xy, z0, z1, d=(1.0, 0.0), w=None):
        w = psize if w is None else w
        """square post turned like the railing (d = railing direction)"""
        base = len(rail_v)
        d = _norm(d) if _len(d) > 1e-9 else (1.0, 0.0)
        n = _left(d)
        for z in (z0, z1):
            for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                rail_v.append((xy[0] + (d[0] * a + n[0] * b) * w / 2, xy[1] + (d[1] * a + n[1] * b) * w / 2, z))
        for q in [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]:
            rail_f.append(tuple(base + i for i in q))
            rail_m.append(0)

    def span(a, b):
        """handrail, middle rail and infill between two posts; a, b = (x, y, base height)"""
        box_between((a[0], a[1], a[2] + rh), (b[0], b[1], b[2] + rh), hand, hand)
        if mid_on:
            mh = min(max(0.05, float(p["rail_mid_height"])), rh - hand)
            box_between((a[0], a[1], a[2] + mh), (b[0], b[1], b[2] + mh), msize, msize)
        if infill:
            dx, dy = b[0] - a[0], b[1] - a[1]
            ln = math.hypot(dx, dy)
            if ln < 1e-6:
                return
            d = (dx / ln, dy / ln)
            free = ln - psize
            n = int(math.floor(free / isp))
            if n < 1:
                return
            start = (ln - (n - 1) * isp) / 2
            for j in range(n):
                u = (start + j * isp) / ln
                cx, cy = a[0] + dx * u, a[1] + dy * u
                base = a[2] + (b[2] - a[2]) * u
                lo_ = min(max(0.0, float(p["rail_infill_bottom"])), rh - hand / 2)
                hi_ = min(max(0.0, float(p["rail_infill_top"])), rh - hand / 2)
                if hi_ - lo_ < 0.02:
                    return
                z0, z1 = base + lo_, base + hi_
                k = len(rail_v)
                for sgn in (-1, 1):
                    rail_v.append((cx + d[0] * iw / 2 * sgn, cy + d[1] * iw / 2 * sgn, z0))
                for sgn in (1, -1):
                    rail_v.append((cx + d[0] * iw / 2 * sgn, cy + d[1] * iw / 2 * sgn, z1))
                rail_f.append((k, k + 1, k + 2, k + 3))
                rail_m.append(1)

    top = H[-1]
    if p["rail_back"] and rh > 0:
        tback = T_back - 0.06
        ss = sorted(set([sA, sB] + [s for s in F.S if sA < s < sB]))
        dense = [ss[0]]
        spacing = max(0.3, float(p["rail_post_spacing"]))
        for a, b in zip(ss, ss[1:]):
            n = max(1, int(math.ceil((b - a) / spacing - 1e-6)))
            if (round(a, 4), round(b, 4)) in back_corners:
                n = 1       # goes around the sharp corner (below)
            for j in range(1, n + 1):
                dense.append(a + (b - a) * j / n)
        prev = None
        for s in dense:
            sc = min(max(s, sA + 0.06), sB - 0.06)
            xy = F.at(sc, tback)     # corners meet the side railings exactly
            if prev is not None:
                key_ = next((k_ for k_ in back_corners if abs(k_[0] - prev_s) < 1e-3 and abs(k_[1] - sc) < 1e-3), None)
                if key_ is not None:
                    # around the sharp corner instead of straight across the stair
                    dp, dn = back_corners[key_]
                    Xr = _meet(F.at(key_[0], tback), dp, F.at(key_[1], tback), dn)
                    if Xr is not None:
                        post(Xr, top, top + rh, dp)
                        span((prev[0], prev[1], top), (Xr[0], Xr[1], top))
                        prev = Xr
            post(xy, top, top + rh, F.tangent(sc, tback))
            if prev is not None:
                span((prev[0], prev[1], top), (xy[0], xy[1], top))
            prev = xy
            prev_s = sc
    if p["rail_sides"] and rh > 0:
        spacing = max(0.3, float(p["rail_post_spacing"]))
        for s, inset in ((sA, 0.06), (sB, -0.06)):
            prev = None
            stair = in_aisle(min(max(s + inset, sA), sB))
            stub_here = has_stub(min(max(s + inset, sA), sB))
            t_corner = T_back - 0.06 if p["rail_back"] else T_back - 0.1
            treads = []
            if stair:
                for ta_, tb2, hh in step_profile("aisle", stub_here):
                    if treads and abs(treads[-1][2] - hh) < 1e-6 and abs(treads[-1][1] - ta_) < 1e-6:
                        treads[-1] = (treads[-1][0], tb2, hh)
                    else:
                        treads.append((ta_, tb2, hh))
            if stair and len(treads) >= 2:
                # along the stairs: the stair repeats every row depth, so the posts do too: same place on the
                # first step of every stair flight, equal distances, one straight handrail
                prof = step_profile("aisle", stub_here)
                off = min(0.22, 0.5 * min(tb2 - ta_ for ta_, tb2, _h in treads[:-1]))
                k = max(1, int(round(spacing / D)))
                starts = [-P_front if (P_front > 0 and stub_here) else 0.0] + [T0[i] + SR[i] for i in range(N - 1)] + [T0[-1] + SR[-1]]
                idx = list(range(0, len(starts), k))
                if idx[-1] != len(starts) - 1:
                    idx.append(len(starts) - 1)
                # all flight posts stand on the same spot of their first step, so their feet lie on one line;
                # the top landing has no next step, so its post is moved forward onto that line
                fl = [(starts[j] + off, h_at(prof, starts[j] + off)) for j in range(len(starts) - 1)]
                if len(fl) >= 3:
                    slope = (fl[-1][1] - fl[1][1]) / (fl[-1][0] - fl[1][0])
                elif len(fl) == 2:
                    slope = (fl[1][1] - fl[0][1]) / (fl[1][0] - fl[0][0])
                else:
                    slope = (H[-1] - fl[0][1]) / max(0.3, T0[-1] + SR[-1] - fl[0][0])
                t_top = fl[-1][0] + (H[-1] - fl[-1][1]) / slope if slope > 1e-6 else T0[-1] + SR[-1] + off
                t_top = min(max(t_top, T0[-1] + 0.05), t_corner - 0.05)
                posts = []
                for j in idx:
                    if j == len(starts) - 1:
                        if t_top - posts[-1][0] > 0.25:     # the landing post is not needed if the last
                            posts.append((t_top, H[-1]))    # flight post already stands at the top
                    else:
                        posts.append(fl[j])
                (ta_, ha_), (tz_, hz_) = posts[0], posts[-1]
                if len(fl) >= 2 and slope > 1e-6:
                    # handrail parallel to the stairs (slope of the post feet), through the top post, so the
                    # railing on the landing is exactly level
                    ta_, ha_ = tz_ - 1.0, hz_ - slope

                def line(t, ta_=ta_, ha_=ha_, tz_=tz_, hz_=hz_):
                    return ha_ + (hz_ - ha_) * (t - ta_) / (tz_ - ta_) if tz_ - ta_ > 1e-6 else ha_
                ts = [(t, line(t), foot) for t, foot in posts]
                # a first row that is deeper than the others (or a stair that starts at the first row): the
                # straight handrail would run down along the long landing. Instead: up the front stair, then
                # level along the landing of row 1, then up the stairs again.
                if N > 1 and len(fl) >= 2 and slope > 1e-6:
                    H0 = H[0]
                    t_k = tz_ - (hz_ - H0) / slope              # where the main handrail reaches row 1 level
                    # the front stair (down to the ground) has its own pitch: its rail runs parallel to it
                    slope_f = max(slope, H0 / P_front) if (stub_here and P_front > 0) else slope
                    if stub_here and P_front > 0:
                        t_s = fl[0][0] + (H0 - fl[0][1]) / slope_f  # where the front stair rail reaches row 1
                    else:
                        t_s = fl[0][0]
                    if t_k - t_s > 0.05:
                        def rail_h(t, t_s=t_s, t_k=t_k, H0=H0, slope_f=slope_f):
                            if t <= t_s:
                                return H0 - (t_s - t) * slope_f if (stub_here and P_front > 0) else H0
                            if t <= t_k:
                                return H0
                            return line(t)
                        pts_ = dict((round(t, 4), foot) for t, foot in posts if not (t_s + 0.2 < t < t_k - 0.2))
                        pts_[round(t_s, 4)] = h_at(prof, t_s + 1e-4)
                        pts_[round(t_k, 4)] = h_at(prof, t_k - 1e-4)
                        n_ = max(1, int(math.ceil((t_k - t_s) / spacing - 1e-6)))
                        for j_ in range(1, n_):
                            tt = t_s + (t_k - t_s) * j_ / n_
                            pts_[round(tt, 4)] = h_at(prof, tt)
                        merged_ = []
                        for t in sorted(pts_):
                            if merged_ and t - merged_[-1][0] < 0.2:
                                continue
                            merged_.append((t, pts_[t]))
                        ts = [(t, rail_h(t), foot) for t, foot in merged_]
                        posts = merged_
                if t_corner - posts[-1][0] > 0.3:
                    ts.append((t_corner, H[-1], H[-1]))
            else:
                # beside the rows: one post at the same place on every row, plus the corner
                ts = []
                for i in range(N):
                    t0 = T0[i] + (0.06 if (i == 0 and p.get("rail_front")) else 0.15)
                    t1 = T0[i] + DR[i] if i < N - 1 else t_corner
                    n = max(1, int(math.ceil((t1 - t0) / spacing - 1e-6)))
                    ts += [(t0 + (t1 - t0) * j / n, H[i], H[i]) for j in range(n)]
                ts.append((t_corner, H[-1], H[-1]))
            dside = _sub(F.at(s + inset, 1.0), F.at(s + inset, 0.0))     # direction of the side railing
            side_key = "L" if inset > 0 else "R"
            if side_key in acc and ts:
                # the side access joins the first row here: the railing starts behind it
                tcut = w_acc + 0.06
                hc, fc = ts[-1][1], ts[-1][2]
                for (t1_, h1__, f1_), (t2_, h2__, f2_) in zip(ts, ts[1:]):
                    if t1_ <= tcut <= t2_:
                        u_ = (tcut - t1_) / (t2_ - t1_) if t2_ - t1_ > 1e-9 else 0.0
                        hc = h1__ + (h2__ - h1__) * u_
                        fc = h_at(step_profile("aisle", stub_here), tcut) if stair else H[0]
                        break
                ts = [(tcut, max(hc, H[0]), fc)] + [x for x in ts if x[0] > tcut + 0.15]
            if ts and side_key not in acc:
                # the top handrail runs 20 cm past the first post at the front (not into a side access opening)
                t0_, h0_, _f0 = ts[0]
                t1_, h1_, _f1 = ts[1] if len(ts) > 1 else (t0_ + 1.0, h0_, h0_)
                a0, a1 = F.at(s + inset, t0_), F.at(s + inset, t1_)
                dl = math.hypot(a1[0] - a0[0], a1[1] - a0[1])
                k = 0.2 / dl if dl > 1e-9 else 0.0
                ext = (a0[0] - (a1[0] - a0[0]) * k, a0[1] - (a1[1] - a0[1]) * k, h0_ - (h1_ - h0_) * k)
                box_between((ext[0], ext[1], ext[2] + rh), (a0[0], a0[1], h0_ + rh), hand, hand)
            for tm, h, foot in ts:
                xy = F.at(s + inset, tm)
                post(xy, foot, h + rh, dside)      # the post stands on the step, the rail follows the slope
                if prev is not None:
                    span(prev, (xy[0], xy[1], h))
                prev = (xy[0], xy[1], h)

    if p.get("rail_front") and rh > 0:
        # along the front edge of the first row, open where the stairs are
        spacing = max(0.3, float(p["rail_post_spacing"]))
        tf = 0.06
        open_ = [iv for iv in aisles if has_stub((iv[0] + iv[1]) / 2) or P_front <= 0]
        cuts_f = sorted(set([sA, sB] + [x for iv in open_ for x in iv]))
        for a, b in zip(cuts_f, cuts_f[1:]):
            m_ = (a + b) / 2
            if b - a < 0.3 or any(iv[0] - 1e-6 <= m_ <= iv[1] + 1e-6 for iv in open_):
                continue
            a2 = a + 0.06
            b2 = b - 0.06
            ss = [a2] + [x for x in F.S if a2 + 1e-6 < x < b2 - 1e-6] + [b2]
            pts_f = [(F.at(ss[0], tf), F.tangent(ss[0], tf))]
            for u, v in zip(ss, ss[1:]):
                dent = front_dents.get((round(u, 4), round(v, 4)))
                if dent:
                    # around the sharp corner of a corner stair that starts at the first row
                    dp, dn = dent[0], dent[1]
                    Pf, Qf = F.at(u, tf), F.at(v, tf)
                    den = _cross(dp, dn)
                    Xf = _add(Pf, _mul(dp, _cross(_sub(Qf, Pf), dn) / den)) if abs(den) > 1e-9 else None
                    if Xf is not None:
                        pts_f.append((Xf, dp))
                    pts_f.append((Qf, dn))
                    continue
                n = max(1, int(math.ceil((v - u) / spacing - 1e-6)))
                for j in range(1, n + 1):
                    sv_ = u + (v - u) * j / n
                    pts_f.append((F.at(sv_, tf), F.tangent(sv_, tf)))
            prev = None
            for xy, dd_ in pts_f:
                post(xy, H[0], H[0] + rh, dd_)
                if prev is not None:
                    span((prev[0], prev[1], H[0]), (xy[0], xy[1], H[0]))
                prev = xy

    # ---------------------------------------------------- side access: ramp or stairs (structure and railings)
    def quad_dir(pts, want):
        """quad from 3D points, turned so that its normal points to 'want' (x, y, z)"""
        a_, b_, c_ = pts[0], pts[1], pts[2]
        u_ = (b_[0] - a_[0], b_[1] - a_[1], b_[2] - a_[2])
        v_ = (c_[0] - a_[0], c_[1] - a_[1], c_[2] - a_[2])
        n_ = (u_[1] * v_[2] - u_[2] * v_[1], u_[2] * v_[0] - u_[0] * v_[2], u_[0] * v_[1] - u_[1] * v_[0])
        if n_[0] * want[0] + n_[1] * want[1] + n_[2] * want[2] < 0:
            pts = pts[::-1]
        return pts

    for side_, a_ in acc.items():
        sgn = 1.0 if side_ == "L" else -1.0           # +1: s grows towards the tribune
        stairs_mode = a_["mode"] == "STAIRS"
        mat_ = 1 if stairs_mode else 0
        # s positions of the profile from the foot to the first row
        if stairs_mode:
            ss_ = [a_["bot"] + sgn * a_["run"] * j / a_["n"] for j in range(a_["n"] + 1)] + [a_["top"]]
        else:
            ss_ = [a_["bot"] + sgn * a_["run"] * j / 8 for j in range(9)] + [a_["top"]]
        t_f, t_b = 0.0, w_acc
        fwd = _sub(F.at(a_["top"], -1.0), F.at(a_["top"], 0.0))           # towards the front
        outw = _sub(F.at(a_["bot"], 0.0), F.at(a_["top"], 0.0))           # away from the tribune
        for u, v in zip(ss_, ss_[1:]):
            if abs(v - u) < 1e-6:
                continue
            if stairs_mode:
                hu = hv = h1 * min(a_["n"], ss_.index(v)) / a_["n"] if v != a_["top"] else h1
            else:
                hu, hv = acc_h(side_, u), acc_h(side_, v)
            pu0, pv0, pu1, pv1 = F.at(u, t_f), F.at(v, t_f), F.at(u, t_b), F.at(v, t_b)
            top_ = quad_dir([(pu0[0], pu0[1], hu), (pv0[0], pv0[1], hv), (pv1[0], pv1[1], hv), (pu1[0], pu1[1], hu)], (0, 0, 1))
            quad(*[vv((q[0], q[1]), q[2]) for q in top_], mat_)
            for tt_, want in ((t_f, (fwd[0], fwd[1], 0.0)), (t_b, (-fwd[0], -fwd[1], 0.0))):
                pu, pv = F.at(u, tt_), F.at(v, tt_)
                wall = quad_dir([(pu[0], pu[1], 0.0), (pv[0], pv[1], 0.0), (pv[0], pv[1], hv), (pu[0], pu[1], hu)], want)
                quad(*[vv((q[0], q[1]), q[2]) for q in wall], 0)
        if stairs_mode:
            # risers, looking away from the tribune
            for j in range(a_["n"]):
                sr = ss_[j]
                lo_ = h1 * j / a_["n"]
                hi_ = h1 * (j + 1) / a_["n"]
                p0_, p1_ = F.at(sr, t_f), F.at(sr, t_b)
                rs = quad_dir([(p0_[0], p0_[1], lo_), (p1_[0], p1_[1], lo_), (p1_[0], p1_[1], hi_), (p0_[0], p0_[1], hi_)],
                              (outw[0], outw[1], 0.0))
                quad(*[vv((q[0], q[1]), q[2]) for q in rs], mat_)
        # railings on both long sides, from the foot up to the first row
        if rh > 0:
            spacing = max(0.3, float(p["rail_post_spacing"]))
            s0_ = a_["bot"] + sgn * 0.06
            s1_ = a_["top"] - sgn * 0.06
            run_end = a_["bot"] + sgn * a_["run"]

            def hr(sv_):
                # handrail: through the stair nosings or along the ramp
                d_ = abs(sv_ - a_["bot"])
                return h1 * min(1.0, d_ / a_["run"]) if not stairs_mode else h1 * min(1.0, (d_ + a_["run"] / a_["n"]) / (a_["run"] + a_["run"] / a_["n"]))
            knots_ = [s0_, run_end, s1_]
            for tt_ in (0.06, w_acc - 0.06):
                if tt_ == 0.06 and p.get("rail_front"):
                    pass
                prev = None
                dense_ = [knots_[0]]
                for u, v in zip(knots_, knots_[1:]):
                    n_ = max(1, int(math.ceil(abs(v - u) / spacing - 1e-6)))
                    dense_ += [u + (v - u) * j / n_ for j in range(1, n_ + 1)]
                for j, sv_ in enumerate(dense_):
                    xy = F.at(sv_, tt_)
                    foot_ = acc_h(side_, sv_, nav=False)
                    base_ = hr(sv_)
                    post(xy, min(foot_, base_ + rh - 0.05), base_ + rh, _sub(F.at(sv_ + sgn, tt_), xy))
                    if prev is not None:
                        span(prev, (xy[0], xy[1], base_))
                    prev = (xy[0], xy[1], base_)
                # the handrail runs 20 cm past the post at the foot
                a0 = F.at(dense_[0], tt_)
                a1 = F.at(dense_[1], tt_)
                dl = math.hypot(a1[0] - a0[0], a1[1] - a0[1])
                k_ = 0.2 / dl if dl > 1e-9 else 0.0
                h0r, h1r = hr(dense_[0]) + rh, hr(dense_[1]) + rh
                box_between((a0[0] - (a1[0] - a0[0]) * k_, a0[1] - (a1[1] - a0[1]) * k_, h0r - (h1r - h0r) * k_),
                            (a0[0], a0[1], h0r), hand, hand)

    # ---------------------------------------------------- seats
    blocks = []     # seating blocks: s-intervals between aisles, corners and the ends
    cuts = sorted(set([sA, sB] + [x for iv in aisles for x in iv] + [F.S[i] for i in corners if sA < F.S[i] < sB]))
    for a, b in zip(cuts, cuts[1:]):
        if b - a < 0.3 or in_aisle((a + b) / 2):
            continue
        blocks.append((a, b))

    def end_margin(s_edge, t):
        if any(abs(s_edge - x) < 1e-6 for iv in aisles for x in iv) or (s_edge > 1e-6 and abs(s_edge - sA) < 1e-6) \
                or (s_edge < L - 1e-6 and abs(s_edge - sB) < 1e-6):
            # the stair edge may be slanted against the rows: keep the seat corners off it
            k = min(range(len(F.S)), key=lambda i: abs(F.S[i] - s_edge))
            m = _norm(F.M[k])
            tilt = 0.0
            for seg in (k - 1, k):
                if 0 <= seg < len(F.d):
                    tilt = max(tilt, math.acos(max(-1.0, min(1.0, _dot(m, _left(F.d[seg]))))))
            return sw / 2 + 0.05 + sd / 2 * math.tan(min(tilt, 1.3))
        for i in corners:
            if abs(F.S[i] - s_edge) < 1e-6:
                return sd / 2 * math.tan(math.radians(abs(F.turn[i])) / 2) + sw / 2 + 0.05
        return sw / 2 + 0.1

    seats = []
    lx, ly, lz = p["sit"]
    zoff = float(p.get("seat_height", 0.0))
    for r in range(N):
        t0 = T0[r]
        tc = t0 + DR[r] - float(p["seat_back_gap"]) - sd / 2    # seat centre (origin) depth inside its row
        t_target = t0 + SR[r] / 2
        order = 0
        for a, b in blocks:
            # polyline of the row centre inside the block
            ss = [a] + [x for x in F.S if a + 1e-6 < x < b - 1e-6] + [b]
            P = [F.at(s, tc) for s in ss]
            cum = [0.0]
            for u, v in zip(P, P[1:]):
                cum.append(cum[-1] + _len(_sub(v, u)))
            total = cum[-1]
            ma, mb = end_margin(a, tc), end_margin(b, tc)
            avail = total - ma - mb
            if avail < -1e-6:
                continue
            n = int(math.floor(avail / pitch + 1e-6)) + 1
            start = ma + (avail - (n - 1) * pitch) / 2
            for j in range(n):
                dist = start + j * pitch
                q = 0
                while q < len(cum) - 2 and cum[q + 1] < dist:
                    q += 1
                seg_len = cum[q + 1] - cum[q]
                u = (dist - cum[q]) / seg_len if seg_len > 1e-12 else 0.0
                s = ss[q] + (ss[q + 1] - ss[q]) * u
                origin = F.at(s, tc)
                tang = F.tangent(s, tc)
                face = _mul(_left(tang), -1.0)        # towards the show area
                yaw = math.atan2(face[0], -face[1])   # rotation about Z that turns local -Y into 'face'
                cy, sy = math.cos(yaw), math.sin(yaw)
                sit = (origin[0] + lx * cy - ly * sy, origin[1] + lx * sy + ly * cy, H[r] + lz + zoff)
                tgt = F.at(s, t_target)
                order += 1
                seats.append({"origin": (origin[0], origin[1], H[r] + zoff), "yaw": yaw, "sit": sit,
                              "target": (tgt[0], tgt[1], H[r]), "row": r + 1, "order": order, "free": False})
    if not seats:
        raise GenError("No seats fit. Make the tribune longer or the aisles narrower.")
    if len(seats) > 400:
        warn.append("%d seats: very large tribunes can be slow in the game." % len(seats))

    # ---------------------------------------------------- outline (ride footprint) with entrances
    t_lo, t_hi = t_front, t_end
    t_lo_l = t_sw - PAD if pad_l else t_lo
    t_lo_r = t_sw - PAD if pad_r else t_lo
    front = list(fcurve)            # outer edge of the show area, following the tribune
    back = [F.at(s, t_hi) for s in [s_lo] + [x for x in F.S if 0 < x < L] + [s_hi]]
    poly, kinds = [], []          # polygon counter-clockwise from above, kind per edge (edge i = poly[i] -> poly[i+1])
    el = float(p["entrance_length"])

    def side_pts(s, t_a, t_b, ent, foot=None):
        """points from t_a to t_b on the side line s; returns list of (point, kind of edge to next).
        ent: entrance/exit side; foot: (t0, t1) where a side access arrives - entrance and exit can go there too"""
        lo, hi = min(t_a, t_b), max(t_a, t_b)
        exf = []
        if ent:
            depth = hi - lo
            exf.append((lo, hi) if (el <= 0.1 or el >= depth - 0.1) else (lo, lo + el))
        if foot:
            exf.append((max(lo, foot[0]), min(hi, foot[1])))
        cuts = sorted(set([lo, hi] + [x for iv in exf for x in iv if lo < x < hi]))
        pieces = []
        for u, v in zip(cuts, cuts[1:]):
            m = (u + v) / 2
            pieces.append((u, v, "EXF" if any(i0 - 1e-6 <= m <= i1 + 1e-6 for i0, i1 in exf) else "FON"))
        # merge neighbours of the same kind
        merged = []
        for pc in pieces:
            if merged and merged[-1][2] == pc[2]:
                merged[-1] = (merged[-1][0], pc[1], pc[2])
            else:
                merged.append(pc)
        if t_a <= t_b:
            return [(F.at(s, u), kd) for u, v, kd in merged]
        return [(F.at(s, v), kd) for u, v, kd in reversed(merged)]

    # front edge: from front-right to front-left? build counter-clockwise: the rows are on the left of the
    # front line, so going along the front line and back along the back line is clockwise for a straight
    # tribune along +X (rows at +Y). Counter-clockwise: front line reversed first.
    # Order: front (s_hi -> s_lo)?  We use: front from s_lo to s_hi, right side up, back from s_hi to s_lo,
    # left side down. For a straight tribune (rows at +Y) that is counter-clockwise.
    seq = []
    for i, q in enumerate(front[:-1]):
        seq.append((q, "EXF" if p["entrance_front"] else "FON"))
    seq += side_pts(s_hi, t_lo_r, t_hi, p["entrance_right"], (t_lo_r, w_acc) if "R" in acc else None)
    for q in list(reversed(back))[:-1]:
        seq.append((q, "EXF" if p["entrance_back"] else "FON"))
    seq += side_pts(s_lo, t_hi, t_lo_l, p["entrance_left"], (t_lo_l, w_acc) if "L" in acc else None)
    for q, kd in seq:
        poly.append(q)
        kinds.append(kd)
    if "EXF" not in kinds:
        raise GenError("Choose at least one entrance side.")

    # ---------------------------------------------------- booth
    bmode = p["booth"]
    s_wl = (acc["L"]["pad"] - Ws / 2) if "L" in acc else -Ws / 2         # middle of the side walkways
    s_wr = (acc["R"]["pad"] + Ws / 2) if "R" in acc else L + Ws / 2
    if bmode == "left" and Ws > 0:
        bxy = F.at(s_wl, T_back / 2)
    elif bmode == "right" and Ws > 0:
        bxy = F.at(s_wr, T_back / 2)
    elif Wb > 0:
        bxy = F.at(L / 2, T_back + Wb / 2)
    elif Ws > 0:
        bxy = F.at(s_wl, T_back / 2)
    else:
        bxy = F.at(L / 2, t_front / 2)
        warn.append("No side or back walkway: the ride booth was put on the show area.")

    # ---------------------------------------------------- centre everything on the origin
    xs = [q[0] for q in poly]
    ys = [q[1] for q in poly]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    if room:
        cx = cy = 0.0   # stays where the room is

    def c2(q): return (q[0] - cx, q[1] - cy)
    def c3(q): return (q[0] - cx, q[1] - cy, q[2])

    for st in seats:
        st["origin"], st["sit"], st["target"] = c3(st["origin"]), c3(st["sit"]), c3(st["target"])
    sx_ = [q[0] for q in top_line] + [q0[0], q1[0]]
    sy_ = [q[1] for q in top_line] + [q0[1], q1[1]]
    mid_front = F.at(L / 2, t_sw)
    cfar = fcurve[len(fcurve) // 2] if len(fcurve) % 2 else \
        ((fcurve[len(fcurve) // 2 - 1][0] + fcurve[len(fcurve) // 2][0]) / 2,
         (fcurve[len(fcurve) // 2 - 1][1] + fcurve[len(fcurve) // 2][1]) / 2)
    stage_c = ((mid_front[0] + cfar[0]) / 2, (mid_front[1] + cfar[1]) / 2)
    return {
        "params": p,
        "structure": {"verts": [c3(v) for v in sv], "faces": sfaces, "mat": smat},
        "rail": {"verts": [c3(v) for v in rail_v], "faces": rail_f, "mat": rail_m},
        "nav": {"verts": [c3(v) for v in nverts], "tris": ntris},
        "seats": seats,
        "outline": {"poly": [c2(q) for q in poly], "kinds": kinds},
        "booth": c2(bxy) + (0.0,),
        "stage": c2(stage_c) + (0.0,),
        "warnings": warn,
        "info": {"length": L, "depth": T_back, "rows": N, "lane": S, "seats": len(seats), "aisles": aisles,
                 "stairs": [{"pos": st_["pos"], "bottom": st_["bottom"], "forced": st_["forced"]} for st_ in stairs]},
    }


# ------------------------------------------------------------------ random free seats


def random_free(seats, seed=7, group_min=2, group_max=6, gap_min=1, gap_max=2, free_start=True):
    """Marks seats as free in random gaps between groups (like real audiences). Changes 'free' in place."""
    import random
    rnd = random.Random(int(seed))
    rows = {}
    for st in seats:
        rows.setdefault(st["row"], []).append(st)
    group_min, group_max = max(1, int(group_min)), max(int(group_min), int(group_max))
    gap_min, gap_max = max(0, int(gap_min)), max(int(gap_min), int(gap_max))
    for r, row in rows.items():
        row.sort(key=lambda x: x["order"])
        for st in row:
            st["free"] = True
        i = rnd.randint(0, 1) if free_start else 0
        while i < len(row):
            g = rnd.randint(group_min, group_max)
            for st in row[i:i + g]:
                st["free"] = False
            i += g + rnd.randint(gap_min, gap_max)
    return seats
