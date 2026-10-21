import os

import bpy
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty,
                       StringProperty)

ROLES = [
    ('NONE', "Model", "Part of the visible tribune model"),
    ('SEAT', "Seat", "Sit point of a guest (arrow = viewing direction)"),
    ('TARGET', "Walk target", "Where the guest walks to before sitting down (child of a seat)"),
    ('NAV', "Navmesh", "Area guests can walk on (not visible in the game)"),
    ('OUTLINE', "Outline", "Footprint of the ride; edges marked as seam are entrances/exits"),
    ('BOOTH', "Ride booth", "Position of the ride operator booth"),
    ('STAGE', "Stage point", "The point the audience looks at (used to turn detected seats)"),
    ('IGNORE', "Ignore", "Not exported"),
]


def _default_library():
    try:
        base = bpy.utils.user_resource('CONFIG')
    except Exception:
        base = os.path.expanduser("~")
    return os.path.join(base, "pc2_tribune_builder", "library")


class TB_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    ovldata_dir: StringProperty(
        name="ovldata folder", subtype='DIR_PATH',
        description="Planet Coaster 2 > Win64 > ovldata. The mod is installed here",
        default=r"C:\Program Files (x86)\Steam\steamapps\common\Planet Coaster 2\Win64\ovldata")
    library_dir: StringProperty(
        name="Library folder", subtype='DIR_PATH', default=_default_library(),
        description="Exported tribunes are kept here. Every build packs all tribunes of the library into the mod")
    yaw_sign: EnumProperty(
        name="Seat rotation", default='1',
        items=[('1', "Normal", "Default"),
               ('-1', "Mirrored", "Use this only if guests sit turned the wrong way on angled tribunes")],
        description="Direction of the seat rotation in the game")

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "ovldata_dir")
        col.prop(self, "library_dir")
        col.prop(self, "yaw_sign")


def prefs(context=None):
    context = context or bpy.context
    return context.preferences.addons[__package__].preferences


def _upd(self, context):
    from . import live
    live.request(self.id_data)


class TB_Segment(bpy.types.PropertyGroup):
    kind: EnumProperty(update=_upd, name="Type", items=[('STRAIGHT', "Straight", "Straight piece"), ('ARC', "Arc", "Curved piece")],
                       default='STRAIGHT')
    length: FloatProperty(update=_upd, name="Length", default=12.0, min=0.5, max=300.0, unit='LENGTH', precision=2)
    turn: FloatProperty(update=_upd, name="Angle", default=0.0, min=-135.0, max=135.0, precision=1,
                        description="Bend in degrees at the start of this piece. Positive = around the show area")
    radius: FloatProperty(update=_upd, name="Radius", default=12.0, min=1.0, max=500.0, unit='LENGTH', precision=2,
                          description="Radius of the front line of the arc")
    angle: FloatProperty(update=_upd, name="Arc angle", default=90.0, min=-300.0, max=300.0, precision=1,
                         description="How far the arc bends, in degrees. Positive = around the show area")


class TB_Stair(bpy.types.PropertyGroup):
    """one stair of the generated tribune (filled by the generator, sorted along the tribune)"""
    pos: StringProperty(default="MIDDLE")
    forced: BoolProperty(default=False)
    bottom: BoolProperty(update=_upd, name="Down to the ground", default=True,
                         description="On: the stair goes down to the ground in front of the tribune. "
                                     "Off: it starts at the first row")


class TB_Settings(bpy.types.PropertyGroup):
    enabled: BoolProperty(default=False)
    mode: EnumProperty(name="Kind", items=[('GENERATED', "Generator", "Built by the generator"),
                                           ('CUSTOM', "Own model", "Your own tribune model")], default='GENERATED')
    tid: StringProperty(name="ID", description="Internal name: lowercase letters, digits and _ (3-31 characters)")
    uid: StringProperty(name="UID", description="Internal: tells this tribune apart from others in the library")
    auto_name: BoolProperty(name="Automatic name", default=True,
                            description="Name in the game: 'Show Arena <seats>', numbered if several have the same "
                                        "seat count. Set when saving to the library")
    game_name: StringProperty(name="Name in game", default="My tribune")
    description: StringProperty(name="Description", default="")

    live: BoolProperty(name="Live view", default=True, update=_upd,
                       description="Shows the tribune while you change the settings (seat points and export "
                                   "data are made with 'Generate tribune')")
    # ----- footprint
    footprint: EnumProperty(update=_upd, name="Shape from", default='PIECES', items=[
        ('PIECES', "Front line", "Build the front line from straight pieces and arcs"),
        ('ROOM', "Room", "Draw a room; the tribune stands against the walls marked as sharp")])
    staff_path: FloatProperty(update=_upd, name="Staff path", default=1.2, min=0.0, max=5.0, unit='LENGTH', precision=2,
                              description="Free path along the walls (behind and beside the tribune) so the ride "
                                          "operator can reach the booth")
    room_object: PointerProperty(update=_upd, name="Room", type=bpy.types.Object,
                                 poll=lambda self, o: o.type == 'MESH',
                                 description="Mesh with the room outline (a face or a closed loop of edges)")
    segments: CollectionProperty(type=TB_Segment)
    stairs: CollectionProperty(type=TB_Stair)
    access_left: EnumProperty(update=_upd, name="Left", default='NONE',
                              items=[('NONE', "None", "No side access"), ('RAMP', "Ramp", "Ramp from the ground to the first row"),
                                     ('STAIRS', "Stairs", "Stairs from the ground to the first row")],
                              description="Side access to the first row at the left end")
    access_right: EnumProperty(update=_upd, name="Right", default='NONE',
                               items=[('NONE', "None", "No side access"), ('RAMP', "Ramp", "Ramp from the ground to the first row"),
                                      ('STAIRS', "Stairs", "Stairs from the ground to the first row")],
                               description="Side access to the first row at the right end")
    access_width: FloatProperty(update=_upd, name="Access width", default=1.2, min=0.6, max=4.0, unit='LENGTH', precision=2,
                                description="Width of the side access (at most the walkway of the first row)")
    access_slope: FloatProperty(update=_upd, name="Ramp gradient", default=12.0, min=3.0, max=30.0, precision=1, subtype='PERCENTAGE',
                                description="Steepness of the ramp in percent; less is longer")
    single_guests: BoolProperty(name="Guests one by one", default=True,
                                description="Guests go onto the tribune one by one instead of as a group side by side "
                                            "(groups walking side by side can slip through the rows). Test in the game")
    floor_pattern: EnumProperty(name="Floor pattern", default='NONE',
                                items=[('NONE', "None", "Smooth floor"),
                                       ('DIAMOND', "Diamond plate", "Metal diamond plate (raised ribs)"),
                                       ('STUDS', "Round studs", "Floor with round studs"),
                                       ('CONCRETE', "Concrete", "Concrete with grunge noise")],
                                description="Bump pattern (normal map) of the floors and steps in the game")
    floor_pattern_size: FloatProperty(name="Pattern size", default=0.6, min=0.1, max=5.0, unit='LENGTH', precision=2,
                                      description="Size of one pattern tile on the floor")
    seat_pattern: EnumProperty(name="Seat surface", default='NONE',
                               items=[('NONE', "None", "Smooth plastic"),
                                      ('SCRATCHED', "Scratched plastic", "Plastic with scratches and wear (roughness map)")],
                               description="Surface of the seats in the game")
    seat_pattern_size: FloatProperty(name="Scratch size", default=0.5, min=0.05, max=3.0, unit='LENGTH', precision=2,
                                     description="Size of one scratch pattern tile on the seats (smaller = finer scratches)")
    front_path: BoolProperty(update=_upd, name="Front walkway", default=True,
                             description="Walkway along the front of the tribune that connects the bottoms of the stairs. "
                                         "Without it only the end stairs can go down to the ground")
    seg_index: IntProperty(default=0)
    arc_step: FloatProperty(update=_upd, name="Arc smoothness", default=7.5, min=2.0, max=20.0,
                            description="Degrees per arc piece (smaller = rounder, more geometry)")
    # ----- rows
    rows: IntProperty(update=_upd, name="Rows", default=5, min=1, max=40)
    row_depth: FloatProperty(update=_upd, name="Row depth", default=1.25, min=0.6, max=3.0, unit='LENGTH', precision=2,
                             description="Depth of one row step (seat + walking lane)")
    seat_height: FloatProperty(update=_upd, name="Seat height", default=-0.04, min=-0.4, max=0.4, unit='LENGTH', precision=3,
                               description="Raise (+) or lower (-) all seats against the seat model")
    first_row_depth: FloatProperty(update=_upd, name="First row depth", default=1.6, min=0.6, max=4.0, unit='LENGTH',
                                   precision=2, description="Depth of the first row; deeper by default, so there is "
                                                            "more room in front of the seats")
    row_rise: FloatProperty(update=_upd, name="Row rise", default=0.35, min=0.0, max=1.2, unit='LENGTH', precision=2,
                            description="Height difference between two rows")
    first_row_height: FloatProperty(update=_upd, name="First row height", default=0.35, min=0.0, max=5.0, unit='LENGTH', precision=2)
    # ----- seats
    seat_source: EnumProperty(update=_upd, name="Seat model", items=[('PLACEHOLDER', "Built-in seat", "Stadium seat with a floor bracket"),
                                                         ('OBJECT', "Own seat", "Any mesh: origin on the floor, guest looks to -Y")],
                              default='PLACEHOLDER')
    seat_object: PointerProperty(update=_upd, name="Seat object", type=bpy.types.Object,
                                 poll=lambda self, o: o.type == 'MESH')
    seat_gap: FloatProperty(update=_upd, name="Gap between seats", default=0.06, min=0.0, max=1.0, unit='LENGTH', precision=2)
    seat_back_gap: FloatProperty(update=_upd, name="Back offset", default=0.05, min=-0.6, max=1.0, unit='LENGTH', precision=2,
                                 description="Seat back to the back edge of the row. Negative: the seat hangs over the "
                                             "next step (like wall-mounted stadium seats)")
    clearance: FloatProperty(update=_upd, name="Knee room", default=0.2, min=0.05, max=1.0, unit='LENGTH', precision=2,
                             description="Free space between the seat front and the walking lane")
    # ----- aisles
    aisle_width: FloatProperty(update=_upd, name="Stair width", default=1.2, min=0.6, max=5.0, unit='LENGTH', precision=2)
    aisle_left: BoolProperty(update=_upd, name="Left", default=True, description="Stairs at the left end")
    aisle_right: BoolProperty(update=_upd, name="Right", default=True, description="Stairs at the right end")
    aisle_center_count: IntProperty(update=_upd, name="Middle stairs", default=0, min=0, max=20,
                                    description="Evenly spaced stairs between the ends")
    aisle_corners: BoolProperty(update=_upd, name="At corners", default=True, description="Stairs at every corner of the front line")
    aisle_custom: StringProperty(update=_upd, name="Extra stairs at",
                                 description="Comma separated positions in metres from the start of the front line, "
                                             "e.g. 4.5, 12")
    corner_threshold: FloatProperty(update=_upd, name="Corner from", default=20.0, min=5.0, max=90.0, precision=0,
                                    description="Bends larger than this angle (degrees) count as corners")
    # ----- around
    stage_depth: FloatProperty(update=_upd, name="Show area depth", default=0.0, min=0.0, max=80.0, unit="LENGTH", precision=2,
                               description="Extra walkable area in front of the walkway that belongs to the ride (0 = only the walkway in front of the seats)")
    front_walk: FloatProperty(update=_upd, name="Front walkway", default=1.5, min=0.5, max=10.0, unit='LENGTH', precision=2)
    side_walk: FloatProperty(update=_upd, name="Side walkways", default=1.5, min=0.0, max=10.0, unit='LENGTH', precision=2)
    back_walk: FloatProperty(update=_upd, name="Back walkway", default=1.2, min=0.0, max=10.0, unit='LENGTH', precision=2)
    entrance_left: BoolProperty(update=_upd, name="Left", default=True)
    entrance_right: BoolProperty(update=_upd, name="Right", default=True)
    entrance_front: BoolProperty(update=_upd, name="Front", default=False)
    entrance_back: BoolProperty(update=_upd, name="Back", default=False)
    entrance_length: FloatProperty(update=_upd, name="Side entrance length", default=6.0, min=0.0, max=100.0, unit='LENGTH',
                                   precision=2, description="Side entrances start at the front corner (0 = whole side)")
    booth: EnumProperty(update=_upd, name="Ride booth", items=[('back', "Behind", ""), ('left', "Left", ""), ('right', "Right", "")],
                        default='back')
    rail_back: BoolProperty(update=_upd, name="Back railing", default=True)
    rail_sides: BoolProperty(update=_upd, name="Side railings", default=True)
    rail_front: BoolProperty(update=_upd, name="Front railing", default=False,
                             description="Railing along the front edge of the first row (open at the stairs)")
    rail_height: FloatProperty(update=_upd, name="Railing height", default=1.0, min=0.3, max=2.0, unit='LENGTH', precision=2)
    rail_post_spacing: FloatProperty(update=_upd, name="Post spacing", default=1.5, min=0.3, max=10.0, unit='LENGTH', precision=2,
                                     description="Distance between the vertical posts of the railings")
    rail_hand: FloatProperty(update=_upd, name="Handrail thickness", default=0.06, min=0.01, max=0.3, unit='LENGTH', precision=3)
    rail_post_size: FloatProperty(update=_upd, name="Post thickness", default=0.05, min=0.01, max=0.4, unit='LENGTH', precision=3)
    rail_mid: BoolProperty(update=_upd, name="Middle rail", default=True)
    rail_mid_size: FloatProperty(update=_upd, name="Middle rail thickness", default=0.03, min=0.005, max=0.2, unit='LENGTH',
                                 precision=3)
    rail_mid_height: FloatProperty(update=_upd, name="Middle rail height", default=0.5, min=0.05, max=2.0, unit='LENGTH',
                                   precision=2, description="Height of the middle rail above the steps")
    rail_infill: BoolProperty(update=_upd, name="Infill bars", default=False,
                              description="Thin vertical bars between the posts (grid look). Each bar is a single "
                                          "double-sided face to save polygons")
    rail_infill_spacing: FloatProperty(update=_upd, name="Bar spacing", default=0.12, min=0.04, max=1.0, unit='LENGTH',
                                       precision=3)
    rail_infill_bottom: FloatProperty(update=_upd, name="Bars from", default=0.1, min=0.0, max=2.0, unit='LENGTH',
                                      precision=2, description="Lower end of the infill bars, height above the steps")
    rail_infill_top: FloatProperty(update=_upd, name="Bars to", default=1.0, min=0.0, max=2.0, unit='LENGTH',
                                   precision=2, description="Upper end of the infill bars, height above the steps "
                                                            "(at most up to the handrail)")
    rail_infill_width: FloatProperty(update=_upd, name="Bar width", default=0.02, min=0.003, max=0.2, unit='LENGTH',
                                     precision=3)

    # ----- free seats
    free_seed: IntProperty(update=_upd, name="Seed", default=7, min=0)
    free_group_min: IntProperty(update=_upd, name="Group min", default=2, min=1, max=20)
    free_group_max: IntProperty(update=_upd, name="Group max", default=6, min=1, max=40)
    free_gap_min: IntProperty(update=_upd, name="Gap min", default=1, min=0, max=10)
    free_gap_max: IntProperty(update=_upd, name="Gap max", default=2, min=0, max=10)

    # ----- own model tools
    detect_mode: EnumProperty(name="Seats are", items=[
        ('PARTS', "Loose parts", "Every loose part of the selected meshes is one seat"),
        ('OBJECTS', "Objects", "Every selected mesh object is one seat")], default='PARTS')
    facing_mode: EnumProperty(name="Facing", items=[
        ('ROW', "Along the rows", "Perpendicular to each row, towards the stage point (or -Y)"),
        ('STAGE', "Stage point", "Every seat looks at the stage point"),
        ('AXIS', "-Y", "All seats look to -Y"),
        ('OBJECT', "Object -Y", "Every seat object looks along its own -Y axis")], default='ROW')
    nav_cell: FloatProperty(name="Grid", default=0.1, min=0.04, max=0.5, unit='LENGTH', precision=2,
                            description="Sample distance of the automatic navmesh")
    nav_max_step: FloatProperty(name="Max. step", default=0.25, min=0.05, max=0.6, unit='LENGTH', precision=2,
                                description="Higher steps count as walls (row risers), lower ones as stairs")
    nav_clearance: FloatProperty(name="Knee room", default=0.2, min=0.0, max=1.0, unit='LENGTH', precision=2)
    nav_headroom: FloatProperty(name="Head room", default=1.8, min=0.5, max=4.0, unit='LENGTH', precision=2)
    outline_margin: FloatProperty(name="Margin", default=1.5, min=0.0, max=20.0, unit='LENGTH', precision=2)


def _poll_tribune(self, coll):
    return coll.tb.enabled


def register():
    bpy.utils.register_class(TB_Preferences)
    bpy.utils.register_class(TB_Segment)
    bpy.utils.register_class(TB_Stair)
    bpy.utils.register_class(TB_Settings)
    bpy.types.Collection.tb = PointerProperty(type=TB_Settings)
    bpy.types.Scene.tb_active = PointerProperty(name="Tribune", type=bpy.types.Collection, poll=_poll_tribune)
    bpy.types.Scene.tb_report = StringProperty(default="")
    bpy.types.Object.tb_role = EnumProperty(name="Role", items=ROLES, default='NONE')
    bpy.types.Object.tb_generated = BoolProperty(default=False)
    bpy.types.Object.tb_seatmesh = BoolProperty(name="Seat geometry", default=False,
                                                description="This mesh contains seats (ignored as floor for the navmesh)")
    bpy.types.Object.tb_row = IntProperty(name="Row", default=1, min=1)
    bpy.types.Object.tb_order = IntProperty(name="Order", default=1, min=1,
                                            description="Position in the row (1 = left as seen by the audience)")
    bpy.types.Object.tb_free = BoolProperty(name="Free", default=False, description="Seat stays empty")
    bpy.types.Object.tb_back = FloatProperty(default=0.3)
    bpy.types.Object.tb_front = FloatProperty(default=0.25)
    bpy.types.Object.tb_halfw = FloatProperty(default=0.26)
    bpy.types.Object.tb_floor = FloatProperty(default=0.0)
    bpy.types.Material.tb_double = BoolProperty(name="Double-sided", default=False,
                                                description="Show both sides (for single-surface parts like seat shells)")
    bpy.types.Material.tb_flexi = EnumProperty(
        name="Flexicolour", default='AUTO',
        items=[('AUTO', "Automatic", "Seats 1, railing 2, structure 3, stairs 4; own materials not recolourable"),
               ('0', "Fixed colour", "Not recolourable in the game"),
               ('1', "Colour 1", "Recolourable in the game with ride colour 1"),
               ('2', "Colour 2", "Recolourable in the game with ride colour 2"),
               ('3', "Colour 3", "Recolourable in the game with ride colour 3"),
               ('4', "Colour 4", "Recolourable in the game with ride colour 4")],
        description="Recolour this material in the game (the colour set here is the default)")


def unregister():
    for attr in ("tb_double", "tb_flexi"):
        if hasattr(bpy.types.Material, attr):
            delattr(bpy.types.Material, attr)
    for attr in ("tb_role", "tb_generated", "tb_seatmesh", "tb_row", "tb_order", "tb_free", "tb_back", "tb_front",
                 "tb_halfw", "tb_floor"):
        if hasattr(bpy.types.Object, attr):
            delattr(bpy.types.Object, attr)
    del bpy.types.Scene.tb_report
    del bpy.types.Scene.tb_active
    del bpy.types.Collection.tb
    bpy.utils.unregister_class(TB_Settings)
    bpy.utils.unregister_class(TB_Stair)
    bpy.utils.unregister_class(TB_Segment)
    bpy.utils.unregister_class(TB_Preferences)
