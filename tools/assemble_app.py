"""Puts the runnable app together: app/ + the generator core and data of the Blender add-on
(one source for both) + the Guest Spawner mod.

    python tools/assemble_app.py <output folder> [cobra-tools folder]

Without a cobra-tools folder the Guest Spawner is left out (it needs cobra-tools to be packed).
To run the app from source afterwards:  python <output folder>/server.py
"""
import os
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON = os.path.join(REPO, "blender_addon", "pc2_tribune_builder")


def assemble(out, cobra=None, log=print):
    ign = shutil.ignore_patterns("__pycache__", "*.pyc")
    if os.path.isdir(out):
        shutil.rmtree(out)
    shutil.copytree(os.path.join(REPO, "app"), out, ignore=ign)
    shutil.copytree(os.path.join(ADDON, "core"), os.path.join(out, "core"), ignore=ign)
    shutil.copytree(os.path.join(ADDON, "data"), os.path.join(out, "data"), ignore=ign)
    shutil.copy2(os.path.join(ADDON, "translations.py"), os.path.join(out, "translations_de.py"))
    if cobra:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import build_guestspawner
        build_guestspawner.build(cobra, os.path.join(out, "extras"), log=log)
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    print(assemble(os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else None))
