"""Builds the Windows program and its installer from this repository (on Windows).

    py -3.12 packaging/build_exe.py

The GitHub Actions workflow .github/workflows/release.yml runs exactly this for every release.

Needs: Python 3.11 or 3.12 (64 bit) for building only, internet (pip, cobra-tools from GitHub),
and Inno Setup 6 (https://jrsoftware.org/isdl.php) for the Setup.exe. End users need none of this.

Result:
    dist/ShowMaster Arena Creator/ShowMaster Arena Creator.exe   (the program folder)
    output/ShowMaster_Arena_Creator_Setup_<version>.exe          (the installer, if Inno Setup is installed)
    output/ShowMaster_Arena_Creator_<version>_portable.zip       (the program folder as zip)
"""
import ast
import glob
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
APP_SRC = os.path.join(REPO, "app")
sys.path.insert(0, os.path.join(REPO, "tools"))
NAME = "ShowMaster Arena Creator"
COBRA_COMMIT = "2dd9d1445608d6171c1ec1f2333cefb4d81a1317"
COBRA_URL = "https://github.com/OpenNaja/cobra-tools/archive/%s.zip" % COBRA_COMMIT
COBRA_SKIP = {".git", ".github", "docs", "tests", "dumps", "experimentals", "logs", "__pycache__"}
WORK = os.path.join(HERE, "work")


def step(msg):
    print("\n=== " + msg)


def run(cmd, **kw):
    print("> " + " ".join('"%s"' % c if " " in c else c for c in cmd))
    subprocess.check_call(cmd, **kw)


def version():
    with open(os.path.join(APP_SRC, "server.py"), encoding="utf-8") as f:
        return re.search(r'VERSION = "([^"]+)"', f.read()).group(1)


def get_cobra():
    """cobra-tools: TB_COBRA_SRC (a folder), else the pinned version from GitHub"""
    src = os.environ.get("TB_COBRA_SRC")
    if src and os.path.isdir(os.path.join(src, "generated")):
        return src
    dst = os.path.join(WORK, "cobra-src")
    if os.path.isdir(os.path.join(dst, "generated")):
        return dst
    step("Downloading cobra-tools %s" % COBRA_COMMIT[:9])
    os.makedirs(WORK, exist_ok=True)
    zpath = os.path.join(WORK, "cobra.zip")
    urllib.request.urlretrieve(COBRA_URL, zpath)
    with zipfile.ZipFile(zpath) as z:
        for info in z.infolist():
            parts = info.filename.split("/", 1)
            if len(parts) < 2 or not parts[1] or info.is_dir():
                continue
            target = os.path.join(dst, *parts[1].split("/"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(info) as a, open(target, "wb") as b:
                shutil.copyfileobj(a, b)
    return dst


def copy_tree(src, dst, skip=()):
    def ignore(d, names):
        return [n for n in names if n in skip or n == "__pycache__" or n.endswith(".pyc")]
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=ignore)


def stdlib_imports(*roots):
    """standard library modules that the plain-folder code imports (PyInstaller cannot see them)"""
    names = set()
    std = set(getattr(sys, "stdlib_module_names", ()))
    for root in roots:
        for path in glob.glob(os.path.join(root, "**", "*.py"), recursive=True):
            try:
                tree = ast.parse(open(path, "rb").read())
            except (SyntaxError, ValueError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    mods = [node.module]
                else:
                    continue
                for m in mods:
                    top = m.split(".")[0]
                    if top in std and top not in ("tkinter", "test", "idlelib", "turtledemo"):
                        names.add(m)
    return sorted(names)


def find_iscc():
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
        if base:
            p = os.path.join(base, "Inno Setup 6", "ISCC.exe")
            if os.path.isfile(p):
                return p
    return shutil.which("iscc")


def main():
    if sys.version_info[:2] not in ((3, 11), (3, 12)) or sys.maxsize < 2 ** 32:
        sys.exit("Please build with 64-bit Python 3.11 or 3.12 (this is %s)." % sys.version.split()[0])
    ver = version()
    step("Version %s - installing build tools" % ver)
    run([sys.executable, "-m", "pip", "install", "-r", os.path.join(HERE, "requirements-build.txt")])

    step("Collecting files")
    stage = os.path.join(WORK, "stage")
    os.makedirs(stage, exist_ok=True)
    cobra = get_cobra()
    copy_tree(cobra, os.path.join(stage, "cobra-tools"), COBRA_SKIP)
    import assemble_app
    assemble_app.assemble(os.path.join(stage, "app"), os.path.join(stage, "cobra-tools"))
    # cobra-tools is shipped as plain, unmodified source files; the standard library modules it uses must be
    # inside the program
    hidden = stdlib_imports(os.path.join(stage, "app"), os.path.join(stage, "cobra-tools"))
    print("%d standard library modules for the plain-folder code" % len(hidden))

    step("Building the program with PyInstaller")
    sep = ";" if os.name == "nt" else ":"
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--onedir",
           "--name", NAME, "--icon", os.path.join(HERE, "icon.ico"),
           "--distpath", os.path.join(HERE, "dist"), "--workpath", os.path.join(WORK, "pyinstaller"),
           "--specpath", WORK,
           "--add-data", os.path.join(stage, "app") + sep + "app",
           "--add-data", os.path.join(stage, "cobra-tools") + sep + "cobra-tools",
           "--collect-all", "webview", "--collect-all", "imageio", "--collect-all", "bitarray",
           "--collect-submodules", "numpy", "--collect-submodules", "PIL"]
    for h in hidden:
        cmd += ["--hidden-import", h]
    cmd.append(os.path.join(HERE, "arena_creator.py"))
    env = dict(os.environ, TB_BUNDLE_ANALYSIS_ONLY="")
    run(cmd, env=env)
    prog = os.path.join(HERE, "dist", NAME)
    for doc in ("README.txt", "LIES MICH.txt"):
        shutil.copy2(os.path.join(HERE, doc), prog)
    shutil.copy2(os.path.join(REPO, "LICENSE"), os.path.join(prog, "LICENSE.txt"))
    shutil.copy2(os.path.join(REPO, "THIRD_PARTY.md"), os.path.join(prog, "THIRD_PARTY.md"))

    out = os.path.join(HERE, "output")
    os.makedirs(out, exist_ok=True)
    step("Portable zip")
    zpath = os.path.join(out, "ShowMaster_Arena_Creator_%s_portable.zip" % ver)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for r, _d, fs in os.walk(prog):
            for f in fs:
                full = os.path.join(r, f)
                z.write(full, os.path.join(NAME, os.path.relpath(full, prog)))
    print(zpath)

    iscc = find_iscc()
    if not iscc:
        print("\nInno Setup 6 not found: no Setup.exe. Install it from https://jrsoftware.org/isdl.php and run again.")
        return
    step("Building the installer with Inno Setup")
    run([iscc, "/DMyAppVersion=" + ver, "/DSourceDir=" + prog, "/O" + out, os.path.join(HERE, "installer.iss")])
    step("Checksums")
    import hashlib
    lines = []
    for f in sorted(os.listdir(out)):
        if f.endswith((".exe", ".zip")):
            h = hashlib.sha256(open(os.path.join(out, f), "rb").read()).hexdigest()
            lines.append("%s  %s" % (h, f))
    with open(os.path.join(out, "SHA256SUMS.txt"), "w", encoding="ascii") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("\nDone: " + out)


if __name__ == "__main__":
    main()
