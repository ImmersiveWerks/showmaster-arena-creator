"""Navmesh checks (pure Python): can guests walk from an entrance to every seat?

Two triangles are connected only when they share a complete edge (both end points identical).
That is how the game builds its walking graph, so a gap, a height step or a T-junction blocks the way.
"""
import math
from collections import defaultdict, deque


def weld(verts, tris, eps=0.002):
    """Merges vertices closer than eps. Returns new verts, tris."""
    key = {}
    remap = []
    out = []
    for v in verts:
        k = (round(v[0] / eps), round(v[1] / eps), round(v[2] / eps))
        if k not in key:
            key[k] = len(out)
            out.append(tuple(v))
        remap.append(key[k])
    nt = []
    for t in tris:
        a, b, c = (remap[i] for i in t)
        if a != b and b != c and a != c:
            nt.append((a, b, c))
    return out, nt


def components(tris):
    """Connected components over shared edges. Returns comp id per triangle."""
    edge_tris = defaultdict(list)
    for i, (a, b, c) in enumerate(tris):
        for e in ((a, b), (b, c), (c, a)):
            edge_tris[tuple(sorted(e))].append(i)
    comp = [-1] * len(tris)
    cid = 0
    for start in range(len(tris)):
        if comp[start] >= 0:
            continue
        comp[start] = cid
        q = deque([start])
        while q:
            i = q.popleft()
            a, b, c = tris[i]
            for e in ((a, b), (b, c), (c, a)):
                for j in edge_tris[tuple(sorted(e))]:
                    if comp[j] < 0:
                        comp[j] = cid
                        q.append(j)
        cid += 1
    return comp, edge_tris


def _in_tri(p, a, b, c, eps=1e-6):
    d1 = (p[0] - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (p[1] - b[1])
    d2 = (p[0] - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (p[1] - c[1])
    d3 = (p[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (p[1] - a[1])
    neg = d1 < -eps or d2 < -eps or d3 < -eps
    pos = d1 > eps or d2 > eps or d3 > eps
    return not (neg and pos)


def _height(p, a, b, c):
    det = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
    if abs(det) < 1e-12:
        return (a[2] + b[2] + c[2]) / 3
    l1 = ((b[1] - c[1]) * (p[0] - c[0]) + (c[0] - b[0]) * (p[1] - c[1])) / det
    l2 = ((c[1] - a[1]) * (p[0] - c[0]) + (a[0] - c[0]) * (p[1] - c[1])) / det
    return l1 * a[2] + l2 * b[2] + (1 - l1 - l2) * c[2]


class TriIndex:
    def __init__(self, verts, tris, cell=2.0):
        self.cell = cell
        self.grid = defaultdict(list)
        for i, (a, b, c) in enumerate(tris):
            xs = (verts[a][0], verts[b][0], verts[c][0])
            ys = (verts[a][1], verts[b][1], verts[c][1])
            for gx in range(int(math.floor(min(xs) / cell)), int(math.floor(max(xs) / cell)) + 1):
                for gy in range(int(math.floor(min(ys) / cell)), int(math.floor(max(ys) / cell)) + 1):
                    self.grid[(gx, gy)].append(i)

    def near(self, x, y):
        return self.grid.get((int(math.floor(x / self.cell)), int(math.floor(y / self.cell))), ())


def locate(p, verts, tris, max_dz=0.5, index=None):
    """Triangle under point p (x, y, z) whose height is within max_dz, else None."""
    best, bd = None, None
    cand = index.near(p[0], p[1]) if index is not None else range(len(tris))
    for i in cand:
        a, b, c = tris[i]
        A, B, C = verts[a], verts[b], verts[c]
        if p[0] < min(A[0], B[0], C[0]) - 1e-3 or p[0] > max(A[0], B[0], C[0]) + 1e-3:
            continue
        if p[1] < min(A[1], B[1], C[1]) - 1e-3 or p[1] > max(A[1], B[1], C[1]) + 1e-3:
            continue
        if not _in_tri(p, A, B, C):
            continue
        dz = abs(_height(p, A, B, C) - p[2])
        if dz <= max_dz and (bd is None or dz < bd):
            best, bd = i, dz
    return best


def _seg_dist(p, a, b):
    ax, ay = b[0] - a[0], b[1] - a[1]
    l2 = ax * ax + ay * ay
    u = 0.0 if l2 < 1e-12 else max(0.0, min(1.0, ((p[0] - a[0]) * ax + (p[1] - a[1]) * ay) / l2))
    return math.hypot(p[0] - a[0] - ax * u, p[1] - a[1] - ay * u)


def check(verts, tris, outline_poly, outline_kinds, seats, entrance_dist=0.6):
    """seats: list of dicts with 'target' (x,y,z), 'free' (bool), 'name' (optional).
    Returns a report dict."""
    verts, tris = weld(verts, tris)
    rep = {"tris": len(tris), "verts": len(verts), "errors": [], "warnings": [], "bad_seats": [], "ok_seats": 0}
    if not tris:
        rep["errors"].append("The navmesh is empty.")
        return rep
    if len(verts) > 65000:
        rep["errors"].append("The navmesh has %d points, the game allows 65000." % len(verts))
    comp, edge_tris = components(tris)
    # open edges on the outline entrance lines = where guests come in
    n = len(outline_poly)
    ent_comps = set()
    for i, kd in enumerate(outline_kinds):
        if kd != "EXF":
            continue
        a, b = outline_poly[i], outline_poly[(i + 1) % n]
        for e, ts in edge_tris.items():
            if len(ts) != 1:
                continue
            p, q = verts[e[0]], verts[e[1]]
            if p[2] > 0.3 or q[2] > 0.3:
                continue
            L = math.hypot(q[0] - p[0], q[1] - p[1])
            k = max(1, int(L / 0.25))
            hits = sum(1 for j in range(k + 1)
                       if _seg_dist((p[0] + (q[0] - p[0]) * j / k, p[1] + (q[1] - p[1]) * j / k), a, b) < entrance_dist)
            if hits * L / k >= min(0.5, L * 0.9):
                ent_comps.add(comp[ts[0]])
    if not ent_comps:
        rep["errors"].append("No walkable ground touches an entrance edge of the outline.")
    sizes = defaultdict(int)
    for c in comp:
        sizes[c] += 1
    islands = [c for c in sizes if c not in ent_comps]
    if islands:
        rep["warnings"].append("%d walkable island(s) cannot be reached from an entrance (%d triangles)."
                               % (len(islands), sum(sizes[c] for c in islands)))
    tindex = TriIndex(verts, tris)
    for idx, st in enumerate(seats):
        if st.get("free"):
            continue
        ti = locate(st["target"], verts, tris, index=tindex)
        if ti is None:
            rep["bad_seats"].append((idx, "walk target is not on the navmesh"))
        elif comp[ti] not in ent_comps:
            rep["bad_seats"].append((idx, "walk target cannot be reached from an entrance"))
        else:
            rep["ok_seats"] += 1
    if rep["bad_seats"]:
        rep["errors"].append("%d seat(s) cannot be reached." % len(rep["bad_seats"]))
    # narrow passages: edges shared by two triangles that are very short and the only link of a region
    return rep
