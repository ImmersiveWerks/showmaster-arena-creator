"""ShowMaster Arena Creator - standalone app of the PC2 Tribune Builder (generator only).

A small local web server: the user interface runs in a browser window (web/), the generator, checks,
library and mod build are the same Python code as in the Blender add-on (core/).
Start with "ShowMaster Arena Creator.pyw" (Windows) or: python server.py
"""
import ast
import base64
import glob
import io
import json
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

APP = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(APP)
WEB = os.path.join(APP, "web")
sys.path.insert(0, APP)

from core import assemble, geom, navcheck  # noqa: E402

VERSION = "0.26.1"
IS_WIN = os.name == "nt"


# ------------------------------------------------------------------ texts (German from the add-on's table)


def _load_de():
    p = os.path.join(APP, "translations_de.py")
    if not os.path.isfile(p):
        return {}
    tree = ast.parse(open(p, encoding="utf-8").read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "DE":
            return ast.literal_eval(node.value)
    return {}


DE = _load_de()
from i18n_srv import MSG  # noqa: E402

LANGS = ("de", "en", "fr", "es", "zh", "ja")
LANG = "de"          # language of the person using the app (set with every request)
_SPEC = r"(%(?:\.\d+)?\d*[sdf]|%%)"
_RX = []
for _en in set(DE) | set(MSG):
    if "%" in _en:
        rx = "".join("(.+?)" if re.fullmatch(r"%(?:\.\d+)?\d*[sdf]", x) else "%" if x == "%%" else re.escape(x)
                     for x in re.split(_SPEC, _en))
        _RX.append((re.compile("^" + rx + "$"), _en))


def _target(en, lang):
    if lang == "en":
        return en
    t = (MSG.get(en) or {}).get(lang)
    if t is None and lang == "de":
        t = DE.get(en)
    return t


def tr(msg, lang=None):
    """a message of the generator / build / server (English, maybe with numbers in it) in the app language"""
    lang = lang or LANG
    msg = str(msg)
    t = _target(msg, lang)
    if t is not None:
        return t
    for rx, en in _RX:
        m = rx.match(msg)
        if m:
            t = _target(en, lang)
            if t is None:
                return msg
            vals = list(m.groups())
            return re.sub(_SPEC, lambda _m: "%" if _m.group(0) == "%%" else (vals.pop(0) if vals else ""), t)
    return msg


def de(msg):
    return tr(msg)


# ------------------------------------------------------------------ settings and folders


def _appdata():
    base = os.environ.get("APPDATA") if IS_WIN else None
    return os.path.join(base or os.path.expanduser("~"), "ShowMaster Arena Creator" if IS_WIN else ".showmaster_arena")


SETTINGS_FILE = os.path.join(_appdata(), "settings.json")
_OLD_SETTINGS = os.path.join(os.environ.get("APPDATA") or "", "PC2 Tribune Builder", "settings.json")


def _blender_dirs():
    base = os.environ.get("APPDATA")
    if not base:
        return []
    vers = glob.glob(os.path.join(base, "Blender Foundation", "Blender", "*"))

    def key(p):
        try:
            return tuple(int(x) for x in os.path.basename(p).split("."))
        except ValueError:
            return (0,)
    return sorted(vers, key=key, reverse=True)


def addon_library():
    """the library of the Blender add-on, so app and add-on share their tribunes (both build all of them)"""
    for v in _blender_dirs():
        p = os.path.join(v, "config", "pc2_tribune_builder", "library")
        if os.path.isdir(p):
            return p
    return None


def cobra_ok(d):
    return bool(d) and os.path.isfile(os.path.join(d, "generated", "formats", "ovl", "__init__.py"))


def find_cobra(pref=None):
    # the copy that comes with the program first, then a folder set in the settings or the Blender add-on's
    cands = [os.path.join(ROOT, "cobra-tools"), os.environ.get("TB_COBRA"), pref]
    cands += glob.glob(os.path.join(ROOT, "cobra-tools*"))
    for v in _blender_dirs():
        cands += glob.glob(os.path.join(v, "scripts", "addons", "cobra*"))
        cands += glob.glob(os.path.join(v, "extensions", "*", "cobra*"))
    for c in cands:
        if cobra_ok(c):
            return os.path.abspath(c)
    return None


def game_ok(d):
    return bool(d) and os.path.isdir(os.path.join(d, "GameMain")) and \
        os.path.isfile(os.path.join(d, "ContentPDLC5", "Rides", "FlatRides", "FR_Cinema", "FR_Cinema.ovl"))


def find_game(pref=None):
    if game_ok(pref):
        return pref
    tail = os.path.join("steamapps", "common", "Planet Coaster 2", "Win64", "ovldata")
    for drive in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        root = drive + ":\\"
        if not IS_WIN or not os.path.isdir(root):
            continue
        for base in ("SteamLibrary", "Steam", os.path.join("Program Files (x86)", "Steam"),
                     os.path.join("Program Files", "Steam"), "Games\\Steam", "Games\\SteamLibrary"):
            c = os.path.join(root, base, tail)
            if game_ok(c):
                return c
    return None


def load_settings():
    s = {}
    for p in (SETTINGS_FILE, _OLD_SETTINGS):
        try:
            with open(p, encoding="utf-8") as f:
                s = json.load(f)
            break
        except Exception:
            pass
    old_lib = os.path.join(os.path.dirname(_OLD_SETTINGS), "library")
    s.setdefault("library", addon_library() or (old_lib if os.path.isdir(old_lib) else os.path.join(_appdata(), "library")))
    s.setdefault("game", "")
    s.setdefault("cobra", "")
    s.setdefault("yaw_sign", 1.0)
    return s


def save_settings(s):
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=1)


SETTINGS = load_settings()


def status():
    cobra = find_cobra(SETTINGS.get("cobra"))
    game = find_game(SETTINGS.get("game"))
    lib = SETTINGS["library"]
    return {"cobra": cobra, "game": game, "library": lib, "shared": bool(addon_library()) and
            os.path.normcase(os.path.abspath(lib)) == os.path.normcase(os.path.abspath(addon_library())),
            "version": VERSION, "settings": SETTINGS, "windows": IS_WIN}


# ------------------------------------------------------------------ tribune state -> generator


PRESETS = {
    "STRAIGHT": [{"kind": "straight", "length": 16, "turn": 0}],
    "L": [{"kind": "straight", "length": 14, "turn": 0}, {"kind": "straight", "length": 14, "turn": 90}],
    "U": [{"kind": "straight", "length": 10, "turn": 0}, {"kind": "straight", "length": 16, "turn": 90},
          {"kind": "straight", "length": 10, "turn": 90}],
    "ARC": [{"kind": "arc", "radius": 14, "angle": 90, "turn": 0}],
    "ARENA": [{"kind": "straight", "length": 3, "turn": 0}, {"kind": "arc", "radius": 10, "angle": 180, "turn": 0},
              {"kind": "straight", "length": 3, "turn": 0}],
    "WEDGE": [{"kind": "straight", "length": 10, "turn": 0}, {"kind": "straight", "length": 10, "turn": 30},
              {"kind": "straight", "length": 10, "turn": 30}],
}

APP_DEFAULTS = {
    "name": "", "auto_name": True, "tid": "", "uid": "", "description": "",
    "single_guests": True,
    "free_on": True, "free_seed": 7, "free_group_min": 2, "free_group_max": 6, "free_gap_min": 1, "free_gap_max": 2,
    "floor_pattern": "NONE", "floor_pattern_size": 0.6, "seat_pattern": "NONE", "seat_pattern_size": 0.5,
    "colors": {}, "flexi": {},
}
GEOM_KEYS = [k for k in geom.DEFAULTS if k not in ("seat_width", "seat_depth", "sit", "seat_bottom", "max_step")]


def default_state():
    st = {k: geom.DEFAULTS[k] for k in GEOM_KEYS}
    st["segments"] = [dict(x) for x in PRESETS["STRAIGHT"]]
    st["stair_bottom"] = []
    st["staff_path"] = 1.2
    st.update(json.loads(json.dumps(APP_DEFAULTS)))
    return st


TEMPLATE = assemble.seat_template()


def generate(state):
    prm = {k: state[k] for k in GEOM_KEYS + ["staff_path"] if k in state}
    prm["segments"] = [dict(s) for s in state.get("segments") or []]
    prm["stair_bottom"] = list(state.get("stair_bottom") or []) or None
    prm.update(seat_width=TEMPLATE["width"], seat_depth=TEMPLATE["depth"], sit=TEMPLATE["sit"],
               seat_bottom=TEMPLATE["bottom"])
    res = geom.generate(prm)
    if state.get("free_on", True) and int(state.get("free_group_max", 6)) >= int(state.get("free_group_min", 2)):
        geom.random_free(res["seats"], int(state.get("free_seed", 7)), int(state.get("free_group_min", 2)),
                         int(state.get("free_group_max", 6)), int(state.get("free_gap_min", 1)),
                         int(state.get("free_gap_max", 2)))
    return res


def check(res):
    rep = navcheck.check(res["nav"]["verts"], res["nav"]["tris"], res["outline"]["poly"], res["outline"]["kinds"],
                         res["seats"])
    used = sum(1 for s in res["seats"] if not s["free"])
    return {"errors": [de(e) for e in rep["errors"]], "warnings": [de(w) for w in rep["warnings"]],
            "ok_seats": rep["ok_seats"], "used": used, "bad": [i for i, _w in rep["bad_seats"]]}


def _b64(arr, dtype="<f4"):
    import numpy as np
    return base64.b64encode(np.ascontiguousarray(arr, dtype=dtype).tobytes()).decode("ascii")


def _soup(verts, faces, mats, names):
    """polygons -> per material corner arrays for the viewer"""
    import numpy as np
    out = {}
    for name, lst in assemble._flat(verts, faces, mats, names).items():
        P = np.array([c[0] for c in lst], float)
        N = np.array([c[1] for c in lst], float)
        out[name] = (P, N)
    return out


def preview(state):
    import numpy as np
    res = generate(state)
    meshes = {}
    st, rl = res["structure"], res["rail"]
    meshes.update(_soup(st["verts"], st["faces"], st.get("mat"), ["TB Concrete", "TB Steps"]))
    meshes.update(_soup(rl["verts"], rl["faces"], rl.get("mat"), ["TB Rail", "TB Rail infill"]))
    out_m = {k: {"p": _b64(P), "n": _b64(N), "count": len(P)} for k, (P, N) in meshes.items()}
    seat_parts = {}
    for name, V, T, smooth in geom.seat_template_for(TEMPLATE, res.get("params"))["parts"]:
        T = np.asarray(T, int)
        A, B, C = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
        fn = np.cross(B - A, C - A)
        if smooth:
            vn = np.zeros_like(V)
            for k in range(3):
                np.add.at(vn, T[:, k], fn)
            CN = vn[T.reshape(-1)]
        else:
            CN = np.repeat(fn, 3, axis=0)
        CN = CN / np.maximum(np.linalg.norm(CN, axis=1, keepdims=True), 1e-12)
        CP = V[T.reshape(-1)]
        seat_parts[name] = {"p": _b64(CP), "n": _b64(CN), "count": len(CP)}
    inst = np.array([[s["origin"][0], s["origin"][1], s["origin"][2], s["yaw"], 1.0 if s["free"] else 0.0]
                     for s in res["seats"]], float).reshape(-1, 5)
    nv, nt = np.array(res["nav"]["verts"], float), np.array(res["nav"]["tris"], int).reshape(-1, 3)
    chk = check(res)
    bad = set(chk["bad"])
    targets = [[*s["sit"], *s["target"]] for i, s in enumerate(res["seats"]) if i in bad]
    info = res["info"]
    return {
        "meshes": out_m, "seat": seat_parts, "inst": _b64(inst), "inst_count": len(inst),
        "nav": _b64(nv[nt.reshape(-1)]) if len(nt) else "", "nav_count": int(len(nt) * 3),
        "outline": res["outline"], "booth": res["booth"], "stage": res["stage"],
        "info": {"seats": info["seats"], "rows": info["rows"], "lane": info["lane"], "length": info["length"],
                 "depth": info["depth"], "stairs": info["stairs"]},
        "warnings": [de(w) for w in res["warnings"]], "check": chk, "bad_targets": targets,
        "auto_name": auto_name(chk["used"], state.get("uid"), state.get("tid")),
    }


# ------------------------------------------------------------------ library


def lib_dir():
    return SETTINGS["library"]


def auto_name(n, uid, tid):
    from core import gamebuild
    taken = set()
    for e in gamebuild.list_index(lib_dir()):
        if (e.get("uid") and e.get("uid") == uid) or e.get("id") == tid:
            continue
        taken.add((e.get("name") or "").strip().lower())
    base = "Show Arena %d" % n
    name, k = base, 1
    while name.lower() in taken:
        k += 1
        name = "%s (%d)" % (base, k)
    return name


def new_tid():
    from core import gamebuild
    used = set(e.get("id") for e in gamebuild.list_index(lib_dir()))
    if os.path.isdir(lib_dir()):
        used |= set(os.listdir(lib_dir()))
    k = 1
    while "tribune_%d" % k in used:
        k += 1
    return "tribune_%d" % k


def library_list():
    from core import gamebuild
    out = []
    for e in gamebuild.list_index(lib_dir()):
        tid = e.get("id")
        out.append({"id": tid, "name": e.get("name") or tid, "seats": e.get("seats", 0),
                    "editable": os.path.isfile(os.path.join(lib_dir(), tid or "", "app_state.json")),
                    "icon": os.path.isfile(os.path.join(lib_dir(), tid or "", "icon.png"))})
    out.sort(key=lambda e: e["name"].lower())
    return out


def save_tribune(state, log):
    """checks the tribune and saves it into the library (like 'Save to library' in Blender)"""
    from core import gamebuild
    cobra = find_cobra(SETTINGS.get("cobra"))
    if not cobra:
        raise RuntimeError(tr("cobra-tools was not found. Please install the program again."))
    if not state.get("uid"):
        state["uid"] = uuid.uuid4().hex
    tid = (state.get("tid") or "").strip() or new_tid()
    if not gamebuild.ID_RE.match(tid):
        raise RuntimeError(tr("Invalid ID '%s': 3-31 lowercase letters, digits and _, starting with a letter." % tid))
    old = gamebuild.library_entry(lib_dir(), tid)
    if old and old.get("uid") and old["uid"] != state["uid"]:
        raise RuntimeError(tr("The ID '%s' is already used by another tribune ('%s'). Enter another ID under 'More' or "
                              "delete the other tribune." % (tid, old.get("name", tid))))
    state["tid"] = tid
    log("Generating tribune ...")
    res = generate(state)
    chk = check(res)
    if chk["errors"]:
        raise RuntimeError(tr("Not saved: %s" % " ".join(chk["errors"])))
    seats = [{"sit": s["sit"], "yaw": s["yaw"], "target": s["target"], "row": s["row"], "order": s["order"],
              "free": s["free"]} for s in res["seats"]]
    used = sum(1 for s in seats if not s["free"])
    if state.get("auto_name", True) or not (state.get("name") or "").strip():
        state["name"] = auto_name(used, state["uid"], tid)
    log("Building model ...")
    parts, bounds = assemble.model_parts(res, TEMPLATE, float(state.get("floor_pattern_size", 0.6)),
                                         float(state.get("seat_pattern_size", 0.5)))
    mats = assemble.materials({k: tuple(v) for k, v in (state.get("colors") or {}).items()}, state.get("flexi"))
    b = res["booth"]
    t = {"id": tid, "name": state["name"], "description": state.get("description", ""), "seats": seats,
         "single_guests": bool(state.get("single_guests", True)),
         "surface": {"floor": state.get("floor_pattern", "NONE"), "seat": state.get("seat_pattern", "NONE")},
         "nav": res["nav"], "outline": res["outline"], "booth": [b[0], b[1], 0.0], "structure_bounds": bounds,
         "uid": state["uid"]}
    log("Saving to the library (model, materials, patterns, icon) ...")
    from core import gamebuild as gb
    with gb.cobra_imports(cobra):
        gb.save_to_library(lib_dir(), t, parts, mats, log=log, root=cobra)
    with open(os.path.join(lib_dir(), tid, "app_state.json"), "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)
    log("Saved: %s (%s, %d seats)" % (state["name"], tid, used))
    return {"tid": tid, "uid": state["uid"], "name": state["name"], "seats": used}


def build_all(log):
    from core import gamebuild
    cobra = find_cobra(SETTINGS.get("cobra"))
    game = find_game(SETTINGS.get("game"))
    if not game:
        raise RuntimeError(tr("Planet Coaster 2 was not found (with the Silver Screen DLC). Please choose the ovldata folder "
                              "in the settings: ...\\steamapps\\common\\Planet Coaster 2\\Win64\\ovldata"))
    cache = os.path.join(os.path.dirname(lib_dir().rstrip("\\/")), "cache")
    with gamebuild.cobra_imports(cobra):
        targets = gamebuild.build_mod(lib_dir(), game, cache, log=log, yaw_sign=float(SETTINGS.get("yaw_sign", 1.0)),
                                      root=cobra)
    return {"targets": targets, "game": game}


# ------------------------------------------------------------------ background jobs (save / build)


JOB = {"running": False, "log": [], "ok": None, "result": None, "error": None, "kind": None}
JOB_LOCK = threading.Lock()


def _run_job(kind, fn):
    lang = LANG
    def log(msg):
        msg = str(msg)
        print("[tribune]", msg)
        JOB["log"].append(tr(msg, lang))

    def work():
        try:
            JOB["result"] = fn(log)
            JOB["ok"] = True
        except Exception as e:
            traceback.print_exc()
            msg = str(e) or type(e).__name__
            if isinstance(e, ImportError):
                msg = "A Python package is missing (%s). Please start the app again." % e
            JOB["error"] = tr(msg, lang)
            JOB["ok"] = False
        finally:
            JOB["running"] = False
    with JOB_LOCK:
        if JOB["running"]:
            return False
        JOB.update(running=True, log=[], ok=None, result=None, error=None, kind=kind)
    threading.Thread(target=work, daemon=True).start()
    return True


# ------------------------------------------------------------------ small helpers for the UI


_PATTERN_CACHE = {}


def pattern_png(group, kind, n=2048, look=False):
    """preview picture of a surface pattern (normal map for floors, roughness for seats).
    look: a lit grey picture for the buttons instead of the raw map"""
    from core import textures
    key = (group, kind, n, look)
    if key not in _PATTERN_CACHE:
        from PIL import Image
        if group == "floor":
            arr = textures.floor_textures(kind, n).get("pnormaltexture")
        else:
            tx = textures.seat_textures(kind, 0.5, n)
            arr = tx.get("proughnesspackedtexture")
        if arr is None:
            return None
        if group == "seat":
            import numpy as np
            g = arr[..., 1]
            if look:
                arr = np.stack([g, g, g, np.full_like(g, 255)], -1)
            else:
                arr = tx["pnormaltexture"].copy()
                arr[..., 3] = g
        elif look:
            import numpy as np
            nrm = arr[..., :3].astype(np.float32) / 127.5 - 1.0
            nrm[..., 1] *= -1
            L = np.array([-0.5, 0.5, 0.7]); L /= np.linalg.norm(L)
            sh = np.clip((nrm * L).sum(-1), 0, 1) * (arr[..., 3] / 255.0)
            g = np.clip(60 + 170 * sh, 0, 255).astype(np.uint8)
            arr = np.stack([g, g, (g * 1.03).clip(0, 255).astype(np.uint8), np.full_like(g, 255)], -1)
        else:
            arr = arr.copy()
            arr[..., 3] = 255
        buf = io.BytesIO()
        im = Image.fromarray(arr, "RGBA")
        if im.size[0] > 1024:
            im = im.resize((1024, 1024), Image.LANCZOS)
        im.save(buf, "PNG")
        _PATTERN_CACHE[key] = buf.getvalue()
    return _PATTERN_CACHE[key]


def icon_png(state):
    """the in-game icon of the current tribune (the same renderer as the build uses)"""
    from core import icon
    import numpy as np
    res = generate(state)
    meshes = {}
    st, rl = res["structure"], res["rail"]
    meshes.update(_soup(st["verts"], st["faces"], st.get("mat"), ["TB Concrete", "TB Steps"]))
    meshes.update(_soup(rl["verts"], rl["faces"], rl.get("mat"), ["TB Rail", "TB Rail infill"]))
    meshes.update(assemble.seat_instances(res, TEMPLATE))
    parts = [(k, P, N, None, np.arange(len(P)).reshape(-1, 3)) for k, (P, N) in meshes.items()]
    mats = assemble.materials({k: tuple(v) for k, v in (state.get("colors") or {}).items()}, state.get("flexi"))
    img = icon.render(parts, mats, icon.BIG)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def pick_folder(start=""):
    if not IS_WIN:
        return None
    ps = ("Add-Type -AssemblyName System.Windows.Forms;"
          "$f=New-Object System.Windows.Forms.FolderBrowserDialog;"
          "$f.ShowNewFolderButton=$true;$f.SelectedPath='%s';"
          "if($f.ShowDialog() -eq 'OK'){[Console]::OutputEncoding=[Text.Encoding]::UTF8;Write-Output $f.SelectedPath}"
          % start.replace("'", "''"))
    r = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", ps], capture_output=True, text=True,
                       encoding="utf-8", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    p = (r.stdout or "").strip()
    return p or None


def open_folder(p):
    if p and os.path.isdir(p):
        if IS_WIN:
            os.startfile(p)
        else:
            subprocess.Popen(["xdg-open", p])


# ------------------------------------------------------------------ extras: the guest spawner test mod


EXTRAS = os.path.join(APP, "extras")
SPAWNER = "Mod_GuestSpawner"


def spawner_status():
    game = find_game(SETTINGS.get("game"))
    src = os.path.join(EXTRAS, SPAWNER)
    inst = bool(game) and os.path.isfile(os.path.join(game, SPAWNER, "Main.ovl"))
    current = False
    if inst:
        try:
            current = open(os.path.join(game, SPAWNER, "Main.ovl"), "rb").read() == open(os.path.join(src, "Main.ovl"), "rb").read()
        except OSError:
            pass
    return {"available": os.path.isfile(os.path.join(src, "Main.ovl")), "game": bool(game), "installed": inst,
            "current": current}


def spawner_install(on):
    game = find_game(SETTINGS.get("game"))
    if not game:
        raise RuntimeError(tr("Planet Coaster 2 was not found. Please choose the ovldata folder in the settings first."))
    dst = os.path.join(game, SPAWNER)
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    if on:
        shutil.copytree(os.path.join(EXTRAS, SPAWNER), dst)
    return spawner_status()


# ------------------------------------------------------------------ HTTP


MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".svg": "image/svg+xml", ".png": "image/png", ".woff2": "font/woff2", ".ico": "image/x-icon"}


class Handler(BaseHTTPRequestHandler):
    server_version = "ArenaCreator/" + VERSION

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n).decode("utf-8") or "{}") if n else {}

    def _lang(self):
        global LANG
        lg = (self.headers.get("X-Lang") or "").lower()[:2]
        if lg in LANGS:
            LANG = lg

    def do_GET(self):
        self._lang()
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path == "/api/init":
                return self._send(200, {"state": default_state(), "presets": PRESETS, "status": status(),
                                        "materials": {k: list(v[0]) for k, v in assemble.MATERIALS.items()},
                                        "flexi_auto": assemble.FLEXI_AUTO})
            if u.path == "/api/status":
                return self._send(200, status())
            if u.path == "/api/library":
                return self._send(200, library_list())
            if u.path == "/api/extras":
                return self._send(200, {"spawner": spawner_status()})
            if u.path == "/api/job":
                return self._send(200, JOB)
            if u.path == "/api/pattern":
                look = bool(q.get("look"))
                png = pattern_png(q.get("group", ["floor"])[0], q.get("kind", ["NONE"])[0], n=512 if look else 2048, look=look)
                return self._send(200, png, "image/png") if png else self._send(404, {"error": "none"})
            if u.path == "/api/library/icon":
                tid = q.get("id", [""])[0]
                p = os.path.join(lib_dir(), tid, "icon.png")
                if re.match(r"^[a-z0-9_]+$", tid) and os.path.isfile(p):
                    return self._send(200, open(p, "rb").read(), "image/png")
                return self._send(404, {"error": "no icon"})
            path = "/index.html" if u.path in ("/", "") else u.path
            f = os.path.normpath(os.path.join(WEB, path.lstrip("/")))
            if f.startswith(WEB) and os.path.isfile(f):
                return self._send(200, open(f, "rb").read(), MIME.get(os.path.splitext(f)[1], "application/octet-stream"))
            self._send(404, {"error": "not found"})
        except Exception as e:
            traceback.print_exc()
            self._send(500, {"error": de(str(e))})

    def do_POST(self):
        self._lang()
        u = urlparse(self.path)
        try:
            d = self._json()
            if u.path == "/api/preview":
                try:
                    return self._send(200, preview(d["state"]))
                except geom.GenError as e:
                    return self._send(200, {"gen_error": de(str(e))})
            if u.path == "/api/icon":
                return self._send(200, icon_png(d["state"]), "image/png")
            if u.path == "/api/save":
                st = d["state"]
                ok = _run_job("save", lambda log: dict(save_tribune(st, log), state=st))
                return self._send(200 if ok else 409, {"started": ok})
            if u.path == "/api/build":
                st = d.get("state")

                def job(log):
                    out = {}
                    if st:
                        out.update(save_tribune(st, log))
                        out["state"] = st
                    log("Building all tribunes of the library as mods ...")
                    out.update(build_all(log))
                    return out
                ok = _run_job("build", job)
                return self._send(200 if ok else 409, {"started": ok})
            if u.path == "/api/library/load":
                tid = d["id"]
                p = os.path.join(lib_dir(), tid, "app_state.json")
                if not os.path.isfile(p):
                    return self._send(200, {"error": tr("This tribune was made in the Blender add-on and cannot be edited here.")})
                st = default_state()
                with open(p, encoding="utf-8") as f:
                    st.update(json.load(f))
                return self._send(200, {"state": st})
            if u.path == "/api/library/remove":
                tid = d["id"]
                p = os.path.join(lib_dir(), tid)
                if re.match(r"^[a-z][a-z0-9_]{2,30}$", tid) and os.path.isfile(os.path.join(p, "info.json")):
                    shutil.rmtree(p)
                return self._send(200, library_list())
            if u.path == "/api/extras/spawner":
                return self._send(200, {"spawner": spawner_install(bool(d.get("install")))})
            if u.path == "/api/library/new_id":
                return self._send(200, {"tid": new_tid()})
            if u.path == "/api/settings":
                for k in ("library", "game", "cobra"):
                    if k in d:
                        SETTINGS[k] = (d[k] or "").strip()
                if not SETTINGS["library"]:
                    SETTINGS["library"] = addon_library() or os.path.join(_appdata(), "library")
                if "yaw_sign" in d:
                    SETTINGS["yaw_sign"] = float(d["yaw_sign"])
                save_settings(SETTINGS)
                return self._send(200, status())
            if u.path == "/api/pick_folder":
                return self._send(200, {"path": pick_folder(d.get("start", ""))})
            if u.path == "/api/open_folder":
                which = d.get("which")
                st = status()
                open_folder({"library": st["library"], "game": st["game"], "cobra": st["cobra"]}.get(which) or "")
                return self._send(200, {"ok": True})
            if u.path == "/api/quit":
                self._send(200, {"ok": True})
                threading.Thread(target=lambda: (time.sleep(0.3), os._exit(0)), daemon=True).start()
                return None
            self._send(404, {"error": "not found"})
        except Exception as e:
            traceback.print_exc()
            self._send(500, {"error": de(str(e))})


def _free_port(start=8765):
    for p in range(start, start + 50):
        with socket.socket() as s:
            if not IS_WIN:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return 0


def open_window(url):
    """an app window without browser bars (Edge / Chrome app mode), else the normal browser"""
    if IS_WIN:
        for exe in (r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
                    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
                    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
                    r"%LocalAppData%\Google\Chrome\Application\chrome.exe"):
            p = os.path.expandvars(exe)
            if os.path.isfile(p):
                subprocess.Popen([p, "--app=" + url, "--window-size=1500,920"])
                return
    webbrowser.open(url)


def _stop_old_instances(start=8765):
    """an older copy of the app that is still running would keep the port (and show the old version): close it"""
    import urllib.request
    stopped = False
    for p in range(start, start + 10):
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/api/status" % p, timeout=0.4) as r:
                srv = r.headers.get("Server", "")
            if not srv.startswith(("TribuneBuilder/", "ArenaCreator/")):
                continue
            req = urllib.request.Request("http://127.0.0.1:%d/api/quit" % p, data=b"{}", method="POST",
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=1).read()
            print("Alte Version auf Port %d beendet. / Closed an older version on port %d." % (p, p))
            stopped = True
        except Exception:
            continue
    if stopped:
        # wait until the port is free again
        for _ in range(25):
            time.sleep(0.2)
            with socket.socket() as sk:
                if not IS_WIN:
                    sk.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    sk.bind(("127.0.0.1", start))
                    break
                except OSError:
                    continue


def start(window=True):
    """starts the server in the background; returns its address"""
    _stop_old_instances(int(os.environ.get("TB_PORT", "8765")))
    port = _free_port(int(os.environ.get("TB_PORT", "8765")))
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = "http://127.0.0.1:%d/" % port
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print("ShowMaster Arena Creator %s: %s" % (VERSION, url))
    if window:
        threading.Timer(0.4, open_window, [url]).start()
    return url


def main():
    start("--no-window" not in sys.argv)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
