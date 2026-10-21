"""Turns tribunes into a Planet Coaster 2 mod (needs cobra-tools, no bpy).

Library layout (one folder per tribune):
    <library>/<id>/tribune.json      seats, navmesh, outline, booth, materials, texts (Blender coordinates)
    <library>/<id>/<id>_models.ms2   the visible model
    <library>/<id>/*.fgm             one material file per material

build_mod() makes one mod folder per tribune, ovldata/Mod_TB_<Id>:
    Init.ovl        texts, database statements, asset packages
    Main.ovl        Lua database (ride definition), navmesh, footprint, entrance lines
    TBShow.ovl      show timing (motion graph, made from the game's own cinema at build time)
    TB_<Id>.ovl     model and materials
"""
import json
import math
import os
import re
import shutil
import struct
import tempfile
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
GAME = "Planet Coaster 2"
MOD_NAME = "Mod_TribuneBuilder"
MARKER = ".pc2_tribune_builder"
ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,30}$")
CINEMA_FILES = ("fr_cinema_nav_.ms2", "fr_cinema_ridespatial_.ms2", "fr_cinema_sceneryplatform_frame_.ms2")

SHADERS = {
    "opaque": "Master_MetallicRoughness_Standard_Opaque",
    "clip2": "Master_MetallicRoughness_Standard_ClipDoubleSided",
}


class BuildError(Exception):
    pass


# ------------------------------------------------------------------ helpers


def write(path, text, crlf=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if crlf:
        text = text.replace("\r\n", "\n").replace("\n", "\r\n")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def ascii_text(text):
    rep = {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss", "é": "e", "è": "e", "à": "a"}
    for a, b in rep.items():
        text = text.replace(a, b)
    return "".join(c if 32 <= ord(c) < 127 else "?" for c in text)


def camel(obj_id):
    return "".join(p[:1].upper() + p[1:] for p in obj_id.split("_") if p)


def ride_key(obj_id):
    return "FR_TB_" + camel(obj_id)


def to_game(p):
    """Blender (x, y, z up) -> game (x, y up, z). The game mirrors x (as cobra-tools does for models)."""
    return (-p[0], p[2], -p[1])


def lin2srgb(c):
    c = max(0.0, min(1.0, c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


class cobra_imports:
    """Makes sure 'utils' and 'generated' are cobra-tools' packages while building
    (other Blender add-ons may bring their own 'utils' module)."""

    def __init__(self, root=None):
        self.root = root

    def __enter__(self):
        import sys
        self.sys = sys
        if self.root is None:
            import generated
            self.root = os.path.dirname(os.path.dirname(os.path.abspath(generated.__file__)))
        self.added = self.root not in sys.path[:1]
        if self.added:
            sys.path.insert(0, self.root)
        self.foreign = {}
        for name, mod in list(sys.modules.items()):
            if name == "utils" or name.startswith("utils."):
                f = os.path.abspath(getattr(mod, "__file__", "") or "")
                if not f.startswith(self.root):
                    self.foreign[name] = sys.modules.pop(name)
        import logging
        if not hasattr(logging, "success"):
            logging.success = logging.info
        return self

    def __exit__(self, *exc):
        self.sys.modules.update(self.foreign)
        if self.added and self.sys.path and self.sys.path[0] == self.root:
            self.sys.path.pop(0)
        return False


def cobra_root():
    import generated
    return os.path.dirname(os.path.dirname(os.path.abspath(generated.__file__)))


def _ovl(root):
    from generated.formats.ovl import OvlFile
    from utils.config import Config
    cfg = Config(root)
    cfg.load()
    o = OvlFile()
    o.cfg = cfg
    o.game = GAME
    o.load_hash_table()
    return o


class _Errors(object):
    """collects error messages cobra-tools only logs (it skips files it cannot pack instead of failing)"""

    def __enter__(self):
        import logging

        class H(logging.Handler):
            def __init__(h):
                logging.Handler.__init__(h, logging.ERROR)
                h.msgs = []

            def emit(h, rec):
                try:
                    msg = rec.getMessage()
                    if rec.exc_info and rec.exc_info[1] is not None:
                        msg += " (%s)" % rec.exc_info[1]
                    h.msgs.append(msg)
                except Exception:
                    pass
        self.h = H()
        logging.getLogger().addHandler(self.h)
        return self.h

    def __exit__(self, *exc):
        import logging
        logging.getLogger().removeHandler(self.h)
        return False


def _src_files(in_dir):
    """files cobra-tools must pack (names as in the ovl: relative, '/', lowercase); pictures are only inputs"""
    out = []
    for r, _d, fs in os.walk(in_dir):
        for f in fs:
            if f.lower().endswith((".png", ".dds")):
                continue
            out.append(os.path.relpath(os.path.join(r, f), in_dir).replace("\\", "/").lower())
    return sorted(out)


def pack(in_dir, out_ovl, log=print, root=None):
    """packs every file of in_dir; fails if cobra-tools left one out"""
    with cobra_imports(root) as ci:
        from generated.formats.ovl_base.enums.Compression import Compression
        # cobra-tools checks Lua files with luacheck and silently drops the file if luacheck cannot run
        # (missing, blocked by antivirus, ...). Our Lua is generated and tested, so only real syntax errors count.
        try:
            from modules.formats.utils import lua_conversion as _lc
            _orig = _lc.check_lua_syntax
        except Exception:
            _lc, _orig = None, None
        if _orig is not None and not getattr(_orig, "_tb_safe", False):
            def _safe(path, _o=_orig):
                try:
                    return _o(path)
                except SyntaxError:
                    raise
                except Exception as e:
                    log("note: Lua check skipped (%s)" % e.__class__.__name__)
            _safe._tb_safe = True
            _lc.check_lua_syntax = _safe
        with _Errors() as errs:
            o = _ovl(ci.root)
            o.user_version.compression = Compression["ZLIB"]
            o.clear()
            o.create(in_dir)
            packed = set(k.lower() for k in o.loaders)
            missing = [f for f in _src_files(in_dir) if f not in packed]
            if missing:
                why = " | ".join(errs.msgs[-3:]) or "unknown reason"
                raise BuildError("%s: cobra-tools could not pack %s. Reason: %s"
                                 % (os.path.basename(out_ovl), ", ".join(missing), why))
            os.makedirs(os.path.dirname(out_ovl), exist_ok=True)
            o.save(out_ovl, commands={"update_aux": True})
        # read it back: every file must be inside
        o2 = _ovl(ci.root)
        o2.load(out_ovl)
        back = set(k.lower() for k in o2.loaders)
        lost = [f for f in _src_files(in_dir) if f not in back]
        if lost:
            raise BuildError("%s is incomplete after saving: %s" % (os.path.basename(out_ovl), ", ".join(lost)))
    log("packed %s (%d files)" % (os.path.basename(out_ovl), len(back)))
    return back


# ------------------------------------------------------------------ game templates from the cinema


def find_cinema(ovldata_dir):
    """FR_Cinema.ovl of the Silver Screen DLC"""
    cand = os.path.join(ovldata_dir, "ContentPDLC5", "Rides", "FlatRides", "FR_Cinema", "FR_Cinema.ovl")
    if os.path.isfile(cand):
        return cand
    for root, _dirs, files in os.walk(ovldata_dir):
        for f in files:
            if f.lower() == "fr_cinema.ovl":
                return os.path.join(root, f)
    raise BuildError("FR_Cinema.ovl not found in %s. The tribunes are based on the cinema ride of the "
                     "Silver Screen DLC; please install the DLC." % ovldata_dir)


def prepare_templates(cinema_ovl, cache_dir, log=print, root=None):
    """Extracts navmesh/collision templates and makes the show motion graph (TBShow.ovl).
    Done once; the results are kept in cache_dir."""
    need = [os.path.join(cache_dir, f) for f in CINEMA_FILES] + [os.path.join(cache_dir, "TBShow.ovl")]
    stamp = os.path.join(cache_dir, "source.txt")
    src_id = "%s|%d" % (cinema_ovl, os.path.getsize(cinema_ovl))
    if all(os.path.isfile(p) for p in need) and os.path.isfile(stamp) and open(stamp).read() == src_id:
        return cache_dir
    os.makedirs(cache_dir, exist_ok=True)
    log("reading the cinema ride (one time) ...")
    with cobra_imports(root) as ci:
        o = _ovl(ci.root)
        o.load(cinema_ovl)
        tmp = tempfile.mkdtemp(prefix="tb_cin_")
        o.extract(tmp, only_names=list(CINEMA_FILES))
        for f in CINEMA_FILES:
            hit = None
            for r, _d, files in os.walk(tmp):
                if f in files:
                    hit = os.path.join(r, f)
            if not hit:
                raise BuildError("Could not extract %s from the cinema." % f)
            shutil.copy2(hit, os.path.join(cache_dir, f))
        shutil.rmtree(tmp, ignore_errors=True)
        _make_show_graph(o, os.path.join(cache_dir, "TBShow.ovl"))
    open(stamp, "w").write(src_id)
    log("cinema templates ready")
    return cache_dir


SHOW_TIMES = {"30Seconds": 30, "40Seconds": 60, "50Seconds": 120, "60Seconds": 180, "70Seconds": 240,
              "80Seconds": 300, "90Seconds": 360, "100Seconds": 480, "110Seconds": 600, "120Seconds": 900}
SHOW_LABELS = {"MainSequence": "Default (about 3 min)", "30Seconds": "30 s", "40Seconds": "1 min", "50Seconds": "2 min",
               "60Seconds": "3 min", "70Seconds": "4 min", "80Seconds": "5 min", "90Seconds": "6 min",
               "100Seconds": "8 min", "110Seconds": "10 min", "120Seconds": "15 min"}


def _make_show_graph(o, dst):
    """Copies the cinema motion graph, slows its clips down (show lengths 30 s .. 15 min) and saves it alone."""
    l = o.loaders["fr_cinema.motiongraph"]
    found = []

    def walk(x, pool, depth=0, seen=set()):
        if id(x) in seen or depth > 80:
            return
        seen.add(id(x))
        if hasattr(x, 'speed') and hasattr(x, 'mani'):
            found.append((x, pool))
        for a in getattr(x, '__dict__', {}).values():
            if isinstance(a, (list, tuple)):
                for b in a:
                    walk(b, pool, depth + 1, seen)
            elif hasattr(a, 'target_pool') and hasattr(a, 'data'):
                d = a.data
                if isinstance(d, (list, tuple)):
                    for b in d:
                        walk(b, a.target_pool, depth + 1, seen)
                elif hasattr(d, '__dict__'):
                    walk(d, a.target_pool, depth + 1, seen)
            elif hasattr(a, '__dict__'):
                walk(a, pool, depth + 1, seen)
            if hasattr(a, '__iter__') and not isinstance(a, (str, bytes, list, tuple, dict)) and not hasattr(a, 'target_pool'):
                try:
                    for b in a:
                        if hasattr(b, '__dict__'):
                            walk(b, pool, depth + 1, seen)
                except Exception:
                    pass

    walk(l.header, l.root_ptr[0], 0, set())
    n = 0
    for f, pool in found:
        name = f.mani.data.split('$')[1]
        sp = int(name.replace("Seconds", "")) / SHOW_TIMES[name] if name in SHOW_TIMES else 1.0
        b = pool.data.getbuffer()
        off = f.speed.io_start
        if abs(struct.unpack_from('<f', b, off)[0] - 1.0) > 1e-6:
            del b
            raise BuildError("Unexpected cinema motion graph (clip speed is not 1).")
        struct.pack_into('<f', b, off, sp)
        del b
        n += 1
    if n < 10:
        raise BuildError("Unexpected cinema motion graph (%d clips)." % n)
    controlled = {c.name for ld in o.loaders.values() for c in getattr(ld, "controlled_loaders", [])}
    for k in [k for k in list(o.loaders) if k != "fr_cinema.motiongraph" and k not in controlled]:
        if k in o.loaders:
            o.loaders[k].remove()
    for k in [k for k in list(o.loaders) if k != "fr_cinema.motiongraph"]:
        o.loaders.pop(k, None)
    o.send_files()
    o.rename([("fr_cinema.motiongraph", "tb_show.motiongraph")])
    o.save(dst)


# ------------------------------------------------------------------ model and materials


def _set_attr(fgm, name, value):
    pat = re.compile(r'(<attribinfo name="%s" dtype="FgmDtype\.\w+">\s*<value>)[^<]*(</value>)' % re.escape(name))
    fgm, n = pat.subn(lambda m: m.group(1) + str(value) + m.group(2), fgm)
    if n != 1:
        raise BuildError("Material template: attribute %s not found" % name)
    return fgm


def _const_tex(slot, rgba):
    return ('<textureinfo name="%s" dtype="FgmDtype.RGBA">\n\t\t\t<value>\n'
            '\t\t\t\t<bytecolor r="%d" g="%d" b="%d" a="%d" />\n'
            '\t\t\t\t<bytecolor r="255" g="255" b="255" a="255" />\n\t\t\t</value>\n\t\t</textureinfo>' % ((slot,) + tuple(rgba)))


def _flexi(fgm, channel):
    """flexicolour: the whole material follows ride colour <channel> (1-4); 0 = fixed colour"""
    mask = [0, 0, 0, 0]
    if 1 <= channel <= 4:
        mask[channel - 1] = 255
    fgm = _replace_texinfo(fgm, "pCustomisation_ChannelMasksTexture", _const_tex("pCustomisation_ChannelMasksTexture", mask))
    if channel:
        # neutral brightness, like Frontier's own recolourable materials
        fgm = _replace_texinfo(fgm, "pCustomisation_ValueTexture", _const_tex("pCustomisation_ValueTexture", (128, 128, 128, 255)))
    for ch in range(1, 5):
        used = ch == channel
        fgm = _set_attr(fgm, "pCustomisation_Channel%dSlotIndex" % ch, ch - 1 if used else -1)
        fgm = _set_attr(fgm, "pCustomisation_Channel%dEnableColour" % ch, 1 if used else 0)
        fgm = _set_attr(fgm, "pCustomisation_Channel%dAllowInstanceColour" % ch, 1 if used else 0)
        fgm = _set_attr(fgm, "pCustomisation_Channel%dColour" % ch, "1.0 1.0 1.0")
    return fgm


# game textures: slot, compression and mip values (checked on working mods, 2048 x 2048)
TEX_KINDS = {
    "pnormaltexture": ("pNormalTexture", "BC7_UNORM", 6, 8),
    "proughnesspackedtexture": ("pRoughnessPackedTexture", "BC5_UNORM", 6, 8),
}
TEX_SIZE, TEX_MIPS = 2048, 12


def texel_name(mod, name):
    import hashlib
    h = hashlib.sha1(("%s/%s" % (mod, name)).encode()).digest()
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(alphabet[b % len(alphabet)] for b in h[:16])


def make_tex_header(path, compression, mips_low, mips_high, texel):
    write(path,
          '<TexHeader compression_type="DdsType.%s" width="%d" height="%d" num_mips="%d" texel="%s" game="%s" '
          'ovs="STATIC" num_mips_low="%d" num_mips_high="%d" flag="96">\n\t<compression_pad>0 0 0</compression_pad>\n'
          '\t<texel_ref />\n\t<texel_padding />\n</TexHeader>\n'
          % (compression, TEX_SIZE, TEX_SIZE, TEX_MIPS, texel, GAME, mips_low, mips_high))


def _tex_block(slot, dep):
    return ('<textureinfo name="%s" dtype="FgmDtype.TEXTURE">\n\t\t\t<value>\n\t\t\t\t<texindex array_index="0" />\n'
            '\t\t\t</value>\n\t\t\t<dependency_name>%s</dependency_name>\n\t\t</textureinfo>' % (slot, dep))


def make_fgm(path, rgb, double_sided=False, roughness=0.67, metal=0.0, flexi=0, textures=None):
    """textures: {texture kind (e.g. "pnormaltexture"): dependency name "<name>.<kind>.tex"}"""
    with open(os.path.join(DATA, "material.fgm"), encoding="utf-8") as f:
        fgm = f.read()
    r, g, b = (int(round(lin2srgb(c) * 255)) for c in rgb[:3])
    block = ('<textureinfo name="pBaseColourTexture" dtype="FgmDtype.RGBA">\n\t\t\t<value>\n'
             '\t\t\t\t<bytecolor r="%d" g="%d" b="%d" a="255" />\n'
             '\t\t\t\t<bytecolor r="255" g="255" b="255" a="255" />\n\t\t\t</value>\n\t\t</textureinfo>' % (r, g, b))
    fgm = _replace_texinfo(fgm, "pBaseColourTexture", block)
    rp = ('<textureinfo name="pRoughnessPackedTexture" dtype="FgmDtype.RGBA">\n\t\t\t<value>\n'
          '\t\t\t\t<bytecolor r="%d" g="%d" b="127" a="255" />\n'
          '\t\t\t\t<bytecolor r="255" g="255" b="255" a="255" />\n\t\t\t</value>\n\t\t</textureinfo>'
          % (int(round(max(0, min(1, metal)) * 255)), int(round(max(0, min(1, roughness)) * 255))))
    fgm = _replace_texinfo(fgm, "pRoughnessPackedTexture", rp)
    fgm = _flexi(fgm, int(flexi or 0))
    if double_sided:
        fgm = fgm.replace('shader_name="%s"' % SHADERS["opaque"], 'shader_name="%s"' % SHADERS["clip2"])
        fgm = _insert_texinfo(fgm, "pRoughnessPackedTexture",
                              '<textureinfo name="pOpacity" dtype="FgmDtype.RGBA">\n\t\t\t<value>\n'
                              '\t\t\t\t<bytecolor r="255" g="255" b="255" a="255" />\n'
                              '\t\t\t\t<bytecolor r="255" g="255" b="255" a="255" />\n\t\t\t</value>\n\t\t</textureinfo>')
        fgm = _insert_attr(fgm, "pCustomisation_Channel1AllowInstanceColour", "pAlphaTestRef", "FLOAT", "0.5")
        fgm = _insert_attr(fgm, "pMaximumPorosity", "pHighlightAlphaTestRefBias", "FLOAT", "0.0")
    for kind, dep in (textures or {}).items():
        fgm = _replace_texinfo(fgm, TEX_KINDS[kind][0], _tex_block(TEX_KINDS[kind][0], dep))
    deps = re.findall(r"<dependency_name>([^<]+)</dependency_name>", fgm)
    stray = [d for d in deps if d not in (textures or {}).values()]
    if stray:
        raise BuildError("Material template still uses textures: %s" % stray)
    write(path, fgm)


def _replace_texinfo(fgm, slot, new_block):
    pat = re.compile(r'<textureinfo name="%s" dtype="FgmDtype\.\w+">.*?</textureinfo>' % re.escape(slot), re.S)
    fgm, n = pat.subn(lambda m: new_block, fgm)
    if n != 1:
        raise BuildError("Material template: slot %s not found" % slot)
    return fgm


def _insert_texinfo(fgm, before_slot, block):
    marker = '<textureinfo name="%s"' % before_slot
    if marker not in fgm:
        raise BuildError("Material template: slot %s not found" % before_slot)
    return fgm.replace(marker, block + "\n\t\t" + marker, 1)


def _insert_attr(fgm, before_attr, name, dtype, value):
    marker = '<attribinfo name="%s"' % before_attr
    if marker not in fgm:
        raise BuildError("Material template: attribute %s not found" % before_attr)
    block = ('<attribinfo name="%s" dtype="FgmDtype.%s">\n\t\t\t<value>%s</value>\n\t\t</attribinfo>\n\t\t'
             % (name, dtype, value))
    return fgm.replace(marker, block + marker, 1)


def _tangent(n):
    import numpy as np
    n = np.array(n, dtype=float)
    a = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 1.0, 0])
    t = np.cross(n, a)
    l = np.linalg.norm(t)
    return tuple(t / l) if l > 1e-12 else (1.0, 0.0, 0.0)


def build_model_ms2(out_path, model_name, parts, root=None):
    """parts: list of (material_name, verts, normals, uvs, tris) in Blender coordinates
    (verts/normals/uvs per vertex, tris = index triples). Returns game-space bounds."""
    import numpy as np
    with cobra_imports(root):
        from generated.formats.ms2 import Ms2File
        from generated.formats.ms2.structs.MeshDataWrap import MeshDataWrap
        from generated.formats.ms2.structs.LodInfo import LodInfo
        from generated.formats.ms2.structs.Object import Object
        from generated.formats.ms2.structs.MaterialName import MaterialName
        from generated.formats.ms2.enums.MeshFormat import MeshFormat
        from generated.formats.ms2.enums.CollisionType import CollisionType
        ms2 = Ms2File()
        ms2.load(os.path.join(DATA, "template.ms2"), read_editable=True)
        tmpl = ms2.model_infos[0].model.meshes[0].mesh
        flag, ue0, ue1, me_fx = tmpl.flag._value, tmpl.unk_float_0, tmpl.unk_float_1, tmpl.material_effects
        ms2.clear()
        mi = ms2.model_infos[0]
        mi.name = model_name
        # the root bone and the physics joint of the template get the name of this model
        if mi.bone_info:
            for bone in mi.bone_info.bones:
                bone.name = bone.name.replace("template", model_name, 1)
            if mi.bone_info.joints:
                for j in mi.bone_info.joints.joint_infos:
                    j.name = j.name.replace("template", model_name, 1)
                    j.bone_name = j.bone_name.replace("template", model_name, 1)
        parts = [p for p in parts if len(p[4])]
        if not parts:
            raise BuildError("The model has no faces.")
        allv = np.concatenate([np.array(p[1], dtype=float) for p in parts])
        bmin_b, bmax_b = allv.min(0), allv.max(0)
        gmin = np.array([bmin_b[0], bmin_b[2], -bmax_b[1]])
        gmax = np.array([bmax_b[0], bmax_b[2], -bmin_b[1]])
        mi.bounds_min.set(gmin)
        mi.bounds_max.set(gmax)
        if hasattr(mi, "bounds_max_repeat"):
            mi.bounds_min_repeat.set(gmin)
            mi.bounds_max_repeat.set(gmax)
        center = (gmin + gmax) / 2
        mi.center.set(center)
        mi.radius = float(np.linalg.norm(gmax - center) * 0.77)
        mi.pack_base = ms2.get_pack_base(gmin, gmax)
        mi.precision = ms2.get_precision(mi.pack_base)
        lod = LodInfo(ms2.context)
        lod.distance = 900.0
        lod.first_object_index = 0
        lod.objects = []
        lod.stream_index = 0
        lod.bone_index = 1
        mi.model.lods.append(lod)
        for idx, (mat_name, V, Nn, UV, T) in enumerate(parts):
            wrapper = MeshDataWrap(mi.context)
            mesh = wrapper.mesh
            mesh.mesh_in_lod = idx
            mesh.flag._value = flag
            mesh.unk_float_0 = ue0
            mesh.unk_float_1 = ue1
            mesh.material_effects = me_fx
            mesh.whatever_range = 0.0
            mesh.mesh_format = MeshFormat.SEPARATE
            mesh.expect_shapekeys = False
            mesh.update_dtype()
            mesh.tri_indices = []
            mesh.verts = []
            mi.model.meshes.append(wrapper)
            nuv = mesh.get_uv_count()

            def vert(i):
                n = tuple(Nn[i])
                uv = UV[i] if UV is not None else (0.0, 0.0)
                return (tuple(V[i]), False, n, n, False, _tangent(n), [(uv[0], 1 - uv[1])] * nuv, (1.0, 1.0, 1.0, 1.0),
                        [[0, 1.0]], 0, 0.0, (0, 0, 0), (np.nan, np.nan, np.nan))
            chunks, verts = [], []
            cur_map, cur_tris = {}, []

            def flush():
                nonlocal cur_map, cur_tris
                if not cur_tris:
                    return
                order = sorted(cur_map.items(), key=lambda kv: kv[1])
                verts.extend(vert(g) for g, _ in order)
                chunks.append((0, cur_tris))
                cur_map, cur_tris = {}, []
            for tri in T:
                new = [g for g in tri if g not in cur_map]
                if len(cur_map) + len(new) > 60 or len(cur_tris) >= 60:
                    flush()
                for g in tri:
                    if g not in cur_map:
                        cur_map[g] = len(cur_map)
                cur_tris.append(tuple(cur_map[g] for g in tri))
            flush()
            mesh.pack_base = mi.pack_base
            mesh.precision = mi.precision
            mesh.shell_index = 0
            mesh.shell_count = 0
            mesh.tris = chunks
            for vc in mesh.vert_chunks:
                vc.vertex_count = int(vc.vertex_count)
            mesh.set_verts(verts)
            mesh.lod_index = 0
            mesh.stream_info.pool_index = 0
            mat = MaterialName(mi.context)
            mat.blend_mode = 0
            mat.name = mat_name
            mi.model.materials.append(mat)
            ob = Object(ms2.context)
            ob.mesh_index = idx
            ob.material_index = idx
            ob.mesh = mesh
            for tc in mesh.tri_chunks:
                tc.material_index = idx
            mi.model.objects.append(ob)
            lod.objects.append(ob)
        lod.last_object_index = len(mi.model.objects)
        # box collider = model bounds
        for ji in mi.bone_info.joints.joint_infos:
            for h in ji.hitchecks:
                if h.dtype == CollisionType.BOUNDING_BOX:
                    c, e = h.collider.center, h.collider.extent
                    c.x, c.y, c.z = (float(v) for v in center)
                    e.x, e.y, e.z = (float(max(v, 0.01)) for v in (gmax - gmin))
        ms2.save(out_path)
    return gmin.tolist(), gmax.tolist()


# ------------------------------------------------------------------ collision, navmesh, entrance lines


def _box(x0, x1, y0, y1, z0, z1):
    import numpy as np
    return np.array([[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)], dtype=np.float32)


def hulls(src, dst, name, b):
    from generated.formats.ms2 import Ms2File
    m = Ms2File()
    m.load(src, read_editable=True)
    mi = m.model_infos[0]
    mi.name = name
    for ji in mi.bone_info.joints.joint_infos:
        for h in ji.hitchecks:
            c = h.collider
            c.vertex_count = 8
            c.vertices = b.copy()
            c.offset.x = c.offset.y = c.offset.z = 0.0
    m.save(dst)


def nav_ms2(src, dst, name, verts, tris):
    import numpy as np
    from generated.formats.ms2 import Ms2File
    from generated.formats.ms2.structs.MeshCollisionData import MeshCollisionData
    verts = np.array(verts, dtype=np.float32)
    tris = np.array(tris, dtype=np.uint16)
    m = Ms2File()
    m.load(src, read_editable=True)
    mi = m.model_infos[0]
    mi.name = name
    c = mi.bone_info.joints.joint_infos[0].hitchecks[0].collider
    c.vertex_count = len(verts)
    c.tri_count = len(tris)
    c.is_optimized = 0
    c.tris_switch = 0
    lo, hi = verts.min(0), verts.max(0)
    c.bounds_min.x, c.bounds_min.y, c.bounds_min.z = (float(x) for x in lo)
    c.bounds_max.x, c.bounds_max.y, c.bounds_max.z = (float(x) for x in hi)
    c.data = MeshCollisionData(c.context, c)
    c.data.vertices[:] = verts
    c.data.triangles[:] = tris
    m.save(dst)


def spl(path, p0, p1):
    """straight spline (game x, z) from p0 to p1"""
    cx, cz = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
    dx, dz = p1[0] - p0[0], p1[1] - p0[1]
    L = (dx * dx + dz * dz) ** 0.5
    sc = max(abs(dx), abs(dz)) / 2 / 32767
    q = lambda v: int(round(v / sc))
    k0 = (q(p0[0] - cx), 0, q(p0[1] - cz))
    k1 = (q(p1[0] - cx), 0, q(p1[1] - cz))
    hs = (L / 3) / 127
    hr = (int(round(dx / L * 127)), 0, int(round(dz / L * 127)))
    hn = (-hr[0], 0, -hr[2])
    key = lambda p, a, b: ('\t\t\t<key handle_scale="%s">\n\t\t\t\t<pos x="%d" y="%d" z="%d" />\n'
                           '\t\t\t\t<handle_left x="%d" y="%d" z="%d" />\n'
                           '\t\t\t\t<handle_right x="%d" y="%d" z="%d" />\n\t\t\t</key>\n'
                           % ((hs,) + tuple(p) + tuple(a) + tuple(b)))
    write(path,
          '<SplRoot count="2" sixteen="16" one="1" length="%s" game="Planet Coaster 2">\n'
          '\t<spline_data scale="%s">\n\t\t<offset x="%s" y="0.0" z="%s" />\n\t\t<keys>\n' % (L, sc, cx, cz)
          + key(k0, (0, 0, 0), hr) + key(k1, hn, (0, 0, 0)) + '\t\t</keys>\n\t</spline_data>\n</SplRoot>\n')


# ------------------------------------------------------------------ library


def save_to_library(library_dir, tribune, parts, materials, log=print, root=None):
    """tribune: dict with id, name, description, seats, nav, outline, booth, structure_bounds (Blender coords).
    parts: model parts (see build_model_ms2). materials: {name: {"color": (r,g,b) linear, "double": bool,
    "roughness": f, "metal": f}}. Writes the tribune into its library folder."""
    tid = tribune["id"]
    if not ID_RE.match(tid):
        raise BuildError("Invalid ID '%s': use 3-31 lowercase letters, digits and _ (starting with a letter)." % tid)
    folder = os.path.join(library_dir, tid)
    if os.path.isdir(folder):
        shutil.rmtree(folder)
    os.makedirs(folder)
    model = "tb_%s" % tid
    names = {}
    out_parts = []
    for mat_name, V, Nn, UV, T in parts:
        gm = names.setdefault(mat_name, "%s_%s" % (model, re.sub(r"[^a-z0-9]+", "_", mat_name.lower()).strip("_")[:24] or "mat"))
        out_parts.append((gm, V, Nn, UV, T))
    gmin, gmax = build_model_ms2(os.path.join(folder, model + "_models.ms2"), model, out_parts, root)
    # surface patterns (normal / roughness maps), one set per kind, shared by the materials that use it
    surf = tribune.get("surface") or {}
    made = {}

    def tex_for(group, kind, rough):
        if not kind or kind == "NONE":
            return {}
        key = (group, kind)
        if key not in made:
            from . import textures as _tx
            arrs = _tx.floor_textures(kind) if group == "floor" else _tx.seat_textures(kind, rough)
            deps = {}
            for tk, arr in arrs.items():
                base = "%s_%s_%s" % (model, group, kind.lower())
                _tx.save_png(arr, os.path.join(folder, "%s.%s.png" % (base, tk)))
                # ready game texture (compressed with mips), so packing needs no texconv
                from . import dds as _dds
                _dds.write_dds(os.path.join(folder, "%s.%s.dds" % (base, tk)), arr, TEX_KINDS[tk][1])
                deps[tk] = "%s.%s.tex" % (base, tk)
            made[key] = deps
        return made[key]
    for mat_name, gm in names.items():
        m = materials.get(mat_name, {})
        grp = m.get("surface")
        texs = {}
        try:
            if grp == "floor":
                texs = tex_for("floor", surf.get("floor"), m.get("roughness", 0.67))
            elif grp == "seat":
                texs = tex_for("seat", surf.get("seat"), m.get("roughness", 0.5))
        except ImportError as e:
            log("note: no surface pattern (%s)" % e)
            texs = {}
        make_fgm(os.path.join(folder, gm + ".fgm"), m.get("color", (0.5, 0.5, 0.5)), m.get("double", False),
                 m.get("roughness", 0.67), m.get("metal", 0.0), m.get("flexi", 0), texs)
    # picture for the build menu
    try:
        from . import icon as _icon
        cols_ = {gm: {"color": materials.get(mn, {}).get("color", (0.5, 0.5, 0.5))} for mn, gm in names.items()}
        _icon.render_icon(out_parts, cols_, os.path.join(folder, "icon_big.png"), os.path.join(folder, "icon.png"))
    except Exception as e:      # (Pillow missing etc.) the cinema icon is used then
        log("note: no icon picture (%s)" % e)
    # default ride colours: the colour of the first material on each flexicolour channel (sRGB 0-1)
    colours = {}
    for mat_name in names:
        m = materials.get(mat_name, {})
        ch = int(m.get("flexi", 0) or 0)
        if ch and ch not in colours:
            colours[ch] = [round(lin2srgb(c), 4) for c in m.get("color", (0.5, 0.5, 0.5))[:3]]
    data = dict(tribune)
    data["model"] = model
    data["model_bounds"] = (gmin, gmax)
    data["colours"] = {str(k): v for k, v in colours.items()}
    # serialise first (a half written file would make the tribune disappear from the library)
    text = json.dumps(data, default=lambda o: list(o) if hasattr(o, "__iter__") else float(o))
    info = json.dumps({"id": tid, "name": tribune.get("name") or tid, "uid": tribune.get("uid", ""),
                       "seats": sum(1 for s in tribune["seats"] if not s.get("free"))})
    with open(os.path.join(folder, "tribune.json"), "w", encoding="utf-8") as f:
        f.write(text)
    with open(os.path.join(folder, "info.json"), "w", encoding="utf-8") as f:
        f.write(info)
    # read back: the build must find it
    found = [t for t in list_library(library_dir) if t.get("id") == tid]
    if not found:
        raise BuildError("The tribune was written to %s but cannot be read back." % folder)
    log("saved %s to the library (%d seats)" % (tid, sum(1 for s in tribune["seats"] if not s.get("free"))))
    return folder


def library_entry(library_dir, tid):
    """info.json of a tribune in the library, or None"""
    p = os.path.join(library_dir, tid, "info.json")
    if not os.path.isfile(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


_INDEX_CACHE = {}


def list_index(library_dir):
    """Small list (id, name, seats) for the user interface, cached by folder time stamps."""
    if not os.path.isdir(library_dir):
        return []
    try:
        stamp = tuple((d, os.path.getmtime(os.path.join(library_dir, d))) for d in sorted(os.listdir(library_dir)))
    except OSError:
        return []
    hit = _INDEX_CACHE.get(library_dir)
    if hit and hit[0] == stamp:
        return hit[1]
    out = []
    for d, _m in stamp:
        p = os.path.join(library_dir, d, "info.json")
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    out.append(json.load(f))
            except Exception:
                pass
    _INDEX_CACHE[library_dir] = (stamp, out)
    return out


def list_library(library_dir, problems=None):
    """all tribunes of the library; folders that cannot be used are listed in problems (if given)"""
    out = []
    if not os.path.isdir(library_dir):
        return out
    for d in sorted(os.listdir(library_dir)):
        folder = os.path.join(library_dir, d)
        if not os.path.isdir(folder):
            continue
        j = os.path.join(folder, "tribune.json")
        if not os.path.isfile(j):
            if problems is not None:
                problems.append("%s: no tribune.json (saving was not finished)" % d)
            continue
        try:
            with open(j, encoding="utf-8") as f:
                t = json.load(f)
            t["folder"] = folder
            if not any(x.endswith("_models.ms2") for x in os.listdir(folder)):
                raise ValueError("model file missing")
            out.append(t)
        except Exception as e:
            if problems is not None:
                problems.append("%s: %s" % (d, e))
    return out


# ------------------------------------------------------------------ game data of one tribune


def seat_table(seats):
    """active seats, numbered 1..n per row in their order. Returns lua rows and count."""
    rows = {}
    for s in seats:
        if s.get("free"):
            continue
        rows.setdefault(int(s["row"]), []).append(s)
    out = []
    for r in sorted(rows):
        lst = sorted(rows[r], key=lambda s: s.get("order", 0))
        for n, s in enumerate(lst):
            sx, sy, sz = to_game(s["sit"])
            tx, ty, tz = to_game(s["target"])
            gy = -float(s["yaw"])      # Blender rotation about +Z -> game rotation about +Y (mirrored)
            out.append((sx, sy, sz, r, n + 1, tx, ty, tz, gy))
    # the game expects rows 1..k without gaps
    remap = {r: i + 1 for i, r in enumerate(sorted(set(o[3] for o in out)))}
    return [o[:3] + (remap[o[3]],) + o[4:] for o in out]


def outline_game(poly, kinds):
    """game (x, z) polygon, counter-clockwise as the cinema's, with edge kinds"""
    g = [(-p[0], -p[1]) for p in poly]
    k = list(kinds)
    area = sum(g[i][0] * g[(i + 1) % len(g)][1] - g[(i + 1) % len(g)][0] * g[i][1] for i in range(len(g)))
    if area < 0:
        # reverse the order; edge i (g[i] -> g[i+1]) becomes edge (n-2-i) of the reversed list
        n = len(g)
        g = g[::-1]
        k = [kinds[(n - 2 - i) % n] for i in range(n)]
    return g, k


def tribune_files(t, main_dir, cache_dir, root=None):
    """Writes navmesh, collision and entrance lines of one tribune. Returns its Lua variant line."""
    import numpy as np
    tid = t["id"]
    pre = "TB" + camel(tid)
    lp = pre.lower()
    # navmesh (game coordinates)
    nv = [to_game(v) for v in t["nav"]["verts"]]
    nt = [(a, c, b) for a, b, c in t["nav"]["tris"]]      # mirrored x -> flip the winding
    if len(nv) > 65000:
        raise BuildError("%s: navmesh has too many points (%d)." % (tid, len(nv)))
    nav_ms2(os.path.join(cache_dir, "fr_cinema_nav_.ms2"), os.path.join(main_dir, lp + "_nav_.ms2"), pre + "_Nav", nv, nt)
    # selection / collision box around the tribune structure, platform frame around the outline
    (bx0, by0, bz0), (bx1, by1, bz1) = t["structure_bounds"]
    g0, g1 = to_game((bx0, by0, bz0)), to_game((bx1, by1, bz1))
    hulls(os.path.join(cache_dir, "fr_cinema_ridespatial_.ms2"), os.path.join(main_dir, lp + "_ridespatial_.ms2"),
          pre + "_RideSpatial", _box(min(g0[0], g1[0]), max(g0[0], g1[0]), 0.0, max(g0[1], g1[1]) + 0.3,
                                     min(g0[2], g1[2]), max(g0[2], g1[2])))
    poly, kinds = outline_game(t["outline"]["poly"], t["outline"]["kinds"])
    xs = [p[0] for p in poly]
    zs = [p[1] for p in poly]
    hulls(os.path.join(cache_dir, "fr_cinema_sceneryplatform_frame_.ms2"),
          os.path.join(main_dir, lp + "_sceneryplatform_frame_.ms2"), pre + "_SceneryPlatform_Frame",
          _box(min(xs), max(xs), 0.0, 0.05, min(zs), max(zs)))
    names = []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        if math.hypot(b[0] - a[0], b[1] - a[1]) < 0.05:
            continue
        nm = "%s_%03d" % (kinds[i], len(names) + 1)
        spl(os.path.join(main_dir, "%s_platform_spl_%s.spl" % (lp, nm.lower())), a, b)
        names.append(nm)
    seats = seat_table(t["seats"])
    if not seats:
        raise BuildError("%s has no active seats." % tid)
    radius = max(math.hypot(x, z) for x, z in poly) + 1.0
    booth = to_game(tuple(t["booth"][:2]) + (0.0,))
    fmt = lambda v: ("%.4f" % v).rstrip("0").rstrip(".") if isinstance(v, float) else str(v)
    lua_seats = ", ".join("{ " + ", ".join(fmt(x) for x in s) + " }" for s in seats)
    line = ('    { key = "%s", pre = "%s", seats = %d, small = true, hide = true, platform = false, show = true, '
            'size = "%s", w = %s, d = %s, model = "%s", pkg = "%s", radius = %s, booth = { %s, %s },\n'
            '      spl = { %s },\n      colours = { %s },\n      seatpos = { %s } },'
            % (ride_key(tid), pre, len(seats), pre, fmt(max(zs) - min(zs)), fmt(max(xs) - min(xs)), t["model"],
               "TB_" + camel(tid), fmt(radius), fmt(booth[0]), fmt(booth[2]),
               ", ".join('"%s"' % s for s in names),
               ", ".join("{ %d, %s, %s, %s }" % ((int(k) - 1,) + tuple(fmt(float(c)) for c in v[:3]))
                         for k, v in sorted((t.get("colours") or {}).items())),
               lua_seats))
    return line, len(seats)


# ------------------------------------------------------------------ database statements


def _ps(name, args, sql):
    a = "".join('\t\t\t\t<arg arg_type="3" arg_index="%d" />\n' % i for i in range(1, args + 1))
    return ('\t\t<preparedstatement arg_count="%d">\n\t\t\t<args pool_type="4">\n%s\t\t\t</args>\n'
            '\t\t\t<statement_name>%s</statement_name>\n\t\t\t<sql_query>%s</sql_query>\n\t\t</preparedstatement>\n'
            % (args, a, name, sql))


SIM_COLS = ("Name, ExcitementRating, IntensityRating, NauseaRating, Prestige, TicketCost, BuildCost, SupportsChildGuests, "
            "MaximumGroupSize, ResearchPack, Duration, MinDuration, MaxDuration, ClampedDuration, PrestigeModifier, "
            "ExcitementRepetition, FearRepetition, NauseaRepetition, PrestigeRepetition, LongTransitionPrestige, ContentPack, "
            "DefaultVariation, BuildUpwardsCost, BuildDownwardsCost, AudioCabinIsEnclosed, UnlockLevel, IsChildOnly, IsSwimsuit, "
            "ServiceInterval, SimpleRideMusic, DisableGuestCameras, MinPrestige, MaxPrestige, TargetPrestige")


def statements(single=False):
    """single: guests go onto the tribune one by one (MaximumGroupSize = 1)"""
    sim_sel = "?1" + SIM_COLS[len("Name"):]
    grp = "MaximumGroupSize = 1, " if single else ""
    st = [
        _ps("TB_Simulation__Count", 1, "SELECT COUNT(*) AS n FROM Simulation WHERE Name = ?1;"),
        _ps("TB_Simulation__Clone", 2, "INSERT OR REPLACE INTO Simulation (%s) SELECT %s FROM Simulation WHERE Name = ?2;" % (SIM_COLS, sim_sel)),
        _ps("TB_Simulation__Cheap", 1, "UPDATE Simulation SET BuildCost = 5000 WHERE Name = ?1;"),
        _ps("TB_Simulation__Show", 1, ("UPDATE Simulation SET " + grp + "BuildCost = 20000, BuildUpwardsCost = 0, BuildDownwardsCost = 0, TicketCost = 100, "
            "Prestige = 1000, TargetPrestige = 1000, MaxPrestige = 1200, MinPrestige = 800, PrestigeModifier = 1.0, LongTransitionPrestige = 0.0, "
            "ExcitementRating = 7.5, IntensityRating = 1.5, NauseaRating = 0.2, "
            "Duration = 60.0, MinDuration = 5.0, MaxDuration = 3600.0, ClampedDuration = 7200.0, "
            "ExcitementRepetition = 1.05, FearRepetition = 1.0, NauseaRepetition = 1.0, PrestigeRepetition = 1.0 WHERE Name = ?1;")),
        _ps("TB_SequenceData__BoostShow", 1, "UPDATE SequenceData SET ExcitementRating = 7.5, IntensityRating = 1.5, NauseaRating = 0.2, Prestige = 1000 WHERE Ride = ?1;"),
        _ps("TB_SequenceData__RelabelShow", 1, "UPDATE SequenceData SET Label = 'TBSeq_' || SequenceID WHERE Ride = ?1;"),
        _ps("TB_SequenceData__Delete", 1, "DELETE FROM SequenceData WHERE Ride = ?1;"),
        _ps("TB_SequenceData__Relabel", 1, "UPDATE SequenceData SET Label = 'TBSeq_' || SequenceID WHERE Ride = ?1;"),
        _ps("TB_SequenceData__Clone", 2, "INSERT INTO SequenceData (Ride, SequenceID, Label, Ordering, ExcitementRating, IntensityRating, NauseaRating, Prestige, TotalBreakdownTime, LocalSpinning, Inversion) SELECT ?1, SequenceID, Label, Ordering, ExcitementRating, IntensityRating, NauseaRating, Prestige, TotalBreakdownTime, LocalSpinning, Inversion FROM SequenceData WHERE Ride = ?2;"),
        _ps("TB_BrowserEntries__Icon", 2, "UPDATE BrowserEntries SET Icon = ?2 WHERE Ride = ?1;"),
        _ps("TB_BrowserEntries__Clone", 4, "INSERT OR REPLACE INTO BrowserEntries (Ride, Label, Icon, Description, ReleaseGroup) SELECT ?1, ?3, Icon, ?4, ReleaseGroup FROM BrowserEntries WHERE Ride = ?2;"),
        _ps("TB_PrefabDefaults__Clone", 2, "INSERT OR REPLACE INTO PrefabDefaults (Ride, SupportBase) SELECT ?1, SupportBase FROM PrefabDefaults WHERE Ride = ?2;"),
        _ps("TB_BlueprintTags__Clone", 2, "INSERT OR IGNORE INTO BlueprintTags (Ride, Tag) SELECT ?1, Tag FROM BlueprintTags WHERE Ride = ?2;"),
        _ps("TB_RideMetadataTags__Clone", 2, "INSERT OR IGNORE INTO RideMetadataTags (Ride, Tag) SELECT ?1, Tag FROM RideMetadataTags WHERE Ride = ?2 AND Tag != 'Filter_Size_LargeRide';"),
        _ps("TB_UtilityConsumer__Clone", 2, "INSERT OR REPLACE INTO UtilityConsumer (RideName, UtilityType, RequiredUtilityQuantity) SELECT ?1, UtilityType, 1.0 FROM UtilityConsumer WHERE RideName = ?2;"),
    ]
    rides = ('<PscollectionRoot count="%d" game="Planet Coaster 2">\n\t<prepared_statements pool_type="4">\n' % len(st)
             + "".join(st) + '\t</prepared_statements>\n</PscollectionRoot>\n')
    own = [_ps("TB_SecurityOwnership__Clone", 2, "INSERT OR REPLACE INTO SecurityOwnership (UniqueKey, ContentPack) SELECT ?1, ContentPack FROM SecurityOwnership WHERE UniqueKey = ?2;")]
    owns = ('<PscollectionRoot count="1" game="Planet Coaster 2">\n\t<prepared_statements pool_type="4">\n'
            + "".join(own) + '\t</prepared_statements>\n</PscollectionRoot>\n')
    return rides, owns


# ------------------------------------------------------------------ the whole mod


def mod_name(tid):
    return "Mod_TB_" + camel(tid)


def _rename_ids(text, pre):
    """statement / collection / show names get the tribune's own prefix, so several tribune mods never clash"""
    text = re.sub(r"\bTB_(\w+?__\w+)", lambda m: "%s_%s" % (pre, m.group(1)), text)
    text = text.replace("TribuneBuilder_RidesOwnership", pre + "_RidesOwnership")
    text = text.replace("TribuneBuilder_Rides", pre + "_Rides")
    text = text.replace('"TB_Show"', '"%s_Show"' % pre)
    return text


def _show_ovl(cache_dir, pre, dst, root=None):
    """the slowed down cinema motion graph under the tribune's own name"""
    with cobra_imports(root) as ci:
        o = _ovl(ci.root)
        o.load(os.path.join(cache_dir, "TBShow.ovl"))
        o.rename([("tb_show.motiongraph", (pre + "_show").lower() + ".motiongraph")])
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        o.save(dst)
        o2 = _ovl(ci.root)
        o2.load(dst)
        if (pre + "_show").lower() + ".motiongraph" not in [k.lower() for k in o2.loaders]:
            raise BuildError("Show timing for %s could not be made." % pre)


def _build_one(t, ovldata_dir, cache_dir, work, log, yaw_sign, root):
    """one tribune = one mod folder ovldata/Mod_TB_<Id>"""
    tid = t["id"]
    C = camel(tid)
    pre = "TB" + C
    mod = mod_name(tid)
    key = ride_key(tid)
    pkg = "TB_" + C
    src = os.path.join(work, "src", mod)
    out = os.path.join(work, "out", mod)
    shutil.rmtree(src, ignore_errors=True)
    shutil.rmtree(out, ignore_errors=True)
    init, main, mdir = os.path.join(src, "Init"), os.path.join(src, "Main"), os.path.join(src, pkg)
    for d in (init, main, mdir):
        os.makedirs(d)
    with cobra_imports(root):
        line, n = tribune_files(t, main, cache_dir, root)
    name = t.get("name") or tid
    write(os.path.join(init, key.lower() + ".txt"), ascii_text(name))
    write(os.path.join(init, key.lower() + "_desc.txt"),
          ascii_text(t.get("description") or ("Tribune with %d seats. Set the show length with the ride time." % n)))
    write(os.path.join(init, pkg.lower() + ".assetpkg"),
          '<AssetpkgRoot game="Planet Coaster 2">\n\t<asset_path>ovldata\\%s\\%s</asset_path>\n</AssetpkgRoot>\n' % (mod, pkg))
    for f in os.listdir(t["folder"]):
        if f.endswith((".ms2", ".fgm")):
            shutil.copy2(os.path.join(t["folder"], f), os.path.join(mdir, f))
        m_ = re.match(r"^(.+)\.(pnormaltexture|proughnesspackedtexture)\.png$", f)
        if m_:
            # surface pattern: the picture plus a texture header; cobra-tools converts it while packing
            _slot, comp, lo, hi = TEX_KINDS[m_.group(2)]
            dds_ = os.path.join(t["folder"], f[:-4] + ".dds")
            if os.path.isfile(dds_):
                shutil.copy2(dds_, os.path.join(mdir, f[:-4] + ".dds"))
            else:
                shutil.copy2(os.path.join(t["folder"], f), os.path.join(mdir, f))
            make_tex_header(os.path.join(mdir, f[:-4] + ".tex"), comp, lo, hi, texel_name(mod, m_.group(1)))
    if not any(f.endswith("_models.ms2") for f in os.listdir(mdir)):
        raise BuildError("%s: the model is missing in the library. Save the tribune to the library again." % tid)
    for sid, txt in SHOW_LABELS.items():
        write(os.path.join(init, ("TBSeq_" + sid).lower() + ".txt"), txt)
    write(os.path.join(init, (pre + "_show").lower() + ".assetpkg"),
          '<AssetpkgRoot game="Planet Coaster 2">\n\t<asset_path>ovldata\\%s\\TBShow</asset_path>\n</AssetpkgRoot>\n' % mod)
    rides, owns = statements(bool(t.get("single_guests", True)))
    write(os.path.join(init, (pre + "_rides").lower() + ".pscollection"), _rename_ids(rides, pre))
    write(os.path.join(init, (pre + "_ridesownership").lower() + ".pscollection"), _rename_ids(owns, pre))
    # icon pictures: like the game's own ride icons, textures uigameface/img/flatrides/<icon name>.png(.tex) and
    # <icon name>_big.png, each in its own archive; the UI package lists them (icondata) and Lua maps it
    uipkg = None
    icon_name = None
    if os.path.isfile(os.path.join(t["folder"], "icon_big.png")) and os.path.isfile(os.path.join(t["folder"], "icon.png")):
        from . import dds as _dds
        from PIL import Image
        icon_name = "FlatRidesCustom" + pre
        uipkg = (pre + "UI").lower()
        idir = os.path.join(main, "uigameface", "img", "flatrides")
        os.makedirs(idir, exist_ok=True)
        xml = '<PPUIPKGRoot game="Planet Coaster 2">\n\t<basic_path>%s/Main</basic_path>\n\t<files />\n\t<icondata>\n' % mod
        for k, (suffix, src_) in enumerate((("", "icon.png"), ("_big", "icon_big.png"))):
            base_ = icon_name.lower() + suffix + ".png"
            ovs_ = "UserInterface%s_%d" % (pre, k)
            img = Image.open(os.path.join(t["folder"], src_)).convert("RGB")
            w_, h_ = img.size
            _dds.write_dds_single(os.path.join(idir, base_ + ".dds"), img)
            write(os.path.join(idir, base_ + ".tex"),
                  '<TexHeader compression_type="DdsType.BC1_UNORM" width="%d" height="%d" num_mips="1" texel="%s" '
                  'game="%s" ovs="%s" num_mips_low="1" num_mips_high="1" flag="0">\n\t<compression_pad>0 0 0</compression_pad>\n'
                  '\t<texel_ref />\n\t<texel_padding />\n</TexHeader>\n' % (w_, h_, (pre + "_uitexel").lower(), GAME, ovs_))
            xml += ('\t\t<userinterfaceicondata>\n\t\t\t<image_name>uigameface/img/flatrides/%s</image_name>\n'
                    '\t\t\t<ovs>%s</ovs>\n\t\t</userinterfaceicondata>\n' % (base_, ovs_))
        xml += '\t</icondata>\n</PPUIPKGRoot>\n'
        write(os.path.join(main, uipkg + ".ppuipkg"), xml)
        line = line.replace(' seats = ', ' icon = "%s", seats = ' % icon_name, 1)
    with open(os.path.join(DATA, "database.lua.in"), encoding="utf-8") as f:
        lua = f.read()
    lua = lua.replace("--@@VARIANTS@@", line).replace("--@@YAWSIGN@@", "%s" % float(yaw_sign))
    lua = lua.replace("--@@UIPKG@@", '"%s"' % uipkg if uipkg else "nil")
    # the game loads "Database.<mod folder name>LuaDatabase" of every mod folder: the names must match exactly
    lua = lua.replace("Database.Mod_TribuneBuilderLuaDatabase", "Database.%sLuaDatabase" % mod)
    lua = _rename_ids(lua, pre)
    if ('key = "%s"' % key) not in lua:
        raise BuildError("%s is missing in the Lua database." % key)
    if ('require("Database.%sLuaDatabase")' % mod) not in lua:
        raise BuildError("Lua module name does not match the mod folder %s." % mod)
    write(os.path.join(main, "database.%sluadatabase.lua" % mod.lower()), lua, crlf=True)
    pack(init, os.path.join(out, "Init.ovl"), log, root)
    pack(main, os.path.join(out, "Main.ovl"), log, root)
    pack(mdir, os.path.join(out, pkg + ".ovl"), log, root)
    _show_ovl(cache_dir, pre, os.path.join(out, "TBShow.ovl"), root)
    target = os.path.join(ovldata_dir, mod) if ovldata_dir else None
    manifest_id = None
    if target and os.path.isfile(os.path.join(target, "Manifest.xml")):
        m = re.search(r"<ID>([^<]+)</ID>", open(os.path.join(target, "Manifest.xml"), encoding="utf-8", errors="ignore").read())
        manifest_id = m.group(1) if m else None
    write(os.path.join(out, "Manifest.xml"),
          '<ContentPack version="1">\n  <Name>%s</Name>\n  <ID>%s</ID>\n  <Version>1</Version>\n  <Type>Game</Type>\n</ContentPack>\n'
          % (mod, manifest_id or uuid.uuid4()), crlf=True)
    write(os.path.join(out, MARKER), "Made by the Blender add-on PC2 Tribune Builder. Replaced on every build.\n")
    import time as _time
    rep = ["%s - built %s" % (mod, _time.strftime("%Y-%m-%d %H:%M:%S")), "",
           "Name in the game: %s" % name, "ID: %s" % tid, "Game key: %s" % key, "Seats: %d" % n, "",
           "Files:"] + ["  %s  %d bytes" % (f, os.path.getsize(os.path.join(out, f))) for f in sorted(os.listdir(out))]
    write(os.path.join(out, "build_log.txt"), "\n".join(rep) + "\n", crlf=True)
    return out, mod, name, n


def build_mod(library_dir, ovldata_dir, cache_dir, log=print, install=True, work_dir=None, yaw_sign=1.0, root=None,
              cinema_ovl=None):
    """every tribune of the library becomes its own mod folder ovldata/Mod_TB_<Id>. Returns the installed folders."""
    problems = []
    tribunes = list_library(library_dir, problems)
    log("library: %s (%d tribunes)" % (library_dir, len(tribunes)))
    for pr in problems:
        log("note: skipped broken library entry " + pr)
    if not tribunes:
        raise BuildError("The library is empty (%s). Save a tribune to the library first." % library_dir)
    keys = {}
    for t in tribunes:
        k = ride_key(t["id"])
        if k in keys:
            raise BuildError("Two tribunes in the library get the same game name %s (%s and %s). Change one ID."
                             % (k, keys[k], t["id"]))
        keys[k] = t["id"]
    cinema_ovl = cinema_ovl or find_cinema(ovldata_dir)
    prepare_templates(cinema_ovl, cache_dir, log, root)
    work = work_dir or tempfile.mkdtemp(prefix="tb_build_")
    shutil.rmtree(os.path.join(work, "src"), ignore_errors=True)
    shutil.rmtree(os.path.join(work, "out"), ignore_errors=True)
    built = []
    for t in tribunes:
        out, mod, name, n = _build_one(t, ovldata_dir, cache_dir, work, log, yaw_sign, root)
        built.append((out, mod, name, n))
        log("built %s: %s (%d seats)" % (mod, name, n))
    if not install:
        return [b[0] for b in built]
    if not os.path.isdir(ovldata_dir):
        raise BuildError("ovldata folder not found: %s" % ovldata_dir)
    ours = set(b[1] for b in built)
    for d in os.listdir(ovldata_dir):
        p_ = os.path.join(ovldata_dir, d)
        if d in ours or not os.path.isfile(os.path.join(p_, MARKER)):
            continue
        # the old all-in-one mod, or a tribune that is no longer in the library
        shutil.rmtree(p_)
        log("removed old mod folder " + d)
    targets = []
    for out, mod, name, n in built:
        target = os.path.join(ovldata_dir, mod)
        if os.path.isdir(target):
            if not os.path.isfile(os.path.join(target, MARKER)):
                raise BuildError("%s exists and was not made by this add-on. Please remove it yourself." % target)
            shutil.rmtree(target)
        shutil.copytree(out, target)
        targets.append(target)
        log("in the mod: %s -> %s (%d seats)" % (name, mod, n))
    return targets
