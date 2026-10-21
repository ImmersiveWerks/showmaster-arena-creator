import math
import os
import uuid
import traceback

import bpy
import numpy as np
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import live
from . import scene as S
from .core import custom, geom, navcheck
from .props import prefs


def tr(msg):
    try:
        return bpy.app.translations.pgettext_rpt(msg)
    except Exception:
        return msg


def need_tribune(op, context):
    coll = S.active_tribune(context)
    if coll is None:
        op.report({'ERROR'}, tr("Create or choose a tribune first."))
    return coll


def set_report(context, lines):
    context.scene.tb_report = "\n".join(lines)


def error_report(op, context, exc):
    op.report({'ERROR'}, str(exc))
    if not isinstance(exc, (geom.GenError, ValueError)):
        print(traceback.format_exc())
        set_report(context, [tr("Error:") + " " + str(exc), tr("Details are in the system console (Window > Toggle System Console).")])


# ------------------------------------------------------------------ tribunes


class TB_OT_new(bpy.types.Operator):
    bl_idname = "tb.new"
    bl_label = "New tribune"
    bl_description = "Creates a new tribune collection"
    bl_options = {'REGISTER', 'UNDO'}

    mode: EnumProperty(items=[('GENERATED', "Generator", ""), ('CUSTOM', "Own model", "")], default='GENERATED')

    def execute(self, context):
        n = 1
        while bpy.data.collections.get("Tribune %d" % n):
            n += 1
        coll = bpy.data.collections.new("Tribune %d" % n)
        context.scene.collection.children.link(coll)
        s = coll.tb
        s.enabled = True
        s.mode = self.mode
        # the ID must not exist yet, neither in this file nor in the library (other .blend files)
        try:
            lib = bpy.path.abspath(prefs(context).library_dir)
            taken = set(os.listdir(lib)) if os.path.isdir(lib) else set()
        except Exception:
            taken = set()
        taken |= {c.tb.tid for c in bpy.data.collections if c.tb.enabled}
        k = n
        while S.make_id("tribune_%d" % k) in taken:
            k += 1
        s.game_name = "Tribune %d" % k
        s.tid = S.make_id("tribune_%d" % k)
        s.uid = uuid.uuid4().hex
        if self.mode == 'GENERATED':
            seg = s.segments.add()
            seg.kind, seg.length = 'STRAIGHT', 16.0
        else:
            moved = 0
            for ob in context.selected_objects:
                if ob.name in coll.all_objects:
                    continue
                for c in list(ob.users_collection):
                    c.objects.unlink(ob)
                coll.objects.link(ob)
                moved += 1
            if moved:
                self.report({'INFO'}, tr("Selected objects moved into the tribune") + ": %d" % moved)
        context.scene.tb_active = coll
        if self.mode == 'GENERATED':
            live.request(coll)
        return {'FINISHED'}


class TB_OT_add_selected(bpy.types.Operator):
    bl_idname = "tb.add_selected"
    bl_label = "Add selected objects"
    bl_description = "Moves the selected objects into the active tribune"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        coll = need_tribune(self, context)
        if not coll:
            return {'CANCELLED'}
        n = 0
        for ob in context.selected_objects:
            if ob.name in coll.all_objects:
                continue
            for c in list(ob.users_collection):
                c.objects.unlink(ob)
            coll.objects.link(ob)
            n += 1
        self.report({'INFO'}, tr("Objects added") + ": %d" % n)
        return {'FINISHED'}


class TB_OT_segment(bpy.types.Operator):
    bl_idname = "tb.segment"
    bl_label = "Front line piece"
    bl_options = {'REGISTER', 'UNDO'}

    action: EnumProperty(items=[('ADD', "Add", ""), ('REMOVE', "Remove", ""), ('UP', "Up", ""), ('DOWN', "Down", "")])

    @classmethod
    def description(cls, context, props):
        return {"ADD": tr("Add a piece to the front line"), "REMOVE": tr("Remove the selected piece"),
                "UP": tr("Move the piece up"), "DOWN": tr("Move the piece down")}.get(props.action, "")

    def execute(self, context):
        coll = need_tribune(self, context)
        if not coll:
            return {'CANCELLED'}
        s = coll.tb
        i = s.seg_index
        if self.action == 'ADD':
            seg = s.segments.add()
            if len(s.segments) > 1:
                seg.turn = 45.0
            seg.length = 10.0
            s.segments.move(len(s.segments) - 1, min(i + 1, len(s.segments) - 1))
            s.seg_index = min(i + 1, len(s.segments) - 1)
        elif self.action == 'REMOVE' and len(s.segments) > 1:
            s.segments.remove(i)
            s.seg_index = max(0, i - 1)
        elif self.action == 'UP' and i > 0:
            s.segments.move(i, i - 1)
            s.seg_index = i - 1
        elif self.action == 'DOWN' and i < len(s.segments) - 1:
            s.segments.move(i, i + 1)
            s.seg_index = i + 1
        live.request(coll)
        return {'FINISHED'}


class TB_OT_preset(bpy.types.Operator):
    bl_idname = "tb.preset"
    bl_label = "Shape preset"
    bl_description = "Replaces the front line with a ready-made shape"
    bl_options = {'REGISTER', 'UNDO'}

    shape: EnumProperty(items=[
        ('STRAIGHT', "Straight", ""), ('L', "Corner (L)", ""), ('U', "Three sides (U)", ""),
        ('ARC', "Arc", ""), ('ARENA', "Arena (half circle)", ""), ('WEDGE', "Angled wings", "")])

    def execute(self, context):
        coll = need_tribune(self, context)
        if not coll:
            return {'CANCELLED'}
        s = coll.tb
        s.segments.clear()
        P = {
            'STRAIGHT': [('STRAIGHT', 16, 0, 0, 0)],
            'L': [('STRAIGHT', 14, 0, 0, 0), ('STRAIGHT', 14, 90, 0, 0)],
            'U': [('STRAIGHT', 10, 0, 0, 0), ('STRAIGHT', 16, 90, 0, 0), ('STRAIGHT', 10, 90, 0, 0)],
            'ARC': [('ARC', 0, 0, 14, 90)],
            'ARENA': [('STRAIGHT', 3, 0, 0, 0), ('ARC', 0, 0, 10, 180), ('STRAIGHT', 3, 0, 0, 0)],
            'WEDGE': [('STRAIGHT', 10, 0, 0, 0), ('STRAIGHT', 10, 30, 0, 0), ('STRAIGHT', 10, 30, 0, 0)],
        }[self.shape]
        for kind, length, turn, radius, angle in P:
            seg = s.segments.add()
            seg.kind, seg.turn = kind, turn
            if kind == 'ARC':
                seg.radius, seg.angle = radius, angle
            else:
                seg.length = length
        s.seg_index = 0
        live.request(coll)
        return {'FINISHED'}


class TB_OT_new_room(bpy.types.Operator):
    bl_idname = "tb.new_room"
    bl_label = "New room"
    bl_description = "Adds a rectangular room (edit it like any mesh) with its back wall marked for the tribune"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        coll = need_tribune(self, context)
        if not coll:
            return {'CANCELLED'}
        w, d = 24.0, 18.0
        verts = [(-w / 2, -d / 2, 0.0), (w / 2, -d / 2, 0.0), (w / 2, d / 2, 0.0), (-w / 2, d / 2, 0.0)]
        ob = S.new_mesh_object("Room", coll, verts, [(0, 1, 2, 3)])
        ob.tb_role = 'IGNORE'
        ob.display_type = 'WIRE'
        ob.hide_render = True
        for e in ob.data.edges:
            a, b = e.vertices
            e.use_edge_sharp = verts[a][1] > 0 and verts[b][1] > 0      # back wall (+Y)
        s = coll.tb
        s.back_walk = 0.0          # the tribune stands right against the wall
        s.entrance_front = True
        s.room_object = ob
        s.footprint = 'ROOM'
        live.request(coll)
        return {'FINISHED'}


class TB_OT_mark_walls(bpy.types.Operator):
    bl_idname = "tb.mark_walls"
    bl_label = "Tribune wall"
    bl_options = {'REGISTER', 'UNDO'}

    clear: BoolProperty(default=False)

    @classmethod
    def description(cls, context, props):
        return tr("Selected edges (Edit Mode): no tribune wall") if props.clear else \
            tr("Selected edges (Edit Mode): the tribune stands against these walls")

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob is not None and ob.type == 'MESH' and ob.mode == 'EDIT'

    def execute(self, context):
        import bmesh
        ob = context.active_object
        bm = bmesh.from_edit_mesh(ob.data)
        n = 0
        for e in bm.edges:
            if e.select:
                e.smooth = self.clear
                n += 1
        bmesh.update_edit_mesh(ob.data)
        for c in bpy.data.collections:
            if c.tb.enabled and c.tb.footprint == 'ROOM' and c.tb.room_object == ob:
                live.request(c)
        self.report({'INFO'}, tr("Edges changed") + ": %d" % n)
        return {'FINISHED'}


class TB_OT_generate(bpy.types.Operator):
    bl_idname = "tb.generate"
    bl_label = "Generate tribune"
    bl_description = "Builds model, seats, navmesh, outline and booth from the settings. " \
                     "Replaces everything the generator made before (your own extra objects stay)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        coll = need_tribune(self, context)
        if not coll:
            return {'CANCELLED'}
        s = coll.tb
        try:
            tmpl = S.seat_template(s, context)
            prm = S.gen_params(s)
            prm.update(seat_width=tmpl["width"], seat_depth=tmpl["depth"], sit=tmpl["sit"], seat_bottom=tmpl["bottom"])
            res = geom.generate(prm)
            if s.free_group_max >= s.free_group_min:
                geom.random_free(res["seats"], s.free_seed, s.free_group_min, s.free_group_max, s.free_gap_min,
                                 s.free_gap_max)
            S.build_generated(context, coll, res, tmpl)
        except Exception as e:
            error_report(self, context, e)
            return {'CANCELLED'}
        info = res["info"]
        active = sum(1 for x in res["seats"] if not x["free"])
        lines = [tr("Generated") + ": %d " % info["seats"] + tr("seats") + " (%d " % active + tr("used") + "), "
                 + "%d " % info["rows"] + tr("rows") + ", " + tr("walking lane") + " %.2f m" % info["lane"]]
        lines += [tr("Note") + ": " + w for w in res["warnings"]]
        set_report(context, lines)
        self.report({'WARNING'} if res["warnings"] else {'INFO'}, lines[0])
        return {'FINISHED'}


# ------------------------------------------------------------------ free seats


class TB_OT_random_free(bpy.types.Operator):
    bl_idname = "tb.random_free"
    bl_label = "Random free seats"
    bl_description = "Leaves random gaps of free seats between groups of guests, like a real audience"
    bl_options = {'REGISTER', 'UNDO'}

    clear: BoolProperty(default=False, options={'SKIP_SAVE'})

    def execute(self, context):
        coll = need_tribune(self, context)
        if not coll:
            return {'CANCELLED'}
        s = coll.tb
        seats = S.objects(coll, 'SEAT')
        if self.clear:
            for e in seats:
                e.tb_free = False
                e.empty_display_size = 0.45
            self.report({'INFO'}, tr("All seats are used"))
            return {'FINISHED'}
        data = [{"obj": e, "row": e.tb_row, "order": e.tb_order, "free": e.tb_free} for e in seats]
        geom.random_free(data, s.free_seed, s.free_group_min, s.free_group_max, s.free_gap_min, s.free_gap_max)
        for d in data:
            d["obj"].tb_free = d["free"]
            d["obj"].empty_display_size = 0.2 if d["free"] else 0.45
        n = sum(1 for d in data if d["free"])
        self.report({'INFO'}, tr("Free seats") + ": %d / %d" % (n, len(data)))
        return {'FINISHED'}


class TB_OT_toggle_free(bpy.types.Operator):
    bl_idname = "tb.toggle_free"
    bl_label = "Toggle free"
    bl_description = "Selected seats: switch between used and free"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        n = 0
        for ob in context.selected_objects:
            e = ob if ob.tb_role == 'SEAT' else (ob.parent if ob.parent and ob.parent.tb_role == 'SEAT' else None)
            if e:
                e.tb_free = not e.tb_free
                e.empty_display_size = 0.2 if e.tb_free else 0.45
                n += 1
        self.report({'INFO'}, tr("Seats changed") + ": %d" % n)
        return {'FINISHED'}


# ------------------------------------------------------------------ own models: seats


def _bvh_for(objs, depsgraph, up_only=False, min_nz=0.6, exclude_fn=None):
    verts, polys = [], []
    for ob in objs:
        W, tv = S.mesh_tris_world(ob, depsgraph)
        if len(tv) == 0:
            continue
        A, B, C = W[tv[:, 0]], W[tv[:, 1]], W[tv[:, 2]]
        n = np.cross(B - A, C - A)
        l = np.linalg.norm(n, axis=1)
        keep = l > 1e-10
        if up_only:
            keep &= (n[:, 2] / np.maximum(l, 1e-12)) >= min_nz
        if exclude_fn is not None:
            cen = (A + B + C) / 3
            keep &= ~np.array([exclude_fn(*c) for c in cen], dtype=bool) if len(cen) else keep
        base = len(verts)
        verts.extend(map(tuple, W.tolist()))
        polys.extend((int(a) + base, int(b) + base, int(c) + base) for a, b, c in tv[keep])
    if not polys:
        return None
    return BVHTree.FromPolygons(verts, polys)


def _floor_below(bvh, x, y, z):
    if bvh is None:
        return 0.0
    hit = bvh.ray_cast(Vector((x, y, z)), Vector((0.0, 0.0, -1.0)), 200.0)
    return hit[0].z if hit[0] is not None else 0.0


def _loose_parts(W, tv):
    parent = list(range(len(W)))

    def f(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for a, b, c in tv:
        ra, rb, rc = f(a), f(b), f(c)
        parent[rb] = ra
        parent[f(rc)] = ra
    groups = {}
    used = set(int(i) for t in tv for i in t)
    for i in used:
        groups.setdefault(f(i), []).append(i)
    return [W[g] for g in groups.values() if len(g) >= 4]


class TB_OT_detect_seats(bpy.types.Operator):
    bl_idname = "tb.detect_seats"
    bl_label = "Seats from selection"
    bl_description = "Creates a sit point with walk target for every seat in the selected meshes " \
                     "(replaces the existing seat points)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        coll = need_tribune(self, context)
        if not coll:
            return {'CANCELLED'}
        s = coll.tb
        sel = [o for o in context.selected_objects if o.type == 'MESH' and o.tb_role == 'NONE']
        if not sel:
            self.report({'ERROR'}, tr("Select the seat meshes first."))
            return {'CANCELLED'}
        try:
            dg = context.evaluated_depsgraph_get()
            stage = None
            for o in S.objects(coll, 'STAGE'):
                stage = tuple(o.matrix_world.translation)
            pieces = []
            for ob in sel:
                if ob.name not in coll.all_objects:
                    for c in list(ob.users_collection):
                        c.objects.unlink(ob)
                    coll.objects.link(ob)
                ob.tb_seatmesh = True
                W, tv = S.mesh_tris_world(ob, dg)
                fwd = ob.matrix_world.to_3x3() @ Vector((0.0, -1.0, 0.0))
                if s.detect_mode == 'PARTS':
                    loose = _loose_parts(W, tv)
                    for grp in custom.merge_parts(loose):
                        pieces.append((np.concatenate([loose[i] for i in grp]), (fwd.x, fwd.y)))
                elif len(W):
                    pieces.append((W, (fwd.x, fwd.y)))
            if not pieces:
                raise ValueError(tr("No seat geometry found in the selection."))
            others = [o for o in S.model_objects(coll) if not o.tb_seatmesh]
            floor_bvh = _bvh_for(others, dg, up_only=True)
            mode = s.facing_mode
            seats = []
            for P, fwd in pieces:
                cen = P.mean(0)
                if mode == 'OBJECT':
                    rough = custom.facing_for(cen, 'OBJECT', obj_forward=fwd)
                elif mode in ('STAGE', 'ROW') and stage is not None:
                    rough = custom.facing_for(cen, 'STAGE', stage=stage)
                else:
                    rough = (0.0, -1.0)
                d = custom.seat_from_points([tuple(p) for p in P], rough)
                # start the ray a bit above the seat's lowest point: seat feet may be sunk into the floor
                fl = _floor_below(floor_bvh, d["sit"][0], d["sit"][1],
                                  min(float(d["sit"][2]) - 0.05, float(P[:, 2].min()) + 0.45))
                seats.append({"pts": P, "rough": rough, "facing": rough, "sit": d["sit"], "floor": fl})
            custom.number_rows(seats, stage=stage if stage else None)
            if mode == 'ROW':
                custom.refine_facing(seats, lambda x: x["rough"])
            old = [o for o in S.objects(coll) if o.tb_role in ('SEAT', 'TARGET')]
            S.remove_objects(old)
            sc = S.child_collection(coll, "Seat points")
            for x in seats:
                d = custom.seat_from_points([tuple(p) for p in x["pts"]], x["facing"], clearance=s.nav_clearance)
                tx, ty = d["target_xy"]
                tz = _floor_below(floor_bvh, tx, ty, d["sit"][2])
                S.make_seat_empty(sc, "Seat %02d-%03d" % (x["row"], x["order"]), d["sit"], d["yaw"], (tx, ty, tz),
                                  x["row"], x["order"], False, (d["back"], d["front"], d["half_w"]), x["floor"])
        except Exception as e:
            error_report(self, context, e)
            return {'CANCELLED'}
        rows = len(set(x["row"] for x in seats))
        msg = tr("Seats found") + ": %d, " % len(seats) + tr("rows") + ": %d" % rows
        if stage is None and mode in ('STAGE', 'ROW'):
            msg += " - " + tr("no stage point: seats look to -Y")
        set_report(context, [msg])
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class TB_OT_add_seat(bpy.types.Operator):
    bl_idname = "tb.add_seat"
    bl_label = "Seat at 3D cursor"
    bl_description = "Adds one sit point at the 3D cursor, looking to -Y (turn it around Z to change the direction)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        coll = need_tribune(self, context)
        if not coll:
            return {'CANCELLED'}
        c = context.scene.cursor.location
        sc = S.child_collection(coll, "Seat points")
        rows = [e.tb_row for e in S.objects(coll, 'SEAT')]
        e, t = S.make_seat_empty(sc, "Seat", (c.x, c.y, c.z), 0.0, (c.x, c.y - 0.6, c.z - 0.5), 1,
                                 len(rows) + 1, False, None, c.z - 0.5)
        for o in context.selected_objects:
            o.select_set(False)
        e.select_set(True)
        context.view_layer.objects.active = e
        return {'FINISHED'}


class TB_OT_renumber(bpy.types.Operator):
    bl_idname = "tb.renumber"
    bl_label = "Renumber rows"
    bl_description = "Sorts all seats into rows (by height) and numbers them from left to right as seen by the audience"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        coll = need_tribune(self, context)
        if not coll:
            return {'CANCELLED'}
        stage = None
        for o in S.objects(coll, 'STAGE'):
            stage = tuple(o.matrix_world.translation)
        data = S.seat_data(coll)
        for d in data:
            d["floor"] = d["obj"].tb_floor if d["obj"].tb_floor else d["sit"][2] - 0.5
        custom.number_rows(data, stage=stage)
        for d in data:
            d["obj"].tb_row, d["obj"].tb_order = d["row"], d["order"]
            d["obj"].name = "Seat %02d-%03d" % (d["row"], d["order"])
        self.report({'INFO'}, tr("Rows") + ": %d" % len(set(d["row"] for d in data)))
        return {'FINISHED'}


class TB_OT_snap_targets(bpy.types.Operator):
    bl_idname = "tb.snap_targets"
    bl_label = "Targets onto navmesh"
    bl_description = "Puts every walk target exactly onto the navmesh below it"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        coll = need_tribune(self, context)
        if not coll:
            return {'CANCELLED'}
        V, T = S.nav_data(coll, context.evaluated_depsgraph_get())
        if not V:
            self.report({'ERROR'}, tr("No navmesh."))
            return {'CANCELLED'}
        bvh = BVHTree.FromPolygons(V, T)
        n = 0
        for e in S.objects(coll, 'TARGET'):
            p = e.matrix_world.translation
            hit = bvh.ray_cast(Vector((p.x, p.y, p.z + 0.6)), Vector((0, 0, -1)), 2.0)
            if hit[0] is not None:
                mw = e.matrix_world.copy()
                mw.translation = Vector((p.x, p.y, hit[0].z))
                e.matrix_world = mw
                n += 1
        self.report({'INFO'}, tr("Targets moved") + ": %d" % n)
        return {'FINISHED'}


# ------------------------------------------------------------------ outline, booth, stage


def _model_bounds(coll, context):
    dg = context.evaluated_depsgraph_get()
    lo = hi = None
    for ob in S.model_objects(coll):
        W, _tv = S.mesh_tris_world(ob, dg)
        if len(W) == 0:
            continue
        lo = W.min(0) if lo is None else np.minimum(lo, W.min(0))
        hi = W.max(0) if hi is None else np.maximum(hi, W.max(0))
    return lo, hi


class TB_OT_outline_default(bpy.types.Operator):
    bl_idname = "tb.outline_default"
    bl_label = "Outline around model"
    bl_description = "Creates a rectangular ride outline around the model with entrances on the left and right " \
                     "(edit it in Edit Mode; edges marked as seam are entrances/exits)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        coll = need_tribune(self, context)
        if not coll:
            return {'CANCELLED'}
        lo, hi = _model_bounds(coll, context)
        if lo is None:
            self.report({'ERROR'}, tr("The tribune has no model yet."))
            return {'CANCELLED'}
        s = coll.tb
        S.remove_objects(S.objects(coll, 'OUTLINE'))
        poly, kinds = custom.default_outline(lo[0], lo[1], hi[0], hi[1], s.outline_margin, s.entrance_length)
        S.outline_object(coll, poly, kinds, generated=False)
        return {'FINISHED'}


class TB_OT_add_marker(bpy.types.Operator):
    bl_idname = "tb.add_marker"
    bl_label = "Add marker"
    bl_options = {'REGISTER', 'UNDO'}

    kind: EnumProperty(items=[('BOOTH', "Ride booth", ""), ('STAGE', "Stage point", "")])

    @classmethod
    def description(cls, context, props):
        return tr("Adds the ride booth at the 3D cursor") if props.kind == 'BOOTH' else \
            tr("Adds the stage point at the 3D cursor (seats are turned towards it)")

    def execute(self, context):
        coll = need_tribune(self, context)
        if not coll:
            return {'CANCELLED'}
        c = context.scene.cursor.location
        S.remove_objects(S.objects(coll, self.kind))
        if self.kind == 'BOOTH':
            S.booth_object(coll, (c.x, c.y), generated=False)
        else:
            e = bpy.data.objects.new("Stage point", None)
            e.empty_display_type = 'PLAIN_AXES'
            e.empty_display_size = 1.0
            e.location = c.copy()
            e.tb_role = 'STAGE'
            coll.objects.link(e)
        return {'FINISHED'}


class TB_OT_set_role(bpy.types.Operator):
    bl_idname = "tb.set_role"
    bl_label = "Set role"
    bl_description = "Sets the role of the selected objects"
    bl_options = {'REGISTER', 'UNDO'}

    role: EnumProperty(items=[('NONE', "Model", ""), ('NAV', "Navmesh", ""), ('OUTLINE', "Outline", ""),
                              ('IGNORE', "Ignore", "")])

    def execute(self, context):
        for ob in context.selected_objects:
            if ob.type == 'MESH' or self.role in ('NONE', 'IGNORE'):
                ob.tb_role = self.role
                if self.role == 'NAV':
                    ob.data.materials.clear()
                    ob.data.materials.append(S.get_material(S.NAV_MAT))
                    ob.show_wire = True
        return {'FINISHED'}


# ------------------------------------------------------------------ navmesh


class TB_OT_nav_auto(bpy.types.Operator):
    bl_idname = "tb.nav_auto"
    bl_label = "Navmesh from model"
    bl_description = "Calculates where guests can walk: on all flat and gently sloped surfaces of the model, " \
                     "not under seats, with stairs as ramps. Replaces the existing navmesh"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        coll = need_tribune(self, context)
        if not coll:
            return {'CANCELLED'}
        s = coll.tb
        try:
            poly, kinds = S.outline_data(coll)
            if not poly:
                lo, hi = _model_bounds(coll, context)
                if lo is None:
                    raise ValueError(tr("The tribune has no model yet."))
                poly, kinds = custom.default_outline(lo[0], lo[1], hi[0], hi[1], s.outline_margin, s.entrance_length)
                S.outline_object(coll, poly, kinds, generated=False)
            dg = context.evaluated_depsgraph_get()
            seats = S.seat_data(coll)
            body = custom.SeatBlocker([dict(x, floor=x["floor"]) for x in seats], clearance=0.0)

            def seat_body(x, y, z):
                # seat shells and backs: above the seat floor, inside the seat footprint
                for k in body.grid.get((int(math.floor(x / body.cell)), int(math.floor(y / body.cell))), ()):
                    fx, fy, rx, ry, a0, a1, b0, b1, floor = body.items[k]
                    a, b = x * fx + y * fy, x * rx + y * ry
                    if a0 <= a <= a1 and b0 <= b <= b1 and floor + 0.12 < z < floor + 1.5:
                        return True
                return False
            model = [o for o in S.model_objects(coll)]
            nonseat = [o for o in model if not o.tb_seatmesh]
            walk = _bvh_for(model, dg, up_only=True, min_nz=0.75, exclude_fn=seat_body if seats else None)
            head = _bvh_for(nonseat, dg)
            block = custom.SeatBlocker(seats, clearance=s.nav_clearance) if seats else None
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            top = 200.0
            hr = s.nav_headroom

            def sample(x, y):
                inside = custom.point_in_poly(x, y, poly)
                if not inside:
                    return None, False
                z = None
                if walk is not None:
                    hit = walk.ray_cast(Vector((x, y, top)), Vector((0.0, 0.0, -1.0)), 2 * top)
                    if hit[0] is not None:
                        z = hit[0].z
                if z is None or z < 0.0:
                    z = 0.0
                over = False
                if head is not None:
                    h = head.ray_cast(Vector((x, y, z + 0.05)), Vector((0.0, 0.0, 1.0)), hr)
                    over = h[0] is not None
                if block is not None and not over:
                    over = block(x, y, z)
                return z, over
            wm = context.window_manager
            wm.progress_begin(0, 100)
            try:
                V, T = custom.nav_grid((min(xs), min(ys), max(xs), max(ys)), sample, cell=s.nav_cell,
                                       max_step=s.nav_max_step, clearance=0.0, outline=poly, kinds=kinds,
                                       progress=lambda f: wm.progress_update(int(f * 100)))
            finally:
                wm.progress_end()
            if not T:
                raise ValueError(tr("No walkable area found that touches an entrance of the outline."))
            if len(V) > 65000:
                raise ValueError(tr("The navmesh is too detailed for the game. Use a bigger grid value.")
                                 + " (%d)" % len(V))
            S.remove_objects(S.objects(coll, 'NAV'))
            S.nav_object(coll, V, T, generated=False)
        except Exception as e:
            error_report(self, context, e)
            return {'CANCELLED'}
        msg = tr("Navmesh") + ": %d " % len(T) + tr("triangles")
        set_report(context, [msg, tr("Run 'Check' to see if every seat can be reached.")])
        self.report({'INFO'}, msg)
        return {'FINISHED'}


def _simplify(V, T):
    """Merges flat areas into bigger triangles. Neighbouring areas keep shared edges."""
    import bmesh
    bm = bmesh.new()
    try:
        bv = [bm.verts.new(v) for v in V]
        for t in T:
            try:
                bm.faces.new([bv[i] for i in t])
            except ValueError:
                pass
        bm.verts.ensure_lookup_table()
        bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(0.5), use_dissolve_boundaries=False,
                                 verts=list(bm.verts), edges=list(bm.edges), delimit=set())
        bmesh.ops.triangulate(bm, faces=list(bm.faces), quad_method='BEAUTY', ngon_method='BEAUTY')
        bm.verts.index_update()
        V2 = [tuple(v.co) for v in bm.verts]
        T2 = [tuple(v.index for v in f.verts) for f in bm.faces]
    except Exception:
        print(traceback.format_exc())
        return V, T
    finally:
        bm.free()
    if not T2 or len(T2) > len(T):
        return V, T
    return V2, T2


# ------------------------------------------------------------------ check


def run_check(coll, context):
    dg = context.evaluated_depsgraph_get()
    lines, bad = [], []
    V, T = S.nav_data(coll, dg)
    poly, kinds = S.outline_data(coll)
    seats = S.seat_data(coll)
    booth = S.objects(coll, 'BOOTH')
    errors, warns = [], []
    if not seats:
        if coll.tb.mode == 'GENERATED':
            errors.append(tr("No seat points yet: press 'Generate tribune'."))
        else:
            errors.append(tr("No seats."))
    if not V:
        errors.append(tr("No navmesh."))
    if not poly:
        errors.append(tr("No outline."))
    elif "EXF" not in kinds:
        errors.append(tr("The outline has no entrance (mark entrance edges as seam)."))
    if not booth:
        errors.append(tr("No ride booth."))
    missing = [x for x in seats if x["target"] is None]
    if missing:
        errors.append(tr("Seats without walk target") + ": %d" % len(missing))
    if poly and booth:
        b = booth[0].matrix_world.translation
        if not custom.point_in_poly(b.x, b.y, poly):
            warns.append(tr("The ride booth is outside the outline."))
    if not S.model_objects(coll):
        errors.append(tr("No visible model."))
    used = [x for x in seats if not x["free"]]
    if len(used) > 400:
        warns.append(tr("Many seats") + ": %d" % len(used))
    rep = None
    if V and poly and seats and not missing:
        rep = navcheck.check(V, T, poly, kinds, seats)
        errors += [tr(e) if "%" not in e else e for e in rep["errors"]]
        warns += rep["warnings"]
        bad = [seats[i]["obj"] for i, _why in rep["bad_seats"]]
        lines.append(tr("Navmesh") + ": %d " % rep["tris"] + tr("triangles") + ", "
                     + tr("reachable seats") + ": %d / %d" % (rep["ok_seats"], len(used)))
    return errors, warns, lines, bad


class TB_OT_check(bpy.types.Operator):
    bl_idname = "tb.check"
    bl_label = "Check"
    bl_description = "Checks if guests can walk from an entrance to every seat and if everything needed is there. " \
                     "Seats that cannot be reached get selected"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        coll = need_tribune(self, context)
        if not coll:
            return {'CANCELLED'}
        try:
            errors, warns, lines, bad = run_check(coll, context)
        except Exception as e:
            error_report(self, context, e)
            return {'CANCELLED'}
        out = list(lines)
        out += [tr("Error") + ": " + e for e in errors]
        out += [tr("Note") + ": " + w for w in warns]
        if not errors:
            out.insert(0, tr("Everything OK - ready to export."))
        set_report(context, out)
        if bad:
            for o in context.selected_objects:
                o.select_set(False)
            for e in bad:
                S.show(e)
            context.view_layer.objects.active = bad[0]
        self.report({'ERROR'} if errors else ({'WARNING'} if warns else {'INFO'}), out[0])
        return {'FINISHED'}


# ------------------------------------------------------------------ export and build


def _cobra_ok():
    try:
        import generated  # noqa: F401
        return True
    except Exception:
        return False


REQUIRED = {"imageio": "imageio>=2.26.0", "PIL": "pillow>=10.0.1", "bitarray": "bitarray~=2.9.2"}


def missing_packages():
    import importlib.util
    return [pip for mod, pip in REQUIRED.items() if importlib.util.find_spec(mod) is None]


class TB_OT_export(bpy.types.Operator):
    bl_idname = "tb.export"
    bl_label = "Save to library"
    bl_description = "Checks the tribune and saves model, seats, navmesh and outline into the library"
    bl_options = {'REGISTER'}

    def execute(self, context):
        coll = need_tribune(self, context)
        if not coll:
            return {'CANCELLED'}
        if not _cobra_ok():
            self.report({'ERROR'}, tr("cobra-tools is not active. Install and enable the cobra-tools add-on."))
            return {'CANCELLED'}
        s = coll.tb
        from .core import gamebuild
        tid = s.tid.strip()
        if not gamebuild.ID_RE.match(tid):
            self.report({'ERROR'}, tr("Invalid ID: 3-31 lowercase letters, digits and _, starting with a letter."))
            return {'CANCELLED'}
        try:
            errors, warns, lines, _bad = run_check(coll, context)
            if errors:
                set_report(context, [tr("Not saved") + ":"] + [tr("Error") + ": " + e for e in errors])
                self.report({'ERROR'}, errors[0])
                return {'CANCELLED'}
            dg = context.evaluated_depsgraph_get()
            parts, mats, bounds = S.model_parts(coll, dg, floor_tile=s.floor_pattern_size,
                                                  seat_tile=getattr(s, "seat_pattern_size", 0.5))
            V, T = S.nav_data(coll, dg)
            poly, kinds = S.outline_data(coll)
            seats = [{"sit": x["sit"], "yaw": x["yaw"], "target": x["target"], "row": x["row"], "order": x["order"],
                      "free": x["free"]} for x in S.seat_data(coll)]
            b = S.objects(coll, 'BOOTH')[0].matrix_world.translation
            t = {"id": tid, "name": s.game_name, "description": s.description, "seats": seats,
                 "single_guests": bool(getattr(s, "single_guests", True)),
                 "surface": {"floor": s.floor_pattern, "seat": s.seat_pattern},
                 "nav": {"verts": [list(v) for v in V], "tris": [list(x) for x in T]},
                 "outline": {"poly": [list(p) for p in poly], "kinds": kinds}, "booth": [b.x, b.y, 0.0],
                 "structure_bounds": bounds}
            lib = bpy.path.abspath(prefs(context).library_dir)
            if not s.uid:
                s.uid = uuid.uuid4().hex
            t["uid"] = s.uid
            if s.auto_name:
                s.game_name = auto_name(lib, used_seats(seats), s.uid, tid)
                t["name"] = s.game_name
            old = gamebuild.library_entry(lib, tid)
            if old and old.get("uid") and old["uid"] != s.uid:
                msg = tr("The ID is already used in the library by another tribune") + \
                    " ('%s'). " % old.get("name", tid) + tr("Change the ID at the top of the Tribune panel or remove the other one in the library.")
                set_report(context, [tr("Not saved") + ":", msg])
                self.report({'ERROR'}, msg)
                return {'CANCELLED'}
            if old and not old.get("uid"):
                warns = list(warns) + [tr("Replaced the tribune saved earlier under this ID") + " ('%s')." % old.get("name", tid)]
            with gamebuild.cobra_imports():
                gamebuild.save_to_library(lib, t, parts, mats, log=print)
        except Exception as e:
            error_report(self, context, e)
            return {'CANCELLED'}
        used = sum(1 for x in seats if not x["free"])
        msg = tr("Saved to library") + ": %s, %s (%d " % (s.game_name, tid, used) + tr("seats") + ")"
        from .core import gamebuild as _gb
        n_lib = len(_gb.list_library(lib))
        set_report(context, [msg, tr("Library") + ": %s (%d)" % (lib, n_lib),
                             tr("Now press 'Build mod and install'.")] + [tr("Note") + ": " + w for w in warns])
        self.report({'INFO'}, msg)
        return {'FINISHED'}


def used_seats(seats):
    return sum(1 for x in seats if not x["free"])


def auto_name(lib, n, uid, tid):
    """'Show Arena <seats>', with ' (2)', ' (3)' ... when other tribunes in the library have the same seat count"""
    from .core import gamebuild
    taken = set()
    for e in gamebuild.list_index(lib):
        if (e.get("uid") and e.get("uid") == uid) or e.get("id") == tid:
            continue
        taken.add((e.get("name") or "").strip().lower())
    base = "Show Arena %d" % n
    name, k = base, 1
    while name.lower() in taken:
        k += 1
        name = "%s (%d)" % (base, k)
    return name


def find_ovldata(pref):
    """the configured ovldata folder, or Planet Coaster 2 in a Steam library on any drive"""
    def ok(d):
        # a complete Planet Coaster 2 with the Silver Screen DLC (leftover folders of old installs are skipped)
        return bool(d) and os.path.isdir(os.path.join(d, "GameMain")) and \
            os.path.isfile(os.path.join(d, "ContentPDLC5", "Rides", "FlatRides", "FR_Cinema", "FR_Cinema.ovl"))
    if ok(pref):
        return pref
    tail = os.path.join("steamapps", "common", "Planet Coaster 2", "Win64", "ovldata")
    cands = []
    for drive in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        root = drive + ":\\"
        if not os.path.isdir(root):
            continue
        for base in ("SteamLibrary", "Steam", os.path.join("Program Files (x86)", "Steam"),
                     os.path.join("Program Files", "Steam"), "Games\\Steam", "Games\\SteamLibrary"):
            cands.append(os.path.join(root, base, tail))
    for c in cands:
        if ok(c):
            return c
    return None


class TB_OT_build(bpy.types.Operator):
    bl_idname = "tb.build"
    bl_label = "Build mod and install"
    bl_description = "Saves the active tribune to the library, then installs every tribune of the library as its " \
                     "own mod folder Mod_TB_<ID> (close the game first)"
    bl_options = {'REGISTER'}

    def execute(self, context):
        if not _cobra_ok():
            self.report({'ERROR'}, tr("cobra-tools is not active. Install and enable the cobra-tools add-on."))
            return {'CANCELLED'}
        from .core import gamebuild
        p = prefs(context)
        lib = bpy.path.abspath(p.library_dir)
        ovl = bpy.path.abspath(p.ovldata_dir)
        found = find_ovldata(ovl)
        if not found:
            self.report({'ERROR'}, tr("Planet Coaster 2 not found. Set the ovldata folder in the Library panel "
                                      "(...\\steamapps\\common\\Planet Coaster 2\\Win64\\ovldata).") + " " + ovl)
            return {'CANCELLED'}
        if os.path.normcase(os.path.normpath(found)) != os.path.normcase(os.path.normpath(ovl)):
            p.ovldata_dir = found
            self.report({'INFO'}, tr("Game found") + ": " + found)
        ovl = found
        # the tribune being edited is always saved first, so the game gets exactly what is in the scene
        saved = None
        if S.active_tribune(context) is not None:
            r = TB_OT_export.execute(self, context)
            if r != {'FINISHED'}:
                return r
            saved = context.scene.tb_report.split("\n")[0]
        cache = os.path.join(os.path.dirname(lib.rstrip("\\/")), "cache")
        log = []
        try:
            targets = gamebuild.build_mod(lib, ovl, cache, log=lambda m: (log.append(m), print("[tribune builder]", m)),
                                         yaw_sign=float(p.yaw_sign))
        except ImportError as e:
            self.report({'ERROR'}, tr("Missing Python packages - press 'Install missing packages'") + ": " + str(e))
            return {'CANCELLED'}
        except Exception as e:
            error_report(self, context, e)
            return {'CANCELLED'}
        lines = ([saved] if saved else []) + [tr("Game folder") + ": " + ovl]
        for l in log:
            if l.startswith("in the mod: "):
                lines.append(tr("Installed") + ": " + l[len("in the mod: "):])
            elif l.startswith("note:") or l.startswith("removed old mod folder") or l.startswith("library: "):
                lines.append(l)
        set_report(context, lines)
        self.report({'INFO'}, tr("Installed") + ": %d " % len(targets) + tr("tribune mods"))
        return {'FINISHED'}


class TB_OT_library_remove(bpy.types.Operator):
    bl_idname = "tb.library_remove"
    bl_label = "Remove from library"
    bl_description = "Removes this tribune from the library (build the mod again afterwards)"
    bl_options = {'REGISTER'}

    tid: StringProperty()

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        import shutil
        lib = bpy.path.abspath(prefs(context).library_dir)
        folder = os.path.join(lib, self.tid)
        if self.tid and os.path.isfile(os.path.join(folder, "tribune.json")):
            shutil.rmtree(folder)
            self.report({'INFO'}, tr("Removed") + ": " + self.tid)
        return {'FINISHED'}


class TB_OT_open_library(bpy.types.Operator):
    bl_idname = "tb.open_library"
    bl_label = "Open library folder"

    def execute(self, context):
        lib = bpy.path.abspath(prefs(context).library_dir)
        os.makedirs(lib, exist_ok=True)
        bpy.ops.wm.path_open(filepath=lib)
        return {'FINISHED'}


class TB_OT_install_deps(bpy.types.Operator):
    bl_idname = "tb.install_deps"
    bl_label = "Install missing packages"
    bl_description = "Installs imageio, Pillow and bitarray for Blender's Python (needs internet). Restart Blender afterwards"

    def execute(self, context):
        import subprocess
        import sys
        miss = missing_packages()
        if not miss:
            self.report({'INFO'}, tr("All packages are already there"))
            return {'FINISHED'}
        target = os.path.join(bpy.utils.user_resource('SCRIPTS'), "addons", "modules")
        os.makedirs(target, exist_ok=True)
        py = sys.executable
        subprocess.run([py, "-m", "ensurepip", "--upgrade"], capture_output=True, text=True)
        r = subprocess.run([py, "-m", "pip", "install", "--no-deps", "--upgrade", "--target", target, *miss],
                           capture_output=True, text=True)
        if r.returncode != 0:
            self.report({'ERROR'}, (r.stderr or r.stdout or "pip failed").strip().splitlines()[-1])
            return {'CANCELLED'}
        self.report({'INFO'}, tr("Installed - please restart Blender"))
        return {'FINISHED'}


class TB_OT_select_role(bpy.types.Operator):
    bl_idname = "tb.select_role"
    bl_label = "Select"
    bl_description = "Selects all objects of this kind in the tribune"
    bl_options = {'REGISTER', 'UNDO'}

    role: StringProperty()
    free_only: BoolProperty(default=False)

    def execute(self, context):
        coll = need_tribune(self, context)
        if not coll:
            return {'CANCELLED'}
        for o in context.selected_objects:
            o.select_set(False)
        n = 0
        for o in S.objects(coll, self.role):
            if self.free_only and not o.tb_free:
                continue
            if S.show(o):
                context.view_layer.objects.active = o
                n += 1
        self.report({'INFO'}, "%d" % n)
        return {'FINISHED'}


CLASSES = [TB_OT_new, TB_OT_add_selected, TB_OT_segment, TB_OT_preset, TB_OT_new_room, TB_OT_mark_walls, TB_OT_generate, TB_OT_random_free,
           TB_OT_toggle_free, TB_OT_detect_seats, TB_OT_add_seat, TB_OT_renumber, TB_OT_snap_targets,
           TB_OT_outline_default, TB_OT_add_marker, TB_OT_set_role, TB_OT_nav_auto, TB_OT_check, TB_OT_export,
           TB_OT_build, TB_OT_library_remove, TB_OT_open_library, TB_OT_install_deps, TB_OT_select_role]


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
