"""Small software renderer for the in-game icon of a tribune (no Blender needed).

render_icon(parts, materials, path_big, path_small)
    parts: list of (material_name, verts, normals, uvs, tris) in Blender coordinates (Z up)
    materials: {name: {"color": (r, g, b) linear}}
Writes two PNG files in the sizes of the game's ride icons (592 x 644 and 152 x 164).
"""
import math

BIG = (592, 644)
SMALL = (152, 164)


def _lin2srgb(c):
    c = max(0.0, min(1.0, c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def _view(direction):
    """orthographic camera looking along 'direction' (x, y, z), Z up"""
    import numpy as np
    f = np.array(direction, float)
    f /= np.linalg.norm(f)
    up = np.array([0.0, 0.0, 1.0])
    r = np.cross(f, up)
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    return r, u, f


def render(parts, materials, size=BIG, direction=(0.55, 1.0, -0.62), supersample=2, background=True):
    """returns a PIL RGBA image"""
    import numpy as np
    from PIL import Image, ImageDraw
    r, u, f = _view(direction)
    light = np.array([-0.35, -0.55, 0.76])
    light /= np.linalg.norm(light)
    tris, cols, depth = [], [], []
    allp = []
    for name, V, N, UV, T in parts:
        V = np.asarray(V, float)
        T = np.asarray(T, int).reshape(-1, 3)
        if len(T) == 0:
            continue
        col = np.array((materials.get(name) or {}).get("color", (0.5, 0.5, 0.5))[:3], float)
        A, B, C = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
        n = np.cross(B - A, C - A)
        ln = np.linalg.norm(n, axis=1)
        ok = ln > 1e-12
        A, B, C, n, ln = A[ok], B[ok], C[ok], n[ok], ln[ok]
        n = n / ln[:, None]
        # two-sided: face the camera
        n[(n @ f) > 0] *= -1
        shade = 0.38 + 0.62 * np.clip(n @ light, 0, 1) + 0.12 * np.clip(n[:, 2], 0, 1)
        c = np.clip(col[None, :] * shade[:, None], 0, 1)
        P = np.stack([A, B, C], 1)
        tris.append(P)
        cols.append(c)
        depth.append((P @ f).mean(1))
        allp.append(P.reshape(-1, 3))
    W, H = size[0] * supersample, size[1] * supersample
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if background:
        t = np.linspace(0, 1, H)[:, None]
        grad = np.zeros((H, W, 4), np.uint8)
        grad[..., 0] = (64 + 70 * t).astype(np.uint8)
        grad[..., 1] = (116 + 60 * t).astype(np.uint8)
        grad[..., 2] = (170 + 50 * t).astype(np.uint8)
        grad[..., 3] = 255
        img = Image.fromarray(grad, "RGBA")
    if not tris:
        return img.resize(size, Image.LANCZOS)
    P = np.concatenate(tris)
    Cc = np.concatenate(cols)
    D = np.concatenate(depth)
    pts = np.concatenate(allp)
    sx, sy = pts @ r, pts @ u
    x0, x1, y0, y1 = sx.min(), sx.max(), sy.min(), sy.max()
    margin = 0.08
    scale = min(W * (1 - 2 * margin) / max(1e-6, x1 - x0), H * (1 - 2 * margin) / max(1e-6, y1 - y0))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    X = (P @ r - cx) * scale + W / 2
    Y = H / 2 - (P @ u - cy) * scale
    order = np.argsort(-D)          # far first
    draw = ImageDraw.Draw(img)
    for i in order:
        rgb = tuple(int(round(_lin2srgb(v) * 255)) for v in Cc[i])
        draw.polygon([(X[i, 0], Y[i, 0]), (X[i, 1], Y[i, 1]), (X[i, 2], Y[i, 2])], fill=rgb + (255,), outline=rgb + (255,))
    return img.resize(size, Image.LANCZOS)


def render_icon(parts, materials, path_big, path_small):
    img = render(parts, materials, BIG)
    img.save(path_big)
    from PIL import Image
    img.resize(SMALL, Image.LANCZOS).save(path_small)
    return path_big, path_small
