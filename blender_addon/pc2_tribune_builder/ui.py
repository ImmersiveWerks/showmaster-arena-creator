import os

import bpy

from . import scene as S
from .props import prefs


def T(s):
    return bpy.app.translations.pgettext_iface(s)


class TB_UL_segments(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        if item.kind == 'ARC':
            row.label(text="%d" % (index + 1), icon='SPHERECURVE')
            row.prop(item, "radius", text="R")
            row.prop(item, "angle", text="°")
        else:
            row.label(text="%d" % (index + 1), icon='IPO_LINEAR')
            row.prop(item, "length", text="")
        if index > 0:
            row.prop(item, "turn", text="∠")


def box(layout, title, icon='NONE'):
    b = layout.box()
    b.label(text=title, icon=icon)
    return b


class TB_PT_main(bpy.types.Panel):
    bl_label = "Tribune Builder"
    bl_idname = "TB_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tribune"

    def draw(self, context):
        layout = self.layout
        sc = context.scene
        from . import bl_info
        layout.label(text="Version %d.%d.%d" % bl_info["version"], icon='INFO', translate=False)
        row = layout.row(align=True)
        row.prop(sc, "tb_active", text="")
        op = row.operator("tb.new", text="", icon='ADD')
        op.mode = 'GENERATED'
        coll = S.active_tribune(context)
        r = layout.row(align=True)
        r.operator("tb.new", text="New: generator", icon='MOD_BUILD').mode = 'GENERATED'
        r.operator("tb.new", text="New: own model", icon='IMPORT').mode = 'CUSTOM'
        if coll is None:
            layout.label(text="Choose or create a tribune.", icon='INFO')
            return
        s = coll.tb
        col = layout.column(align=True)
        col.prop(s, "mode", expand=True)
        col = layout.column(align=True)
        col.prop(s, "auto_name")
        r_ = col.row(align=True)
        r_.enabled = not s.auto_name
        r_.prop(s, "game_name")
        col.prop(s, "tid")
        col.prop(s, "description")
        col.prop(s, "single_guests")


class TB_PT_shape(bpy.types.Panel):
    bl_label = "1. Shape"
    bl_parent_id = "TB_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tribune"

    @classmethod
    def poll(cls, context):
        c = S.active_tribune(context)
        return c is not None and c.tb.mode == 'GENERATED'

    def draw(self, context):
        s = S.active_tribune(context).tb
        layout = self.layout
        layout.prop(s, "footprint", expand=True)
        if s.footprint == 'ROOM':
            row = layout.row(align=True)
            row.prop(s, "room_object", text="")
            row.operator("tb.new_room", text="", icon='ADD')
            layout.prop(s, "staff_path")
            col = layout.column(align=True)
            col.label(text="Draw the room from above (a face or edge loop).")
            col.label(text="Edit Mode: select wall edges, then:")
            row = layout.row(align=True)
            row.operator("tb.mark_walls", text="Tribune wall", icon='MOD_BUILD').clear = False
            row.operator("tb.mark_walls", text="Normal wall", icon='X').clear = True
            col = layout.column(align=True)
            col.label(text="The back stays on the walls, the ends follow")
            col.label(text="the neighbouring walls. More rows grow into the room.")
            return
        layout.label(text="Front line (rows are behind it):")
        g = layout.grid_flow(columns=3, align=True)
        for shape, label in (('STRAIGHT', "Straight"), ('L', "Corner"), ('U', "U shape"), ('ARC', "Arc"),
                             ('ARENA', "Arena"), ('WEDGE', "Wings")):
            g.operator("tb.preset", text=label).shape = shape
        row = layout.row()
        row.template_list("TB_UL_segments", "", s, "segments", s, "seg_index", rows=3)
        c = row.column(align=True)
        c.operator("tb.segment", text="", icon='ADD').action = 'ADD'
        c.operator("tb.segment", text="", icon='REMOVE').action = 'REMOVE'
        c.separator()
        c.operator("tb.segment", text="", icon='TRIA_UP').action = 'UP'
        c.operator("tb.segment", text="", icon='TRIA_DOWN').action = 'DOWN'
        if 0 <= s.seg_index < len(s.segments):
            seg = s.segments[s.seg_index]
            b = layout.box()
            b.prop(seg, "kind", expand=True)
            if seg.kind == 'ARC':
                b.prop(seg, "radius")
                b.prop(seg, "angle")
            else:
                b.prop(seg, "length")
            if s.seg_index > 0:
                b.prop(seg, "turn")
            else:
                b.label(text="The first piece has no angle.", icon='INFO')
        layout.prop(s, "arc_step")


class TB_PT_rows(bpy.types.Panel):
    bl_label = "2. Rows and seats"
    bl_parent_id = "TB_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tribune"

    @classmethod
    def poll(cls, context):
        c = S.active_tribune(context)
        return c is not None and c.tb.mode == 'GENERATED'

    def draw(self, context):
        s = S.active_tribune(context).tb
        layout = self.layout
        col = layout.column(align=True)
        col.prop(s, "rows")
        col.prop(s, "first_row_depth")
        col.prop(s, "row_depth")
        col.prop(s, "row_rise")
        col.prop(s, "first_row_height")
        b = layout.box()
        b.prop(s, "seat_source")
        if s.seat_source == 'OBJECT':
            b.prop(s, "seat_object")
            b.label(text="Origin on the floor, guest looks to -Y", icon='INFO')
        col = b.column(align=True)
        col.prop(s, "seat_height")
        col.prop(s, "seat_gap")
        col.prop(s, "seat_back_gap")
        col.prop(s, "clearance")


class TB_PT_aisles(bpy.types.Panel):
    bl_label = "3. Stairs"
    bl_parent_id = "TB_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tribune"

    @classmethod
    def poll(cls, context):
        c = S.active_tribune(context)
        return c is not None and c.tb.mode == 'GENERATED'

    def draw(self, context):
        s = S.active_tribune(context).tb
        layout = self.layout
        layout.prop(s, "aisle_width")
        row = layout.row(align=True)
        row.prop(s, "aisle_left", toggle=True)
        row.prop(s, "aisle_right", toggle=True)
        row.prop(s, "aisle_corners", toggle=True)
        layout.prop(s, "aisle_center_count")
        layout.prop(s, "aisle_custom")
        layout.prop(s, "corner_threshold")
        layout.separator()
        box = layout.box()
        box.label(text="Side access to the first row:")
        row = box.row(align=True)
        row.prop(s, "access_left")
        row.prop(s, "access_right")
        if s.access_left != 'NONE' or s.access_right != 'NONE':
            col = box.column(align=True)
            col.prop(s, "access_width")
            if 'RAMP' in (s.access_left, s.access_right):
                col.prop(s, "access_slope")
        layout.prop(s, "front_path")
        if len(s.stairs):
            box = layout.box()
            box.label(text="Where each stair starts:")
            iface_ = getattr(getattr(bpy.app, "translations", None), "pgettext_iface", None) or (lambda x: x)
            names = {"LEFT": iface_("left end"), "RIGHT": iface_("right end"), "MIDDLE": iface_("middle")}
            for i, st in enumerate(s.stairs):
                row = box.row(align=True)
                row.label(text="%s %d (%s)" % (iface_("Stair"), i + 1, names.get(st.pos, st.pos)), translate=False)
                sub = row.row(align=True)
                sub.enabled = not st.forced
                if st.forced:
                    sub.label(text="From row 1 (needs the front walkway)")
                else:
                    sub.prop(st, "bottom", text="Down to the ground" if st.bottom else "From row 1", toggle=True)


class TB_PT_around(bpy.types.Panel):
    bl_label = "4. Around the tribune"
    bl_parent_id = "TB_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tribune"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        c = S.active_tribune(context)
        return c is not None and c.tb.mode == 'GENERATED'

    def draw(self, context):
        s = S.active_tribune(context).tb
        layout = self.layout
        col = layout.column(align=True)
        col.prop(s, "stage_depth")
        col.prop(s, "front_walk")
        col.prop(s, "side_walk")
        col.prop(s, "back_walk")
        layout.label(text="Entrances / exits:")
        row = layout.row(align=True)
        row.prop(s, "entrance_left", toggle=True)
        row.prop(s, "entrance_right", toggle=True)
        row.prop(s, "entrance_front", toggle=True)
        row.prop(s, "entrance_back", toggle=True)
        layout.prop(s, "entrance_length")
        layout.prop(s, "booth")


class TB_PT_railing(bpy.types.Panel):
    bl_label = "5. Railing"
    bl_parent_id = "TB_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tribune"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        c = S.active_tribune(context)
        return c is not None and c.tb.mode == 'GENERATED'

    def draw(self, context):
        s = S.active_tribune(context).tb
        layout = self.layout
        row = layout.row(align=True)
        row.prop(s, "rail_back", toggle=True)
        row.prop(s, "rail_sides", toggle=True)
        row.prop(s, "rail_front", toggle=True)
        col = layout.column(align=True)
        col.prop(s, "rail_height")
        col.prop(s, "rail_post_spacing")
        col = layout.column(align=True)
        col.prop(s, "rail_hand")
        col.prop(s, "rail_post_size")
        b = layout.box()
        b.prop(s, "rail_mid")
        col = b.column(align=True)
        col.enabled = s.rail_mid
        col.prop(s, "rail_mid_height")
        col.prop(s, "rail_mid_size")
        b = layout.box()
        b.prop(s, "rail_infill")
        col = b.column(align=True)
        col.enabled = s.rail_infill
        col.prop(s, "rail_infill_spacing")
        col.prop(s, "rail_infill_width")
        col = b.column(align=True)
        col.enabled = s.rail_infill
        col.prop(s, "rail_infill_bottom")
        col.prop(s, "rail_infill_top")


class TB_PT_generate(bpy.types.Panel):
    bl_label = "6. Generate"
    bl_parent_id = "TB_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tribune"
    bl_options = {'HIDE_HEADER'}

    @classmethod
    def poll(cls, context):
        c = S.active_tribune(context)
        return c is not None and c.tb.mode == 'GENERATED'

    def draw(self, context):
        layout = self.layout
        s = S.active_tribune(context).tb
        layout.prop(s, "live", icon='HIDE_OFF')
        row = layout.row()
        row.scale_y = 1.6
        row.operator("tb.generate", icon='MOD_BUILD')
        layout.label(text="Generating again replaces everything it made before.", icon='INFO')


class TB_PT_custom(bpy.types.Panel):
    bl_label = "Own model"
    bl_parent_id = "TB_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tribune"

    @classmethod
    def poll(cls, context):
        c = S.active_tribune(context)
        return c is not None and c.tb.mode == 'CUSTOM'

    def draw(self, context):
        coll = S.active_tribune(context)
        s = coll.tb
        layout = self.layout
        b = box(layout, "1. Model", 'MESH_DATA')
        col = b.column(align=True)
        col.label(text="Ride centre = world origin.")
        col.label(text="The audience looks to -Y (front view).")
        b.operator("tb.add_selected", icon='ADD')
        n = len(S.model_objects(coll))
        b.label(text=T("Model objects") + ": %d" % n, translate=False)

        b = box(layout, "2. Seats", 'OUTLINER_OB_EMPTY')
        b.prop(s, "detect_mode")
        b.prop(s, "facing_mode")
        row = b.row(align=True)
        row.operator("tb.add_marker", text="Stage point at cursor", icon='PIVOT_CURSOR').kind = 'STAGE'
        b.operator("tb.detect_seats", icon='VIEWZOOM')
        row = b.row(align=True)
        row.operator("tb.add_seat", icon='ADD')
        row.operator("tb.renumber", icon='SORTSIZE')
        b.label(text=T("Seats") + ": %d" % len(S.objects(coll, 'SEAT')), translate=False)

        b = box(layout, "3. Walk area", 'MOD_DECIM')
        b.prop(s, "outline_margin")
        b.prop(s, "entrance_length")
        b.operator("tb.outline_default", icon='MESH_PLANE')
        b.operator("tb.add_marker", text="Ride booth at cursor", icon='MESH_CUBE').kind = 'BOOTH'
        col = b.column(align=True)
        col.prop(s, "nav_cell")
        col.prop(s, "nav_max_step")
        col.prop(s, "nav_clearance")
        col.prop(s, "nav_headroom")
        b.operator("tb.nav_auto", icon='MOD_REMESH')
        row = b.row(align=True)
        row.label(text="Selected objects are:")
        row = b.row(align=True)
        row.operator("tb.set_role", text="Model").role = 'NONE'
        row.operator("tb.set_role", text="Navmesh").role = 'NAV'
        row.operator("tb.set_role", text="Outline").role = 'OUTLINE'
        row.operator("tb.set_role", text="Ignore").role = 'IGNORE'


class TB_PT_seats(bpy.types.Panel):
    bl_label = "Seats and free places"
    bl_parent_id = "TB_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tribune"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return S.active_tribune(context) is not None

    def draw(self, context):
        coll = S.active_tribune(context)
        s = coll.tb
        layout = self.layout
        seats = S.objects(coll, 'SEAT')
        free = sum(1 for e in seats if e.tb_free)
        layout.label(text=T("Seats") + ": %d, " % len(seats) + T("used") + ": %d, " % (len(seats) - free) + T("free") + ": %d" % free,
                     translate=False)
        col = layout.column(align=True)
        row = col.row(align=True)
        row.prop(s, "free_group_min")
        row.prop(s, "free_group_max")
        row = col.row(align=True)
        row.prop(s, "free_gap_min")
        row.prop(s, "free_gap_max")
        col.prop(s, "free_seed")
        row = layout.row(align=True)
        row.operator("tb.random_free", icon='MOD_NOISE')
        row.operator("tb.random_free", text="All used", icon='CHECKMARK').clear = True
        row = layout.row(align=True)
        row.operator("tb.toggle_free", icon='ARROW_LEFTRIGHT')
        op = row.operator("tb.select_role", text="Select free", icon='RESTRICT_SELECT_OFF')
        op.role, op.free_only = 'SEAT', True
        ob = context.active_object
        if ob and ob.tb_role in ('SEAT', 'TARGET'):
            e = ob if ob.tb_role == 'SEAT' else ob.parent
            if e:
                b = layout.box()
                b.label(text=e.name, icon='OUTLINER_OB_EMPTY', translate=False)
                row = b.row(align=True)
                row.prop(e, "tb_row")
                row.prop(e, "tb_order")
                b.prop(e, "tb_free")
                b.label(text="Arrow = viewing direction, sphere = walk target", icon='INFO')
        layout.operator("tb.snap_targets", icon='SNAP_ON')


class TB_PT_materials(bpy.types.Panel):
    bl_label = "Materials"
    bl_parent_id = "TB_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tribune"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return S.active_tribune(context) is not None

    def draw(self, context):
        coll = S.active_tribune(context)
        layout = self.layout
        mats = []
        for ob in S.model_objects(coll):
            for sl in ob.material_slots:
                if sl.material and sl.material not in mats:
                    mats.append(sl.material)
        if not mats:
            layout.label(text="No materials yet.")
        for m in mats:
            row = layout.row(align=True)
            row.label(text=m.name, icon='MATERIAL', translate=False)
            bsdf = None
            if m.use_nodes and m.node_tree:
                bsdf = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
            if bsdf and not bsdf.inputs["Base Color"].is_linked:
                row.prop(bsdf.inputs["Base Color"], "default_value", text="")
            else:
                row.prop(m, "diffuse_color", text="")
            row.prop(m, "tb_double", text="", icon='MOD_SOLIDIFY')
            sub = layout.row(align=True)
            sub.separator(factor=3.0)
            sub.prop(m, "tb_flexi", text="Flexicolour")
            if m.tb_flexi == 'AUTO':
                ch = S.flexi_channel(m)
                sub.label(text=("Colour %d" % ch) if ch else "Fixed colour")
        s = coll.tb
        box = layout.box()
        box.label(text="Surface patterns (in the game)", icon='TEXTURE')
        box.prop(s, "floor_pattern")
        if s.floor_pattern != 'NONE':
            box.prop(s, "floor_pattern_size")
        box.prop(s, "seat_pattern")
        if s.seat_pattern != 'NONE':
            box.prop(s, "seat_pattern_size")
        layout.label(text="Colour, roughness and metal of the Principled BSDF are used.", icon='INFO')
        layout.label(text="Flexicolour: recolour in the game under the ride colours.", icon='INFO')


class TB_PT_check(bpy.types.Panel):
    bl_label = "Check and export"
    bl_parent_id = "TB_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tribune"

    @classmethod
    def poll(cls, context):
        return S.active_tribune(context) is not None

    def draw(self, context):
        layout = self.layout
        sc = context.scene
        row = layout.row(align=True)
        row.scale_y = 1.3
        row.operator("tb.check", icon='CHECKMARK')
        row.operator("tb.export", icon='EXPORT')
        if sc.tb_report:
            b = layout.box()
            col = b.column(align=True)
            for line in sc.tb_report.split("\n")[:14]:
                icon = 'ERROR' if line.startswith(("Error", "Fehler")) else ('INFO' if line.startswith(("Note", "Hinweis")) else 'NONE')
                col.label(text=line, icon=icon, translate=False)
        row = layout.row()
        row.scale_y = 1.5
        row.operator("tb.build", icon='PACKAGE')


class TB_PT_library(bpy.types.Panel):
    bl_label = "Library"
    bl_parent_id = "TB_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tribune"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        p = prefs(context)
        lib = bpy.path.abspath(p.library_dir)
        from .core import gamebuild
        items = gamebuild.list_index(lib)
        if not items:
            layout.label(text="The library is empty.")
        for t in items:
            row = layout.row(align=True)
            row.label(text="%s (%d)" % (t.get("name") or t["id"], t.get("seats", 0)), icon='OUTLINER_COLLECTION',
                      translate=False)
            row.operator("tb.library_remove", text="", icon='TRASH').tid = t["id"]
        layout.operator("tb.open_library", icon='FILE_FOLDER')
        b = layout.box()
        b.prop(p, "ovldata_dir")
        b.prop(p, "library_dir")
        b.prop(p, "yaw_sign")
        from .ops import _cobra_ok, missing_packages
        if not _cobra_ok():
            b.label(text="cobra-tools add-on is not active!", icon='ERROR')
        miss = missing_packages()
        if miss:
            b.label(text=T("Missing") + ": " + ", ".join(miss), icon='ERROR', translate=False)
            b.operator("tb.install_deps", icon='IMPORT')


CLASSES = [TB_UL_segments, TB_PT_main, TB_PT_shape, TB_PT_rows, TB_PT_aisles, TB_PT_around, TB_PT_railing, TB_PT_generate,
           TB_PT_custom, TB_PT_seats, TB_PT_materials, TB_PT_check, TB_PT_library]


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
