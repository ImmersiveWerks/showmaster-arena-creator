"""Live view: rebuilds the generated tribune (meshes only) shortly after a setting changed."""
import bpy
from bpy.app.handlers import persistent

_pending = set()


def request(coll):
    if coll is None or not getattr(coll, "tb", None) or not coll.tb.enabled or coll.tb.mode != 'GENERATED':
        return
    if not coll.tb.live:
        return
    _pending.add(coll.name)
    try:
        if not bpy.app.timers.is_registered(_run):
            bpy.app.timers.register(_run, first_interval=0.08)
    except Exception:
        pass


def _redraw():
    try:
        for win in bpy.context.window_manager.windows:
            for area in win.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
    except Exception:
        pass


def preview(context, coll):
    from . import scene as S
    from .core import geom
    s = coll.tb
    try:
        tmpl = S.seat_template(s, context)
        prm = S.gen_params(s)
        prm.update(seat_width=tmpl["width"], seat_depth=tmpl["depth"], sit=tmpl["sit"], seat_bottom=tmpl["bottom"])
        res = geom.generate(prm)
        if s.free_group_max >= s.free_group_min:
            geom.random_free(res["seats"], s.free_seed, s.free_group_min, s.free_group_max, s.free_gap_min,
                             s.free_gap_max)
        S.build_generated(context, coll, res, tmpl, preview=True)
    except Exception as e:      # keep the last good view and show why the new one failed
        msg = str(e) if isinstance(e, geom.GenError) else "%s: %s" % (type(e).__name__, e)
        try:
            context.scene.tb_report = bpy.app.translations.pgettext_rpt("Live view") + ": " + msg
        except Exception:
            pass
        return False
    info = res["info"]
    used = sum(1 for x in res["seats"] if not x["free"])
    T = bpy.app.translations.pgettext_rpt
    lines = [T("Live view") + ": %d " % info["seats"] + T("seats") + " (%d " % used + T("used") + "), "
             + T("walking lane") + " %.2f m" % info["lane"]]
    lines += [T("Note") + ": " + w for w in res["warnings"]]
    lines.append(T("Press 'Generate tribune' to create the seat points for the export."))
    try:
        context.scene.tb_report = "\n".join(lines)
    except Exception:
        pass
    return True


def _run():
    names = list(_pending)
    _pending.clear()
    for n in names:
        coll = bpy.data.collections.get(n)
        if coll is not None and coll.tb.enabled:
            preview(bpy.context, coll)
    _redraw()
    return None


def _room_owners(idb):
    out = []
    for c in bpy.data.collections:
        s = getattr(c, "tb", None)
        if not s or not s.enabled or s.mode != 'GENERATED' or s.footprint != 'ROOM' or not s.live:
            continue
        ro = s.room_object
        if ro is None:
            continue
        if idb == ro or (ro.data is not None and idb == ro.data):
            out.append(c)
    return out


@persistent
def _on_depsgraph(scene, depsgraph):
    """the room mesh was edited: update the tribunes standing in it"""
    try:
        for u in depsgraph.updates:
            idb = getattr(u.id, "original", u.id)
            if isinstance(idb, (bpy.types.Object, bpy.types.Mesh)):
                for c in _room_owners(idb):
                    request(c)
    except Exception:
        pass


def register():
    if _on_depsgraph not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)


def unregister():
    if _on_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph)
