"""Builds the Guest Spawner mod folder (Main.ovl + Manifest.xml) from guestspawner/.

    python tools/build_guestspawner.py <cobra-tools folder> <output folder>

The UI script (guestspawner/ui/...) is put into a UI package (.ppuipkg) next to the Lua database,
then everything is packed with cobra-tools.
"""
import base64
import os
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "blender_addon", "pc2_tribune_builder"))
MOD = "Mod_GuestSpawner"


def build(cobra, out_dir, log=print):
    from core import gamebuild
    src = os.path.join(REPO, "guestspawner")
    work = tempfile.mkdtemp(prefix="gs_")
    main = os.path.join(work, "Main")
    shutil.copytree(os.path.join(src, "src", "Main"), main)
    ui_root = os.path.join(src, "ui")
    xml = '<PPUIPKGRoot game="Planet Coaster 2">\n\t<basic_path>%s/Main</basic_path>\n\t<files>\n' % MOD
    for r, _d, fs in os.walk(ui_root):
        for f in sorted(fs):
            full = os.path.join(r, f)
            rel = os.path.relpath(full, ui_root).replace("\\", "/")
            data = open(full, "rb").read()
            xml += ('\t\t<ppuipkgfile file_size="%d">\n\t\t\t<file_name>%s</file_name>\n'
                    '\t\t\t<file_content encoding="base64">%s</file_content>\n\t\t</ppuipkgfile>\n'
                    % (len(data), rel, base64.b64encode(data).decode()))
    xml += '\t</files>\n\t<icondata />\n</PPUIPKGRoot>\n'
    with open(os.path.join(main, "guestspawner.ppuipkg"), "w", encoding="utf-8") as f:
        f.write(xml)
    target = os.path.join(out_dir, MOD)
    os.makedirs(target, exist_ok=True)
    with gamebuild.cobra_imports(cobra):
        gamebuild.pack(main, os.path.join(target, "Main.ovl"), log=log, root=cobra)
    shutil.copy2(os.path.join(src, "Manifest.xml"), os.path.join(target, "Manifest.xml"))
    shutil.rmtree(work, ignore_errors=True)
    return target


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    print(build(os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])))
