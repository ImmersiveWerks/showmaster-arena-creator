"""Procedural surface textures (seamless, 2048 x 2048) for floors and seats.

Floors (normal map, RGB = DirectX tangent normal, A = ambient occlusion):
    DIAMOND   metal diamond plate (raised lenses in a herringbone pattern)
    STUDS     round studs in a grid
    CONCRETE  concrete with grunge noise (plus a roughness map)
Seats (roughness map, R = metal, G = roughness):
    SCRATCHED scratched plastic

One texture tile covers 'size' metres (the UVs of the meshes are made with box_uv()).
"""
import math

SIZE = 2048

FLOOR_PATTERNS = ("NONE", "DIAMOND", "STUDS", "CONCRETE")
SEAT_PATTERNS = ("NONE", "SCRATCHED")


# ------------------------------------------------------------------ UVs (shared by add-on and app)


def box_uv(p, n, size):
    """UV of point p (x, y, z) on a face with normal n: planar projection along the main axis of n,
    one texture tile per 'size' metres"""
    ax, ay, az = abs(n[0]), abs(n[1]), abs(n[2])
    s = 1.0 / max(1e-6, size)
    if az >= ax and az >= ay:
        return p[0] * s, p[1] * s
    if ax >= ay:
        return p[1] * s, p[2] * s
    return p[0] * s, p[2] * s


# ------------------------------------------------------------------ helpers


def _grid(n=SIZE):
    import numpy as np
    v = (np.arange(n) + 0.5) / n
    return np.meshgrid(v, v)


def _noise(n, beta, seed):
    """seamless fractal noise (1/f^beta spectrum), normalised to 0..1"""
    import numpy as np
    rng = np.random.default_rng(seed)
    w = rng.standard_normal((n, n))
    F = np.fft.fft2(w)
    fx = np.fft.fftfreq(n)[None, :]
    fy = np.fft.fftfreq(n)[:, None]
    f = np.sqrt(fx * fx + fy * fy)
    f[0, 0] = 1.0
    F = F / f ** beta
    F[0, 0] = 0
    h = np.real(np.fft.ifft2(F))
    h -= h.min()
    return h / max(1e-9, h.max())


def _normal_from_height(h, strength):
    """seamless tangent-space normal map (DirectX: green = -Y) from a height field 0..1"""
    import numpy as np
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5 * strength
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5 * strength
    nx, ny, nz = -dx, dy, np.ones_like(h)          # image rows go down = -V (DirectX convention)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    return nx / ln, ny / ln, nz / ln


def _pack_normal(nx, ny, nz, ao):
    import numpy as np
    out = np.zeros(nx.shape + (4,), np.uint8)
    out[..., 0] = np.clip((nx * 0.5 + 0.5) * 255, 0, 255)
    out[..., 1] = np.clip((-ny * 0.5 + 0.5) * 255, 0, 255)
    out[..., 2] = np.clip((nz * 0.5 + 0.5) * 255, 0, 255)
    out[..., 3] = np.clip(ao * 255, 0, 255)
    return out


# ------------------------------------------------------------------ floors


def _diamond_height(n):
    import numpy as np
    u, v = _grid(n)
    cells = 8                                   # lenses per tile edge
    cu, cv = u * cells, v * cells
    iu, iv = np.floor(cu), np.floor(cv)
    fu, fv = cu - iu - 0.5, cv - iv - 0.5
    flip = ((iu + iv) % 2) == 1                 # alternate the direction (+45 / -45 degrees): diamond plate look
    a = np.where(flip, -fu, fu)
    b = fv
    r1 = (a + b) / math.sqrt(2)
    r2 = (a - b) / math.sqrt(2)
    lens = (r1 / 0.46) ** 2 + (r2 / 0.1) ** 2
    h = np.clip(1.0 - lens, 0, 1) ** 0.5
    return h


def _studs_height(n):
    import numpy as np
    u, v = _grid(n)
    cells = 10
    fu = (u * cells) % 1.0 - 0.5
    fv = (v * cells) % 1.0 - 0.5
    r = np.sqrt(fu * fu + fv * fv) / 0.3
    return np.clip(1.0 - r * r, 0, 1) ** 0.5


def floor_textures(kind, n=SIZE):
    """returns {"pnormaltexture": RGBA array, "proughnesspackedtexture": RGBA array or None}"""
    import numpy as np
    kind = (kind or "NONE").upper()
    if kind == "NONE":
        return {}
    rough = None
    if kind == "DIAMOND":
        h = _diamond_height(n)
        nx, ny, nz = _normal_from_height(h, n / 90.0)
        ao = 0.82 + 0.18 * h
    elif kind == "STUDS":
        h = _studs_height(n)
        nx, ny, nz = _normal_from_height(h, n / 70.0)
        ao = 0.8 + 0.2 * np.clip(h * 3, 0, 1)
    elif kind == "CONCRETE":
        h = 0.6 * _noise(n, 1.6, 7) + 0.4 * _noise(n, 1.1, 11)
        pits = _noise(n, 0.6, 13)
        h = h - 0.35 * (pits > 0.82)                 # small pores
        nx, ny, nz = _normal_from_height(h, n / 160.0)
        ao = 0.78 + 0.22 * np.clip((h - h.min()) / max(1e-9, np.ptp(h)), 0, 1)
        grunge = _noise(n, 1.3, 17)
        rough = np.zeros((n, n, 4), np.uint8)
        rough[..., 0] = 0                                       # not metal
        rough[..., 1] = np.clip((0.72 + 0.22 * (grunge - 0.5)) * 255, 0, 255)
        rough[..., 2] = 127
        rough[..., 3] = 255
    else:
        return {}
    out = {"pnormaltexture": _pack_normal(nx, ny, nz, ao)}
    if rough is not None:
        out["proughnesspackedtexture"] = rough
    return out


# ------------------------------------------------------------------ seats


def seat_textures(kind, base_roughness=0.5, n=SIZE):
    """scratched plastic: roughness map (glossy plastic, matt scratches and wear) plus a normal map with
    the scratch grooves, so the scratches also show in flat light"""
    import numpy as np
    kind = (kind or "NONE").upper()
    if kind != "SCRATCHED":
        return {}
    rng = np.random.default_rng(23)
    # scratches: thin straight lines in random directions (drawn on a wrapped canvas = seamless)
    from PIL import Image, ImageDraw, ImageFilter
    canvas = Image.new("L", (n, n), 0)
    d = ImageDraw.Draw(canvas)
    for _ in range(520):
        x, y = rng.uniform(0, n, 2)
        ang = rng.uniform(0, math.pi)
        ln = rng.uniform(0.015, 0.14) * n * (2.0 if rng.random() < 0.08 else 1.0)
        w = int(rng.choice([1, 2, 2, 3, 4]))
        val = int(rng.integers(90, 256))
        dx, dy = math.cos(ang) * ln, math.sin(ang) * ln
        for ox in (-n, 0, n):
            for oy in (-n, 0, n):
                d.line([(x + ox, y + oy), (x + dx + ox, y + dy + oy)], fill=val, width=w)
    sc = np.asarray(canvas, np.float32) / 255.0
    soft = np.asarray(canvas.filter(ImageFilter.GaussianBlur(2.5)), np.float32) / 255.0
    wear = _noise(n, 1.2, 29)
    gloss = min(0.4, float(base_roughness))                       # the plastic itself is fairly glossy
    g = gloss + 0.18 * np.clip(wear - 0.45, 0, 1) + 0.5 * sc      # worn patches and scratches are matt
    rough = np.zeros((n, n, 4), np.uint8)
    rough[..., 0] = 0
    rough[..., 1] = np.clip(g * 255, 0, 255)
    rough[..., 2] = 127
    rough[..., 3] = 255
    h = 0.6 * (1.0 - soft) + 0.02 * wear                           # grooves
    nx, ny, nz = _normal_from_height(h, n / 40.0)
    ao = 1.0 - 0.25 * soft
    return {"proughnesspackedtexture": rough, "pnormaltexture": _pack_normal(nx, ny, nz, ao)}


def save_png(arr, path):
    from PIL import Image
    Image.fromarray(arr, "RGBA").save(path)
