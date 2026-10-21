"""Tools for tribune models built by hand (pure Python, no bpy).

- seats_from_parts: one seat per seat mesh (or loose part): sit point, facing, row and order
- nav_grid: walkable navmesh from height samples on a regular grid (conforming triangles)
- default_outline: rectangle around the model with entrances left and right
"""
import math
from collections import defaultdict

from . import navcheck


def _norm2(x, y):
    l = math.hypot(x, y)
    return (x / l, y / l) if l > 1e-9 else (0.0, -1.0)


def seat_from_points(pts, facing, clearance=0.2, lane=0.45):
    """pts: world points (x, y, z) of one seat. facing: unit XY vector the guest looks to.
    Returns sit point, yaw, footprint and the walk target XY (height still unknown)."""
    fx, fy = facing
    rx, ry = fy, -fx                       # right-hand side of the guest
    a = [p[0] * fx + p[1] * fy for p in pts]     # forward coordinate
    b = [p[0] * rx + p[1] * ry for p in pts]     # sideways coordinate
    amin, amax = min(a), max(a)
    bmin, bmax = min(b), max(b)
    zmin = min(p[2] for p in pts)
    depth = max(0.05, amax - amin)
    front = [p[2] for p, ai in zip(pts, a) if ai > amin + 0.6 * depth]
    pan = max(front) if front else max(p[2] for p in pts)
    a_sit = amin + min(0.35, 0.64 * depth)
    bc = (bmin + bmax) / 2
    sx, sy = a_sit * fx + bc * rx, a_sit * fy + bc * ry
    a_t = amax + clearance + lane / 2
    tx, ty = a_t * fx + bc * rx, a_t * fy + bc * ry
    yaw = math.atan2(fx, -fy)
    return {"sit": (sx, sy, pan), "yaw": yaw, "target_xy": (tx, ty), "bottom": zmin,
            "width": bmax - bmin, "depth": depth,
            # footprint relative to the sit point (along the facing direction / sideways)
            "back": a_sit - amin, "front": amax - a_sit, "half_w": (bmax - bmin) / 2}


def refine_facing(seats, rough):
    """Turns every seat perpendicular to its row (direction between its neighbours in the row),
    on the same side as the rough facing. seats need 'row', 'order', 'sit'. rough(seat) -> (fx, fy)."""
    rows = defaultdict(list)
    for s in seats:
        rows[s["row"]].append(s)
    for lst in rows.values():
        lst.sort(key=lambda s: s["order"])
        if len(lst) < 2:
            continue
        gaps = sorted(math.hypot(b["sit"][0] - a["sit"][0], b["sit"][1] - a["sit"][1]) for a, b in zip(lst, lst[1:]))
        lim = gaps[len(gaps) // 2] * 1.6
        for i, s in enumerate(lst):
            tx = ty = 0.0
            for j in (i - 1, i + 1):
                if 0 <= j < len(lst):
                    o = lst[j]
                    dx, dy = o["sit"][0] - s["sit"][0], o["sit"][1] - s["sit"][1]
                    d = math.hypot(dx, dy)
                    if 1e-6 < d <= lim:
                        sgn = 1.0 if j > i else -1.0
                        tx += sgn * dx / d
                        ty += sgn * dy / d
            if abs(tx) + abs(ty) < 1e-9:
                continue
            tx, ty = _norm2(tx, ty)
            fx, fy = ty, -tx
            rx, ry = rough(s)
            if fx * rx + fy * ry < 0:
                fx, fy = -fx, -fy
            s["facing"] = (fx, fy)
    return seats


class SeatBlocker:
    """Fast test: is a point on the floor under/at a seat (plus clearance in front)?
    seats: dicts with sit (x, y, ...), facing (fx, fy), back, front, half_w, floor"""

    def __init__(self, seats, clearance=0.2, cell=1.0):
        self.cell = cell
        self.items = []
        self.grid = defaultdict(list)
        for s in seats:
            fx, fy = s["facing"]
            rx, ry = fy, -fx
            sx, sy = s["sit"][0], s["sit"][1]
            a0 = sx * fx + sy * fy - s["back"] - 0.02
            a1 = sx * fx + sy * fy + s["front"] + clearance
            bm = sx * rx + sy * ry
            box = (fx, fy, rx, ry, a0, a1, bm - s["half_w"] - 0.02, bm + s["half_w"] + 0.02, s["floor"])
            k = len(self.items)
            self.items.append(box)
            pts = [(a * fx + b * rx, a * fy + b * ry) for a in (box[4], box[5]) for b in (box[6], box[7])]
            x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
            y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
            for i in range(int(math.floor(x0 / cell)), int(math.floor(x1 / cell)) + 1):
                for j in range(int(math.floor(y0 / cell)), int(math.floor(y1 / cell)) + 1):
                    self.grid[(i, j)].append(k)

    def __call__(self, x, y, z):
        for k in self.grid.get((int(math.floor(x / self.cell)), int(math.floor(y / self.cell))), ()):
            fx, fy, rx, ry, a0, a1, b0, b1, floor = self.items[k]
            if abs(z - floor) > 0.15:
                continue
            a = x * fx + y * fy
            b = x * rx + y * ry
            if a0 <= a <= a1 and b0 <= b <= b1:
                return True
        return False


def merge_parts(parts, min_overlap=0.3):
    """Groups loose parts that belong to one seat (shell, legs, armrests): parts whose footprints (XY boxes)
    overlap by more than min_overlap of the smaller one. parts: list of point arrays (n, 3). Returns lists of indices."""
    boxes = []
    for P in parts:
        xs = [p[0] for p in P]
        ys = [p[1] for p in P]
        boxes.append((min(xs), min(ys), max(xs), max(ys)))
    parent = list(range(len(parts)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    cell = 1.0
    grid = defaultdict(list)
    for i, (x0, y0, x1, y1) in enumerate(boxes):
        for gx in range(int(math.floor(x0 / cell)), int(math.floor(x1 / cell)) + 1):
            for gy in range(int(math.floor(y0 / cell)), int(math.floor(y1 / cell)) + 1):
                grid[(gx, gy)].append(i)
    for lst in grid.values():
        for a_i in range(len(lst)):
            for b_i in range(a_i + 1, len(lst)):
                a, b = lst[a_i], lst[b_i]
                A, B = boxes[a], boxes[b]
                w = min(A[2], B[2]) - max(A[0], B[0])
                h = min(A[3], B[3]) - max(A[1], B[1])
                if w <= 0 or h <= 0:
                    continue
                aa = max(1e-6, (A[2] - A[0]) * (A[3] - A[1]))
                ab = max(1e-6, (B[2] - B[0]) * (B[3] - B[1]))
                if w * h > min_overlap * min(aa, ab):
                    parent[find(a)] = find(b)
    groups = defaultdict(list)
    for i in range(len(parts)):
        groups[find(i)].append(i)
    return list(groups.values())


def facing_for(center, mode, stage=None, axis=(0.0, -1.0), obj_forward=None):
    if mode == "STAGE" and stage is not None:
        return _norm2(stage[0] - center[0], stage[1] - center[1])
    if mode == "OBJECT" and obj_forward is not None:
        return _norm2(obj_forward[0], obj_forward[1])
    return _norm2(axis[0], axis[1])


def number_rows(seats, stage=None, row_tol=0.12):
    """Assigns 'row' (1 = lowest) and 'order' (left to right as seen by the audience) to seat dicts
    that have 'sit' and 'floor'."""
    if not seats:
        return seats
    hs = sorted(set(round(s["floor"] / row_tol) for s in seats))
    # merge neighbouring height buckets
    groups = []
    for h in hs:
        if groups and h - groups[-1][-1] <= 1:
            groups[-1].append(h)
        else:
            groups.append([h])
    bucket_row = {}
    for i, g in enumerate(groups):
        for h in g:
            bucket_row[h] = i + 1
    rows = defaultdict(list)
    for s in seats:
        s["row"] = bucket_row[round(s["floor"] / row_tol)]
        rows[s["row"]].append(s)
    for r, lst in rows.items():
        if stage is not None:
            # angle around the stage, seen from above; audience left = larger angle
            ang = [math.atan2(s["sit"][1] - stage[1], s["sit"][0] - stage[0]) for s in lst]
            mean = math.atan2(sum(math.sin(x) for x in ang), sum(math.cos(x) for x in ang))
            key = lambda s: -(((math.atan2(s["sit"][1] - stage[1], s["sit"][0] - stage[0]) - mean + math.pi)
                               % (2 * math.pi)) - math.pi)
        else:
            f = (math.sin(lst[0]["yaw"]), -math.cos(lst[0]["yaw"]))
            right = (f[1], -f[0])
            key = lambda s: -(s["sit"][0] * right[0] + s["sit"][1] * right[1])
        lst.sort(key=key)
        for i, s in enumerate(lst):
            s["order"] = i + 1
    return seats


def default_outline(xmin, ymin, xmax, ymax, margin=1.5, entrance_length=6.0):
    """Rectangle around the model (audience looks to -Y). Entrances on the left and right side,
    starting at the front corners. Returns poly (counter-clockwise) and edge kinds."""
    x0, y0, x1, y1 = xmin - margin, ymin - margin, xmax + margin, ymax + margin
    depth = y1 - y0
    el = min(entrance_length, depth) if entrance_length > 0.1 else depth
    poly = [(x0, y0), (x1, y0), (x1, y0 + el)]
    kinds = ["FON", "EXF"]
    if el < depth - 0.05:
        poly.append((x1, y1))
        kinds.append("FON")
    else:
        poly[-1] = (x1, y1)
    poly.append((x0, y1))
    kinds.append("FON")     # back edge (x1,y1)->(x0,y1)
    if el < depth - 0.05:
        poly.append((x0, y0 + el))
        kinds.append("FON")
    kinds.append("EXF")
    return poly, kinds


def point_in_poly(x, y, poly):
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def nav_grid(bounds, sample, cell=0.1, max_step=0.25, blocked=None, clearance=0.2, outline=None, kinds=None,
             progress=None):
    """Builds a navmesh from height samples.

    bounds: (xmin, ymin, xmax, ymax)
    sample(x, y) -> (z or None, blocked_by_overhead: bool)
        z: height of the highest walkable surface (ground = 0 inside the outline), None = not walkable
    Returns verts (x, y, z) and triangles (counter-clockwise). All neighbouring triangles share full edges.
    """
    xmin, ymin, xmax, ymax = bounds
    nx = max(1, int(math.ceil((xmax - xmin) / cell)))
    ny = max(1, int(math.ceil((ymax - ymin) / cell)))
    if (nx + 1) * (ny + 1) > 900000:
        raise ValueError("The area is too big for this grid size; use a bigger cell size.")
    Z = [[None] * (nx + 1) for _ in range(ny + 1)]
    over = [[False] * (nx + 1) for _ in range(ny + 1)]
    for j in range(ny + 1):
        if progress and j % 20 == 0:
            progress(j / (ny + 1))
        y = ymin + j * cell
        for i in range(nx + 1):
            x = xmin + i * cell
            z, o = sample(x, y)
            Z[j][i] = z
            over[j][i] = o
    # keep a distance to overhead obstacles (seat shells, railings): dilate the blocked points
    r = int(math.ceil(clearance / cell - 1e-6)) if clearance > 0 else 0
    bad = [[over[j][i] or Z[j][i] is None for i in range(nx + 1)] for j in range(ny + 1)]
    if r > 0:
        src = [[over[j][i] for i in range(nx + 1)] for j in range(ny + 1)]
        for j in range(ny + 1):
            for i in range(nx + 1):
                if not src[j][i]:
                    continue
                for dj in range(-r, r + 1):
                    for di in range(-r, r + 1):
                        if di * di + dj * dj > r * r:
                            continue
                        jj, ii = j + dj, i + di
                        if 0 <= jj <= ny and 0 <= ii <= nx and Z[jj][ii] is not None \
                                and abs(Z[jj][ii] - (Z[j][i] if Z[j][i] is not None else Z[jj][ii])) < 0.6:
                            bad[jj][ii] = True
    # valid cells
    ok = [[False] * nx for _ in range(ny)]
    flat = [[False] * nx for _ in range(ny)]
    for j in range(ny):
        for i in range(nx):
            c = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
            if any(bad[cj][ci] for ci, cj in c):
                continue
            zs = [Z[cj][ci] for ci, cj in c]
            if all(abs(zs[a] - zs[(a + 1) % 4]) <= max_step for a in range(4)):
                ok[j][i] = True
                flat[j][i] = max(zs) - min(zs) < 1e-4
    # merge flat cells of equal height into rectangles (fewer triangles); sloped cells stay small
    used = [[False] * nx for _ in range(ny)]
    faces = []      # (i0, j0, i1, j1, flat)
    for j in range(ny):
        for i in range(nx):
            if not ok[j][i] or used[j][i]:
                continue
            if not flat[j][i]:
                used[j][i] = True
                faces.append((i, j, i + 1, j + 1, False))
                continue
            z0 = Z[j][i]
            w = 1
            while i + w < nx and ok[j][i + w] and flat[j][i + w] and not used[j][i + w] and abs(Z[j][i + w] - z0) < 1e-4:
                w += 1
            h = 1
            while j + h < ny and all(ok[j + h][i + k] and flat[j + h][i + k] and not used[j + h][i + k]
                                     and abs(Z[j + h][i + k] - z0) < 1e-4 for k in range(w)):
                h += 1
            for jj in range(j, j + h):
                for ii in range(i, i + w):
                    used[jj][ii] = True
            faces.append((i, j, i + w, j + h, True))
    corner_used = set()
    for i0, j0, i1, j1, _f in faces:
        corner_used.update(((i0, j0), (i1, j0), (i1, j1), (i0, j1)))
    verts, index, tris = [], {}, []

    def v(i, j):
        k = (i, j)
        if k not in index:
            index[k] = len(verts)
            verts.append((xmin + i * cell, ymin + j * cell, Z[j][i]))
        return index[k]

    for i0, j0, i1, j1, is_flat in faces:
        # perimeter counter-clockwise, with every grid point a neighbour uses (no T-junctions)
        ring = [(i, j0) for i in range(i0, i1)] + [(i1, j) for j in range(j0, j1)] + \
               [(i, j1) for i in range(i1, i0, -1)] + [(i0, j) for j in range(j1, j0, -1)]
        ring = [p for p in ring if p in corner_used]
        if len(ring) == 4:
            a, b, c, d = (v(*p) for p in ring)
            tris.append((a, b, c))
            tris.append((a, c, d))
            continue
        # fan around a centre point
        cx, cy = xmin + (i0 + i1) / 2 * cell, ymin + (j0 + j1) / 2 * cell
        ci = len(verts)
        verts.append((cx, cy, Z[j0][i0]))
        ids = [v(*p) for p in ring]
        for k in range(len(ids)):
            tris.append((ci, ids[k], ids[(k + 1) % len(ids)]))
    # keep only what can be reached from an entrance
    if outline and kinds and tris:
        rep_comp, edge_tris = navcheck.components(tris)
        keep_c = set()
        n = len(outline)
        for e, ts in edge_tris.items():
            if len(ts) != 1:
                continue
            p, q = verts[e[0]], verts[e[1]]
            for k, kd in enumerate(kinds):
                if kd != "EXF":
                    continue
                A, B = outline[k], outline[(k + 1) % n]
                if navcheck._seg_dist(p, A, B) < cell * 1.5 + 0.3 and navcheck._seg_dist(q, A, B) < cell * 1.5 + 0.3:
                    keep_c.add(rep_comp[ts[0]])
        if keep_c:
            tris = [t for t, c in zip(tris, rep_comp) if c in keep_c]
    used = sorted(set(i for t in tris for i in t))
    remap = {o: n for n, o in enumerate(used)}
    return [verts[i] for i in used], [tuple(remap[i] for i in t) for t in tris]
