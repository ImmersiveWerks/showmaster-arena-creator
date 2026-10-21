"""Reading and writing tribune objects in the Blender scene."""
import json
import math
import os
import re

import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector

from .core import geom

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

MATERIALS = {
    # name: (linear colour, roughness, metallic, double sided)
    "TB Concrete": ((0.19, 0.19, 0.19), 0.8, 0.0, False),
    "TB Steps": ((0.10, 0.10, 0.11), 0.8, 0.0, False),
    "TB Rail": ((0.03, 0.03, 0.03), 0.4, 1.0, False),
    "TB Seat": ((0.060, 0.132, 0.251), 0.5, 0.0, True),
    "TB Seat frame": ((0.055, 0.055, 0.055), 0.5, 1.0, False),
    "TB Rail infill": ((0.03, 0.03, 0.03), 0.4, 1.0, True),
}
NAV_MAT = "TB Navmesh (not exported)"
# default flexicolour channel of the built-in materials (0 = fixed colour)
FLEXI_AUTO = {"TB Seat": 1, "TB Rail": 2, "TB Rail infill": 2, "TB Concrete": 3, "TB Steps": 4}


def flexi_channel(mat, name=None):
    v = getattr(mat, "tb_flexi", 'AUTO') if mat is not None else 'AUTO'
    if v == 'AUTO':
        return FLEXI_AUTO.get(name or (mat.name if mat is not None else ""), 0)
    return int(v)


# ------------------------------------------------------------------ tribune collections


def active_tribune(context):
    coll = getattr(context.scene, "tb_active", None)
    if coll and coll.tb.enabled:
        return coll
    ob = context.active_object
    if ob:
        for c in bpy.data.collections:
            if c.tb.enabled and ob.name in c.all_objects:
                return c
    return None


def child_collection(parent, name):
    full = "%s %s" % (parent.name, name)
    for c in parent.children:
        if c.name == full or c.get("tb_child") == name:
            return c
    c = bpy.data.collections.new(full)
    c["tb_child"] = name
    parent.children.link(c)
    return c


def objects(coll, role=None):
    out = [o for o in coll.all_objects if role is None or o.tb_role == role]
    return out


def make_id(text):
    t = text.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        t = t.replace(a, b)
    t = re.sub(r"[^a-z0-9_]+", "_", t).strip("_")
    if not t or not t[0].isalpha():
        t = "tribune_" + t
    return t[:31]


def remove_objects(obs):
    meshes = []
    for o in obs:
        if o.type == 'MESH' and o.data and o.data.users <= 1:
            meshes.append(o.data)
        bpy.data.objects.remove(o, do_unlink=True)
    for m in meshes:
        if m.users == 0:
            bpy.data.meshes.remove(m)


def get_material(name):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    if name == NAV_MAT:
        col, rough, metal, double = (0.1, 0.8, 0.2), 1.0, 0.0, False
        m.diffuse_color = (0.1, 0.8, 0.2, 0.45)
        for attr, val in (("surface_render_method", 'BLENDED'), ("blend_method", 'BLEND')):
            try:
                setattr(m, attr, val)
                break
            except (AttributeError, TypeError):
                pass
    else:
        col, rough, metal, double = MATERIALS.get(name, ((0.5, 0.5, 0.5), 0.7, 0.0, False))
        m.diffuse_color = tuple(col) + (1.0,)
    bsdf = m.node_tree.nodes.get("Principled BSDF") if m.node_tree else None
    if bsdf:
        bsdf.inputs["Base Color"].default_value = tuple(col) + (1.0,)
        bsdf.inputs["Roughness"].default_value = rough
        bsdf.inputs["Metallic"].default_value = metal
        if name == NAV_MAT and "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = 0.45
    m.tb_double = double
    return m


def material_values(mat):
    """(linear rgb, roughness, metallic) of a Blender material"""
    col, rough, metal = tuple(mat.diffuse_color[:3]), 0.7, 0.0
    nt = getattr(mat, "node_tree", None)
    if mat.use_nodes and nt:
        for n in nt.nodes:
            if n.type == 'BSDF_PRINCIPLED':
                bc = n.inputs["Base Color"]
                if not bc.is_linked:
                    col = tuple(bc.default_value[:3])
                rough = float(n.inputs["Roughness"].default_value)
                metal = float(n.inputs["Metallic"].default_value)
                break
    return col, rough, metal


# ------------------------------------------------------------------ settings -> generator parameters


def room_data(ob):
    """Wall chain of a room mesh: the longest run of edges marked as sharp. Works in Edit Mode too."""
    import bmesh
    if ob is None or ob.type != 'MESH':
        raise geom.GenError("Choose the room object (a mesh).")
    me = ob.data
    own = ob.mode != 'EDIT'
    if own:
        bm = bmesh.new()
        bm.from_mesh(me)
    else:
        bm = bmesh.from_edit_mesh(me)
    try:
        bm.verts.index_update()
        M = ob.matrix_world
        if len(bm.faces):
            edges = [e for e in bm.edges if len(e.link_faces) == 1]
        else:
            edges = list(bm.edges)
        nb, flag = {}, {}
        for e in edges:
            a, b = e.verts[0].index, e.verts[1].index
            nb.setdefault(a, []).append(b)
            nb.setdefault(b, []).append(a)
            flag[frozenset((a, b))] = not e.smooth
        co = {}
        for v in bm.verts:
            w = M @ v.co
            co[v.index] = (w.x, w.y)
    finally:
        if own:
            bm.free()
    if not nb or any(len(x) != 2 for x in nb.values()):
        raise geom.GenError("The room must be one closed outline (a face or a closed loop of edges).")
    start = min(nb)
    order, prev, cur = [start], None, start
    while True:
        nxt = [x for x in nb[cur] if x != prev]
        if not nxt or nxt[0] == start:
            break
        order.append(nxt[0])
        prev, cur = cur, nxt[0]
        if len(order) > len(nb):
            break
    if len(order) != len(nb):
        raise geom.GenError("The room must be one closed outline (a face or a closed loop of edges).")
    poly = [co[i] for i in order]
    n = len(poly)
    marked = [flag[frozenset((order[i], order[(i + 1) % n]))] for i in range(n)]
    area = sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1] for i in range(n))
    if area < 0:        # counter-clockwise from above
        poly = poly[::-1]
        marked = [marked[(n - 2 - i) % n] for i in range(n)]
    if not any(marked):
        raise geom.GenError("Mark the walls for the tribune: select their edges in Edit Mode and press "
                            "'Mark as tribune wall' (or Edge > Mark Sharp).")
    if all(marked):
        raise geom.GenError("Leave at least one wall unmarked.")
    # longest run of marked edges (cyclic)
    best, start_i = None, None
    for i in range(n):
        if marked[i] and not marked[(i - 1) % n]:
            j, ln = i, 0.0
            while marked[j % n]:
                a, b = poly[j % n], poly[(j + 1) % n]
                ln += math.hypot(b[0] - a[0], b[1] - a[1])
                j += 1
            if best is None or ln > best[0]:
                best = (ln, i, j)
    _ln, i0, i1 = best
    pts = [poly[k % n] for k in range(i0, i1 + 1)]
    chain = pts[::-1]           # the room is on the right side of this direction

    def unit(p, q):
        dx, dy = q[0] - p[0], q[1] - p[1]
        l = math.hypot(dx, dy)
        return (dx / l, dy / l) if l > 1e-9 else None
    start_in = unit(poly[i1 % n], poly[(i1 + 1) % n])
    end_in = unit(poly[i0 % n], poly[(i0 - 1) % n])
    return {"chain": chain, "start_in": start_in, "end_in": end_in, "poly": poly}


def gen_params(s):
    segs = []
    for seg in s.segments:
        if seg.kind == 'ARC':
            segs.append({"kind": "arc", "radius": seg.radius, "angle": seg.angle, "turn": seg.turn})
        else:
            segs.append({"kind": "straight", "length": seg.length, "turn": seg.turn})
    custom = []
    for part in (s.aisle_custom or "").replace(";", ",").split(","):
        part = part.strip().replace(" ", "")
        if part:
            try:
                custom.append(float(part))
            except ValueError:
                raise geom.GenError("Extra stairs: '%s' is not a number." % part)
    room = None
    if s.footprint == 'ROOM':
        room = room_data(s.room_object)
    return dict(
        room=room, staff_path=s.staff_path, segments=segs, rows=s.rows, row_depth=s.row_depth, first_row_depth=s.first_row_depth, row_rise=s.row_rise, first_row_height=s.first_row_height,
        seat_gap=s.seat_gap, seat_height=s.seat_height, seat_back_gap=s.seat_back_gap, clearance=s.clearance,
        aisle_width=s.aisle_width, aisle_left=s.aisle_left, aisle_right=s.aisle_right,
        aisle_center_count=s.aisle_center_count, aisle_corners=s.aisle_corners, aisle_custom=custom,
        corner_threshold=s.corner_threshold, stage_depth=s.stage_depth, front_walk=s.front_walk,
        side_walk=s.side_walk, back_walk=s.back_walk, entrance_left=s.entrance_left, entrance_right=s.entrance_right,
        entrance_front=s.entrance_front, entrance_back=s.entrance_back, entrance_length=s.entrance_length,
        booth=s.booth, rail_back=s.rail_back, rail_sides=s.rail_sides, rail_front=s.rail_front, front_path=s.front_path, access_left=s.access_left, access_right=s.access_right, access_width=s.access_width, access_slope=s.access_slope / 100.0, stair_bottom=[st.bottom for st in s.stairs], rail_height=s.rail_height,
        rail_post_spacing=s.rail_post_spacing, rail_hand=s.rail_hand, rail_post_size=s.rail_post_size,
        rail_mid=s.rail_mid, rail_mid_size=s.rail_mid_size, rail_mid_height=s.rail_mid_height, rail_infill=s.rail_infill,
        rail_infill_spacing=s.rail_infill_spacing, rail_infill_width=s.rail_infill_width,
        rail_infill_bottom=s.rail_infill_bottom, rail_infill_top=s.rail_infill_top, arc_step=s.arc_step)


# ------------------------------------------------------------------ seat model


def seat_template(s, context):
    """Seat geometry (centred in XY, origin on the floor, looking to -Y).
    Returns dict: parts [(material, verts np(n,3), faces, smooth flags)], sit, width, depth, bottom"""
    if s.seat_source == 'OBJECT':
        ob = s.seat_object
        if ob is None or ob.type != 'MESH':
            raise geom.GenError("Choose a seat object (mesh) or use the built-in seat.")
        dg = context.evaluated_depsgraph_get()
        oe = ob.evaluated_get(dg)
        me = oe.to_mesh()
        try:
            co = np.empty(len(me.vertices) * 3)
            me.vertices.foreach_get("co", co)
            co = co.reshape(-1, 3)
            # keep the object's scale/rotation, not its location
            M = np.array(ob.matrix_world.to_3x3())
            co = co @ M.T
            mats = [sl.material for sl in oe.material_slots] or [None]
            by_mat = {}
            for p in me.polygons:
                by_mat.setdefault(min(p.material_index, len(mats) - 1), []).append((tuple(p.vertices), p.use_smooth))
            parts = []
            for mi, polys in by_mat.items():
                mat = mats[mi]
                parts.append((mat.name if mat else "TB Seat", co, [p[0] for p in polys], [p[1] for p in polys]))
        finally:
            oe.to_mesh_clear()
        if len(co) == 0:
            raise geom.GenError("The seat object has no geometry.")
        lo, hi = co.min(0), co.max(0)
        shift = np.array([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, 0.0])
        parts = [(n, c + shift, f, sm) for n, c, f, sm in parts]
        pts = [tuple(p) for p in co + shift]
        from .core import custom
        d = custom.seat_from_points(pts, (0.0, -1.0))
        return {"parts": parts, "sit": (0.0, d["sit"][1], d["sit"][2]), "width": hi[0] - lo[0], "depth": hi[1] - lo[1],
                "bottom": lo[2], "back": d["back"], "front": d["front"], "half_w": d["half_w"]}
    with open(os.path.join(DATA, "placeholder_seat.json"), encoding="utf-8") as f:
        js = json.load(f)
    parts = []
    allv = []
    for p in js["parts"]:
        v = np.array(p["verts"], dtype=float)
        allv.append(v)
        parts.append((p["material"], v, [tuple(t) for t in p["tris"]], [True] * len(p["tris"]) if p["material"] == "TB Seat"
                      else [False] * len(p["tris"])))
    allv = np.concatenate(allv)
    shell = np.array(js["parts"][0]["verts"])
    lo, hi = allv.min(0), allv.max(0)
    sit = js["sit"]
    return {"parts": parts, "sit": tuple(sit), "width": hi[0] - lo[0], "depth": hi[1] - lo[1],
            "bottom": float(shell[:, 2].min()), "back": hi[1] - sit[1], "front": sit[1] - lo[1], "half_w": (hi[0] - lo[0]) / 2}


# ------------------------------------------------------------------ building objects


def new_mesh_object(name, coll, verts, faces, mats=None, mat_idx=None, smooth=None, edges=()):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], list(edges), [tuple(f) for f in faces])
    me.validate(clean_customdata=False)
    if mats:
        for m in mats:
            me.materials.append(m)
    if mat_idx is not None and len(me.polygons) == len(mat_idx):
        me.polygons.foreach_set("material_index", list(mat_idx))
    if smooth is not None and len(me.polygons) == len(smooth):
        me.polygons.foreach_set("use_smooth", [bool(x) for x in smooth])
    me.update()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def seat_matrix(sit, yaw):
    return Matrix.LocRotScale(Vector(sit), Euler((math.pi / 2, 0.0, yaw)), None)


def make_seat_empty(coll, name, sit, yaw, target, row, order, free=False, dims=None, floor=0.0, generated=False):
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = 'SINGLE_ARROW'
    e.empty_display_size = 0.45 if not free else 0.2
    e.location = Vector(sit)
    e.rotation_euler = Euler((math.pi / 2, 0.0, yaw))
    e.tb_role = 'SEAT'
    e.tb_row, e.tb_order, e.tb_free = int(row), int(order), bool(free)
    e.tb_floor = float(floor)
    e.tb_generated = generated
    if dims:
        e.tb_back, e.tb_front, e.tb_halfw = dims
    coll.objects.link(e)
    t = bpy.data.objects.new(name + " target", None)
    t.empty_display_type = 'SPHERE'
    t.empty_display_size = 0.08
    t.tb_role = 'TARGET'
    t.tb_generated = generated
    t.parent = e
    t.matrix_parent_inverse = Matrix.Identity(4)
    t.location = seat_matrix(sit, yaw).inverted() @ Vector(target)
    coll.objects.link(t)
    return e, t


def seat_facing(e):
    v = e.matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0))
    l = math.hypot(v.x, v.y)
    return (v.x / l, v.y / l) if l > 1e-9 else (0.0, -1.0)


def seat_target(e):
    for c in e.children:
        if c.tb_role == 'TARGET':
            return tuple(c.matrix_world.translation)
    return None


def outline_object(coll, poly, kinds, name="Outline", generated=True):
    verts = [(p[0], p[1], 0.03) for p in poly]
    n = len(verts)
    edges = [(i, (i + 1) % n) for i in range(n)]
    ob = new_mesh_object(name, coll, verts, [], edges=edges)
    for i, e in enumerate(ob.data.edges):
        e.use_seam = kinds[i] == "EXF"
    ob.tb_role = 'OUTLINE'
    ob.tb_generated = generated
    ob.show_wire = True
    ob.show_in_front = True
    ob.hide_render = True
    return ob


def nav_object(coll, verts, tris, name="Navmesh", generated=True):
    ob = new_mesh_object(name, coll, verts, tris, mats=[get_material(NAV_MAT)])
    ob.tb_role = 'NAV'
    ob.tb_generated = generated
    ob.show_wire = True
    ob.color = (0.1, 0.8, 0.2, 0.5)
    ob.hide_render = True
    return ob


def booth_object(coll, loc, generated=True):
    b = bpy.data.objects.new("Ride booth", None)
    b.empty_display_type = 'CUBE'
    b.empty_display_size = 0.75
    b.location = Vector((loc[0], loc[1], 0.75))
    b.tb_role = 'BOOTH'
    b.tb_generated = generated
    coll.objects.link(b)
    return b


def set_mesh(coll, key, verts, faces, edges=(), mats=None, mat_idx=None, smooth=None):
    """Creates the generated mesh object 'key' or replaces its geometry in place (fast, keeps the object)."""
    ob = next((o for o in coll.all_objects if o.tb_generated and o.get("tb_part") == key and o.type == 'MESH'), None)
    if ob is None:
        ob = new_mesh_object(key, coll, verts, faces, mats=mats, mat_idx=mat_idx, smooth=smooth, edges=edges)
        ob["tb_part"] = key
        ob.tb_generated = True
        return ob, True
    me = ob.data
    me.clear_geometry()
    me.from_pydata([tuple(v) for v in verts], list(edges), [tuple(x) for x in faces])
    me.validate(clean_customdata=False)
    if mats is not None:
        me.materials.clear()
        for m in mats:
            me.materials.append(m)
    if mat_idx is not None and len(me.polygons) == len(mat_idx):
        me.polygons.foreach_set("material_index", list(mat_idx))
    if smooth is not None and len(me.polygons) == len(smooth):
        me.polygons.foreach_set("use_smooth", [bool(x) for x in smooth])
    me.update()
    return ob, False


def _seat_mesh(res, tmpl):
    tmpl = geom.seat_template_for(tmpl, res.get("params"))
    mat_names = []
    for name, _v, _f, _sm in tmpl["parts"]:
        if name not in mat_names:
            mat_names.append(name)
    mats = [bpy.data.materials.get(n) or get_material(n) for n in mat_names]
    V, F, MI, SM = [], [], [], []
    base = 0
    for seat in res["seats"]:
        c, sn = math.cos(seat["yaw"]), math.sin(seat["yaw"])
        R = np.array([[c, -sn, 0.0], [sn, c, 0.0], [0.0, 0.0, 1.0]])
        org = np.array(seat["origin"])
        for name, verts, faces, smooth in tmpl["parts"]:
            P = verts @ R.T + org
            V.extend(map(tuple, P))
            F.extend(tuple(base + i for i in f) for f in faces)
            MI.extend([mat_names.index(name)] * len(faces))
            SM.extend(smooth)
            base += len(P)
    return V, F, mats, MI, SM


def _marker(coll, role, name, loc, display, size):
    ob = next((o for o in coll.all_objects if o.tb_generated and o.tb_role == role), None)
    if ob is None:
        ob = bpy.data.objects.new(name, None)
        ob.empty_display_type = display
        ob.empty_display_size = size
        ob.tb_role = role
        ob.tb_generated = True
        coll.objects.link(ob)
    ob.location = Vector(loc)
    return ob


def sync_stairs(coll, res):
    """the stair list in the panel follows the generated stairs; the choices are kept by position"""
    info = (res.get("info") or {}).get("stairs") or []
    lst = coll.tb.stairs
    try:
        while len(lst) > len(info):
            lst.remove(len(lst) - 1)
        while len(lst) < len(info):
            lst.add()
        for item, st in zip(lst, info):
            if item.pos != st["pos"]:
                item.pos = st["pos"]
            if item.forced != bool(st["forced"]):
                item.forced = bool(st["forced"])
    except Exception:
        pass        # not allowed in some drawing contexts; the next generate does it


def build_generated(context, coll, res, tmpl, preview=False):
    """Creates or updates all objects of a generated tribune.
    preview=True: only meshes (fast, for the live view); the seat points are shown as lines."""
    sync_stairs(coll, res)
    st = res["structure"]
    m0, m1, m2 = get_material("TB Concrete"), get_material("TB Steps"), get_material("TB Rail")
    set_mesh(coll, "Structure", st["verts"], st["faces"], mats=[m0, m1], mat_idx=st["mat"])
    set_mesh(coll, "Railings", res["rail"]["verts"], res["rail"]["faces"], mats=[m2, get_material("TB Rail infill")],
             mat_idx=res["rail"].get("mat"))
    V, F, mats, MI, SM = _seat_mesh(res, tmpl)
    so, _new = set_mesh(coll, "Seats", V, F, mats=mats, mat_idx=MI, smooth=SM)
    so.tb_seatmesh = True
    nav, new = set_mesh(coll, "Navmesh", res["nav"]["verts"], res["nav"]["tris"], mats=[get_material(NAV_MAT)])
    if new:
        nav.tb_role = 'NAV'
        nav.show_wire = True
        nav.hide_render = True
    poly = res["outline"]["poly"]
    n = len(poly)
    ol, new = set_mesh(coll, "Outline", [(p[0], p[1], 0.03) for p in poly], [], edges=[(i, (i + 1) % n) for i in range(n)])
    for i, e in enumerate(ol.data.edges):
        e.use_seam = res["outline"]["kinds"][i] == "EXF"
    if new:
        ol.tb_role = 'OUTLINE'
        ol.show_wire = True
        ol.show_in_front = True
        ol.hide_render = True
    b = res["booth"]
    _marker(coll, 'BOOTH', "Ride booth", (b[0], b[1], 0.75), 'CUBE', 0.75)
    _marker(coll, 'STAGE', "Stage point", res["stage"], 'PLAIN_AXES', 1.0)
    old = [o for o in coll.all_objects if o.tb_generated and o.tb_role in ('SEAT', 'TARGET')]
    remove_objects(old)
    if preview:
        # sit points as short lines towards the walk targets
        LV, LE = [], []
        for seat in res["seats"]:
            LV.append(seat["sit"])
            LV.append(seat["target"])
            LE.append((len(LV) - 2, len(LV) - 1))
        ln, new = set_mesh(coll, "Seat lines (preview)", LV, [], edges=LE)
        if new:
            ln.tb_role = 'IGNORE'
            ln.show_in_front = True
            ln.hide_render = True
        return
    remove_objects([o for o in coll.all_objects if o.tb_generated and o.get("tb_part") == "Seat lines (preview)"])
    sc = child_collection(coll, "Seat points")
    dims = (tmpl["back"], tmpl["front"], tmpl["half_w"])
    for seat in res["seats"]:
        make_seat_empty(sc, "Seat %02d-%03d" % (seat["row"], seat["order"]), seat["sit"], seat["yaw"], seat["target"],
                        seat["row"], seat["order"], seat["free"], dims, seat["origin"][2], generated=True)


# ------------------------------------------------------------------ reading a tribune for export / checks


def outline_data(coll):
    obs = objects(coll, 'OUTLINE')
    if not obs:
        return None, None
    ob = obs[0]
    me = ob.data
    M = ob.matrix_world
    nb = {}
    seam = {}
    for e in me.edges:
        a, b = e.vertices
        nb.setdefault(a, []).append(b)
        nb.setdefault(b, []).append(a)
        seam[frozenset((a, b))] = e.use_seam
    if not nb:
        return None, None
    if any(len(v) != 2 for v in nb.values()):
        raise ValueError("The outline must be one closed loop of edges (every point with exactly two edges).")
    start = min(nb)
    order = [start]
    prev, cur = None, start
    while True:
        nxt = [x for x in nb[cur] if x != prev]
        if not nxt:
            break
        n = nxt[0]
        if n == start:
            break
        order.append(n)
        prev, cur = cur, n
        if len(order) > len(nb):
            break
    if len(order) != len(nb):
        raise ValueError("The outline must be one closed loop of edges.")
    poly = []
    for i in order:
        w = M @ me.vertices[i].co
        poly.append((w.x, w.y))
    kinds = ["EXF" if seam[frozenset((order[i], order[(i + 1) % len(order)]))] else "FON" for i in range(len(order))]
    # counter-clockwise
    area = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly)))
    if area < 0:
        n = len(poly)
        poly = poly[::-1]
        kinds = [kinds[(n - 2 - i) % n] for i in range(n)]
    return poly, kinds


def mesh_tris_world(ob, depsgraph):
    oe = ob.evaluated_get(depsgraph)
    me = oe.to_mesh()
    try:
        me.calc_loop_triangles()
        nt = len(me.loop_triangles)
        nv = len(me.vertices)
        co = np.empty(nv * 3)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        tv = np.empty(nt * 3, dtype=np.int64)
        me.loop_triangles.foreach_get("vertices", tv)
        tv = tv.reshape(-1, 3)
    finally:
        oe.to_mesh_clear()
    M = np.array(ob.matrix_world)
    W = co @ M[:3, :3].T + M[:3, 3]
    if np.linalg.det(M[:3, :3]) < 0:
        tv = tv[:, [0, 2, 1]]
    return W, tv


def nav_data(coll, depsgraph):
    obs = objects(coll, 'NAV')
    if not obs:
        return None, None
    V, T = [], []
    for ob in obs:
        W, tv = mesh_tris_world(ob, depsgraph)
        if len(tv):
            # every triangle must face up (the game ignores the others)
            A, B, C = W[tv[:, 0]], W[tv[:, 1]], W[tv[:, 2]]
            nz = (B[:, 0] - A[:, 0]) * (C[:, 1] - A[:, 1]) - (B[:, 1] - A[:, 1]) * (C[:, 0] - A[:, 0])
            tv = np.where((nz < 0)[:, None], tv[:, [0, 2, 1]], tv)
        base = len(V)
        V.extend(map(tuple, W.tolist()))
        T.extend(tuple(int(i) + base for i in t) for t in tv)
    return V, T


def seat_data(coll):
    seats = []
    for e in objects(coll, 'SEAT'):
        f = seat_facing(e)
        tgt = seat_target(e)
        sit = tuple(e.matrix_world.translation)
        seats.append({"name": e.name, "obj": e, "sit": sit, "yaw": math.atan2(f[0], -f[1]), "facing": f,
                      "target": tgt, "row": e.tb_row, "order": e.tb_order, "free": e.tb_free,
                      "back": e.tb_back, "front": e.tb_front, "half_w": e.tb_halfw, "floor": e.tb_floor})
    return seats


def _hidden(o):
    try:
        return o.hide_get()
    except RuntimeError:
        return True     # not in the view layer (excluded collection)


def model_objects(coll):
    return [o for o in coll.all_objects
            if o.type in ('MESH', 'CURVE', 'SURFACE', 'META', 'FONT') and o.tb_role == 'NONE' and not _hidden(o)]


def show(o, select=True):
    try:
        o.hide_set(False)
        o.select_set(select)
        return True
    except RuntimeError:
        return False


# materials that get the surface patterns, and the size of one seat texture tile
SURFACE_GROUP = {"TB Concrete": "floor", "TB Steps": "floor", "TB Seat": "seat"}
SEAT_TILE = 0.5


def model_parts(coll, depsgraph, floor_tile=None, seat_tile=SEAT_TILE):
    """Visible model, grouped by material: [(material name, verts, normals, uvs, tris)], materials info, bounds.
    floor_tile: box-mapped UVs for the pattern materials (one tile per floor_tile metres)"""
    groups = {}
    mats = {}
    lo, hi = None, None
    for ob in model_objects(coll):
        oe = ob.evaluated_get(depsgraph)
        try:
            me = oe.to_mesh()
        except RuntimeError:
            continue
        if me is None:
            continue
        try:
            me.calc_loop_triangles()
            nt = len(me.loop_triangles)
            if nt == 0:
                continue
            nl = len(me.loops)
            co = np.empty(len(me.vertices) * 3)
            me.vertices.foreach_get("co", co)
            co = co.reshape(-1, 3)
            lt = np.empty(nt * 3, dtype=np.int64)
            me.loop_triangles.foreach_get("loops", lt)
            mi = np.empty(nt, dtype=np.int64)
            me.loop_triangles.foreach_get("material_index", mi)
            vidx = np.empty(nl, dtype=np.int64)
            me.loops.foreach_get("vertex_index", vidx)
            cn = np.empty(nl * 3)
            if hasattr(me, "corner_normals"):
                me.corner_normals.foreach_get("vector", cn)
            else:
                me.calc_normals_split()
                me.loops.foreach_get("normal", cn)
            cn = cn.reshape(-1, 3)
            uv = np.zeros((nl, 2))
            if me.uv_layers.active:
                u = np.empty(nl * 2)
                me.uv_layers.active.data.foreach_get("uv", u)
                uv = u.reshape(-1, 2)
            slots = [sl.material for sl in oe.material_slots]
        finally:
            oe.to_mesh_clear()
        M = np.array(ob.matrix_world)
        R = M[:3, :3]
        N = np.linalg.inv(R).T
        flip = np.linalg.det(R) < 0
        W = co @ R.T + M[:3, 3]
        lo = W.min(0) if lo is None else np.minimum(lo, W.min(0))
        hi = W.max(0) if hi is None else np.maximum(hi, W.max(0))
        lt = lt.reshape(-1, 3)
        if flip:
            lt = lt[:, [0, 2, 1]]
        for m in np.unique(mi):
            mat = slots[m] if 0 <= m < len(slots) else None
            name = mat.name if mat else "TB Concrete"
            if name not in mats:
                if mat:
                    col, rough, metal = material_values(mat)
                    mats[name] = {"color": col, "roughness": rough, "metal": metal, "double": bool(mat.tb_double),
                                  "flexi": flexi_channel(mat)}
                else:
                    c, r, mt, d = MATERIALS["TB Concrete"]
                    mats[name] = {"color": c, "roughness": r, "metal": mt, "double": d,
                                  "flexi": flexi_channel(None, "TB Concrete")}
                if name in SURFACE_GROUP:
                    mats[name]["surface"] = SURFACE_GROUP[name]
            loops = lt[mi == m].reshape(-1)
            P = W[vidx[loops]]
            Nn = cn[loops] @ N.T
            Nn /= np.maximum(np.linalg.norm(Nn, axis=1, keepdims=True), 1e-12)
            U = uv[loops]
            grp = SURFACE_GROUP.get(name)
            if floor_tile and grp:
                from .core.textures import box_uv
                size = floor_tile if grp == "floor" else (seat_tile or SEAT_TILE)
                Pt = P.reshape(-1, 3, 3)
                fn = np.cross(Pt[:, 1] - Pt[:, 0], Pt[:, 2] - Pt[:, 0])
                fn = np.repeat(fn, 3, axis=0)
                U = np.array([box_uv(p, n, size) for p, n in zip(P, fn)], float).reshape(-1, 2)
            groups.setdefault(name, []).append((P, Nn, U))
    parts = []
    for name, lst in groups.items():
        P = np.concatenate([x[0] for x in lst])
        Nn = np.concatenate([x[1] for x in lst])
        U = np.concatenate([x[2] for x in lst])
        key = np.round(np.hstack([P, Nn * 0.5, U]), 4)
        uniq, inv = np.unique(key, axis=0, return_index=False, return_inverse=True)
        inv = inv.reshape(-1)
        first = np.zeros(len(uniq), dtype=np.int64)
        first[inv[::-1]] = np.arange(len(inv))[::-1]
        V = P[first]
        NN = Nn[first]
        UU = U[first]
        T = inv.reshape(-1, 3)
        T = T[(T[:, 0] != T[:, 1]) & (T[:, 1] != T[:, 2]) & (T[:, 0] != T[:, 2])]
        parts.append((name, V.tolist(), NN.tolist(), UU.tolist(), [tuple(int(i) for i in t) for t in T]))
    bounds = None if lo is None else (lo.tolist(), hi.tolist())
    return parts, mats, bounds
