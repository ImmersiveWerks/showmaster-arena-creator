"""Generator result -> model parts for the game (without Blender). Used by the standalone app.

Matches what the add-on exports from the Blender scene: same material names, flat shading for the
structure and railings, smooth seat shells, box-mapped UVs for the surface patterns.
"""
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")

MATERIALS = {
    # name: (linear colour, roughness, metallic, double sided)
    "TB Concrete": ((0.19, 0.19, 0.19), 0.8, 0.0, False),
    "TB Steps": ((0.10, 0.10, 0.11), 0.8, 0.0, False),
    "TB Rail": ((0.03, 0.03, 0.03), 0.4, 1.0, False),
    "TB Seat": ((0.060, 0.132, 0.251), 0.5, 0.0, True),
    "TB Seat frame": ((0.055, 0.055, 0.055), 0.5, 1.0, False),
    "TB Rail infill": ((0.03, 0.03, 0.03), 0.4, 1.0, True),
}
FLEXI_AUTO = {"TB Seat": 1, "TB Rail": 2, "TB Rail infill": 2, "TB Concrete": 3, "TB Steps": 4}
SURFACE_GROUP = {"TB Concrete": "floor", "TB Steps": "floor", "TB Seat": "seat"}
SEAT_TILE = 0.5


def seat_template():
    """the built-in seat: parts [(material, verts (n,3), tris, smooth)], sit, width, depth, bottom"""
    import numpy as np
    with open(os.path.join(DATA, "placeholder_seat.json"), encoding="utf-8") as f:
        js = json.load(f)
    parts, allv = [], []
    for p in js["parts"]:
        v = np.array(p["verts"], dtype=float)
        allv.append(v)
        parts.append((p["material"], v, [tuple(t) for t in p["tris"]], p["material"] == "TB Seat"))
    allv = np.concatenate(allv)
    shell = np.array(js["parts"][0]["verts"])
    lo, hi = allv.min(0), allv.max(0)
    sit = js["sit"]
    return {"parts": parts, "sit": tuple(sit), "width": float(hi[0] - lo[0]), "depth": float(hi[1] - lo[1]),
            "bottom": float(shell[:, 2].min()), "back": float(hi[1] - sit[1]), "front": float(sit[1] - lo[1]),
            "half_w": float((hi[0] - lo[0]) / 2)}


def _poly_tris(P):
    """triangles of one planar polygon (3D points), keeping the winding"""
    from .geom import _triangulate
    n = len(P)
    if n == 3:
        return [(0, 1, 2)]
    if n == 4:
        return [(0, 1, 2), (0, 2, 3)] if _convex(P) else _tri_proj(P, _triangulate)
    return _tri_proj(P, _triangulate)


def _normal(P):
    nx = ny = nz = 0.0
    for i in range(len(P)):
        a, b = P[i], P[(i + 1) % len(P)]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    l = math.sqrt(nx * nx + ny * ny + nz * nz)
    return (nx / l, ny / l, nz / l) if l > 1e-12 else (0.0, 0.0, 1.0)


def _convex(P):
    n = _normal(P)
    sgn = 0
    for i in range(len(P)):
        a, b, c = P[i - 1], P[i], P[(i + 1) % len(P)]
        u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        v = (c[0] - b[0], c[1] - b[1], c[2] - b[2])
        cr = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        d = cr[0] * n[0] + cr[1] * n[1] + cr[2] * n[2]
        if abs(d) < 1e-12:
            continue
        s = 1 if d > 0 else -1
        if sgn and s != sgn:
            return False
        sgn = s
    return True


def _tri_proj(P, tri):
    n = _normal(P)
    ax = max(range(3), key=lambda i: abs(n[i]))
    i0, i1 = [(1, 2), (2, 0), (0, 1)][ax]
    Q = [(p[i0], p[i1]) for p in P]
    out = tri(Q)          # counter-clockwise in the projection
    flip = n[ax] < 0
    return [(a, c, b) if flip else (a, b, c) for a, b, c in out]


def _flat(verts, faces, mats, names):
    """polygon mesh -> {material: [(p, n)] corner list (triangles)}"""
    out = {}
    for f, m in zip(faces, mats if mats is not None else [0] * len(faces)):
        P = [tuple(verts[i]) for i in f]
        if len(P) < 3:
            continue
        n = _normal(P)
        lst = out.setdefault(names[min(int(m), len(names) - 1)], [])
        for a, b, c in _poly_tris(P):
            lst.extend(((P[a], n), (P[b], n), (P[c], n)))
    return out


def _weld(corners_p, corners_n, uv):
    """corner arrays -> unique vertices + triangle indices"""
    import numpy as np
    P = np.asarray(corners_p, float)
    N = np.asarray(corners_n, float)
    U = np.asarray(uv, float)
    key = np.round(np.hstack([P, N * 0.5, U]), 4)
    uniq, inv = np.unique(key, axis=0, return_inverse=True)
    inv = inv.reshape(-1)
    first = np.zeros(len(uniq), dtype=np.int64)
    first[inv[::-1]] = np.arange(len(inv))[::-1]
    T = inv.reshape(-1, 3)
    T = T[(T[:, 0] != T[:, 1]) & (T[:, 1] != T[:, 2]) & (T[:, 0] != T[:, 2])]
    return P[first], N[first], U[first], T


def _box_uvs(P, Fn, size):
    s = 1.0 / max(1e-6, size)
    import numpy as np
    A = np.abs(Fn)
    U = np.zeros((len(P), 2))
    z = (A[:, 2] >= A[:, 0]) & (A[:, 2] >= A[:, 1])
    x = ~z & (A[:, 0] >= A[:, 1])
    y = ~z & ~x
    U[z] = P[z][:, [0, 1]] * s
    U[x] = P[x][:, [1, 2]] * s
    U[y] = P[y][:, [0, 2]] * s
    return U


def seat_instances(res, tmpl):
    """all seats as one corner soup per material: {material: (P (n,3), N (n,3))}"""
    import numpy as np
    from .geom import seat_template_for
    tmpl = seat_template_for(tmpl, res.get("params"))
    out = {}
    for name, V, T, smooth in tmpl["parts"]:
        T = np.asarray(T, int)
        A, B, C = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
        fn = np.cross(B - A, C - A)
        if smooth:
            vn = np.zeros_like(V)
            for k in range(3):
                np.add.at(vn, T[:, k], fn)
            vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
            CN = vn[T.reshape(-1)]
        else:
            fl = fn / np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
            CN = np.repeat(fl, 3, axis=0)
        CP = V[T.reshape(-1)]
        Ps, Ns = [], []
        for seat in res["seats"]:
            c, sn = math.cos(seat["yaw"]), math.sin(seat["yaw"])
            R = np.array([[c, -sn, 0.0], [sn, c, 0.0], [0.0, 0.0, 1.0]])
            Ps.append(CP @ R.T + np.array(seat["origin"]))
            Ns.append(CN @ R.T)
        if Ps:
            out[name] = (np.concatenate(Ps), np.concatenate(Ns))
    return out


def model_parts(res, tmpl, floor_tile=0.6, seat_tile=SEAT_TILE):
    """[(material, verts, normals, uvs, tris)] and bounds, like the add-on's export"""
    import numpy as np
    groups = {}
    st = res["structure"]
    for name, lst in _flat(st["verts"], st["faces"], st.get("mat"), ["TB Concrete", "TB Steps"]).items():
        groups.setdefault(name, []).append((np.array([c[0] for c in lst]), np.array([c[1] for c in lst])))
    rl = res["rail"]
    for name, lst in _flat(rl["verts"], rl["faces"], rl.get("mat"), ["TB Rail", "TB Rail infill"]).items():
        groups.setdefault(name, []).append((np.array([c[0] for c in lst]), np.array([c[1] for c in lst])))
    for name, (P, N) in seat_instances(res, tmpl).items():
        groups.setdefault(name, []).append((P, N))
    parts = []
    lo = hi = None
    for name, lst in groups.items():
        P = np.concatenate([x[0] for x in lst])
        N = np.concatenate([x[1] for x in lst])
        if not len(P):
            continue
        grp = SURFACE_GROUP.get(name)
        if grp:
            Pt = P.reshape(-1, 3, 3)
            fn = np.repeat(np.cross(Pt[:, 1] - Pt[:, 0], Pt[:, 2] - Pt[:, 0]), 3, axis=0)
            U = _box_uvs(P, fn, floor_tile if grp == "floor" else seat_tile)
        else:
            U = np.zeros((len(P), 2))
        V, NN, UU, T = _weld(P, N, U)
        lo = V.min(0) if lo is None else np.minimum(lo, V.min(0))
        hi = V.max(0) if hi is None else np.maximum(hi, V.max(0))
        parts.append((name, V.tolist(), NN.tolist(), UU.tolist(), [tuple(int(i) for i in t) for t in T]))
    bounds = None if lo is None else (lo.tolist(), hi.tolist())
    return parts, bounds


def materials(colors=None, flexi=None):
    """material info for gamebuild. colors: {name: (r, g, b) linear}, flexi: {name: 0..4 or "AUTO"}"""
    out = {}
    for name, (c, r, m, d) in MATERIALS.items():
        ch = (flexi or {}).get(name, "AUTO")
        ch = FLEXI_AUTO.get(name, 0) if ch in (None, "AUTO") else int(ch)
        out[name] = {"color": tuple((colors or {}).get(name, c)), "roughness": r, "metal": m, "double": d, "flexi": ch}
        if name in SURFACE_GROUP:
            out[name]["surface"] = SURFACE_GROUP[name]
    return out
