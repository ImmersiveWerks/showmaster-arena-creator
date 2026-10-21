bl_info = {
    "name": "PC2 Tribune Builder",
    "author": "ImmersiveWerks",
    "version": (0, 26, 0),
    "blender": (4, 2, 0),
    "location": "3D View > Sidebar (N) > Tribune",
    "description": "Generate or import grandstands and install them as working show rides in Planet Coaster 2 "
                   "(needs cobra-tools in Blender; ACSE, ForgeUtils and the Silver Screen DLC in the game)",
    "warning": "Beta",
    "category": "Import-Export",
}

if "bpy" in locals():
    import importlib
    for _m in ("props", "scene", "live", "ops", "ui", "translations"):
        if _m in locals():
            importlib.reload(locals()[_m])

import bpy  # noqa: E402

from . import props, scene, live, ops, ui, translations  # noqa: E402,F401


def register():
    translations.register()
    props.register()
    ops.register()
    ui.register()
    live.register()


def unregister():
    live.unregister()
    ui.unregister()
    ops.unregister()
    props.unregister()
    translations.unregister()
