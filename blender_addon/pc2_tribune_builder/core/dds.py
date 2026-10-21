"""Tiny DDS writer (numpy only): BC5 and BC7 (mode 6) with a full mip chain.

So the mod build needs no texconv: cobra-tools uses a .dds next to the .tex directly.
Quality is plain (one endpoint line per 4x4 block), which is enough for soft bump / roughness patterns.
"""
import struct

DXGI = {"BC5_UNORM": 83, "BC7_UNORM": 98}
_W16 = (0, 4, 9, 13, 17, 21, 26, 30, 34, 38, 43, 47, 51, 55, 60, 64)


def _mips(img):
    """img: HxWxC uint8 -> list of float arrays, halving down to 1x1"""
    import numpy as np
    a = img.astype(np.float32)
    out = [a]
    while a.shape[0] > 1 or a.shape[1] > 1:
        h, w = max(1, a.shape[0] // 2), max(1, a.shape[1] // 2)
        if a.shape[0] > 1:
            a = (a[0::2] + a[1::2]) * 0.5
        if a.shape[1] > 1:
            a = (a[:, 0::2] + a[:, 1::2]) * 0.5
        a = a[:h, :w]
        out.append(a)
    return out


def _blocks(a):
    """HxWxC -> (N, 16, C), padded to whole 4x4 blocks by repeating the edge"""
    import numpy as np
    h, w, c = a.shape
    H, W = max(4, (h + 3) // 4 * 4), max(4, (w + 3) // 4 * 4)
    if (H, W) != (h, w):
        a = np.pad(a, ((0, H - h), (0, W - w), (0, 0)), mode="edge")
    b = a.reshape(H // 4, 4, W // 4, 4, c).transpose(0, 2, 1, 3, 4).reshape(-1, 16, c)
    return b


def _bc4(v):
    """v: (N, 16) float 0..255 -> (N, 8) uint8"""
    import numpy as np
    r0 = np.clip(np.round(v.max(1)), 0, 255).astype(np.int64)
    r1 = np.clip(np.round(v.min(1)), 0, 255).astype(np.int64)
    same = r0 == r1
    r0 = np.where(same & (r0 < 255), r0 + 1, r0)
    r1 = np.where(same & (r0 == 255) & (r1 == 255), 254, r1)
    span = np.maximum(1, r0 - r1)[:, None]
    k = np.clip(np.round((r0[:, None] - v) / span * 7), 0, 7).astype(np.int64)   # 0 = r0 ... 7 = r1
    idx = np.where(k == 0, 0, np.where(k == 7, 1, k + 1))
    bits = np.zeros(len(v), np.uint64)
    for i in range(16):
        bits |= idx[:, i].astype(np.uint64) << np.uint64(3 * i)
    out = np.zeros((len(v), 8), np.uint8)
    out[:, 0] = r0
    out[:, 1] = r1
    for j in range(6):
        out[:, 2 + j] = ((bits >> np.uint64(8 * j)) & np.uint64(255)).astype(np.uint8)
    return out


def _bc5(b):
    import numpy as np
    return np.concatenate([_bc4(b[:, :, 0]), _bc4(b[:, :, 1])], 1)


def _q7(v):
    """8-bit endpoint -> (7-bit value, p-bit) choosing the p-bit per endpoint with the smallest error"""
    import numpy as np
    best = None
    for p in (0, 1):
        c = np.clip(np.round((v - p) / 2.0), 0, 127)
        err = np.abs(c * 2 + p - v).sum(1)
        if best is None:
            best = [c, np.full(len(v), p), err]
        else:
            m = err < best[2]
            best[0] = np.where(m[:, None], c, best[0])
            best[1] = np.where(m, p, best[1])
            best[2] = np.minimum(err, best[2])
    return best[0].astype(np.int64), best[1].astype(np.int64)


def _bc7(b):
    """b: (N, 16, 4) float -> (N, 16) uint8, mode 6"""
    import numpy as np
    # endpoints along the main axis of the block's colours (better than the bounding box diagonal)
    mean = b.mean(1)
    x = b - mean[:, None, :]
    cov = np.einsum("nki,nkj->nij", x, x)
    ax = (b.max(1) - b.min(1)) + 1e-3
    for _ in range(6):
        ax = np.einsum("nij,nj->ni", cov, ax)
        ax /= np.maximum(np.linalg.norm(ax, axis=1, keepdims=True), 1e-9)
    pr = (x * ax[:, None, :]).sum(2)
    lo_v = np.clip(mean + ax * pr.min(1)[:, None], 0, 255)
    hi_v = np.clip(mean + ax * pr.max(1)[:, None], 0, 255)
    c0, p0 = _q7(lo_v)
    c1, p1 = _q7(hi_v)
    e0 = (c0 * 2 + p0[:, None]).astype(np.float32)
    e1 = (c1 * 2 + p1[:, None]).astype(np.float32)
    d = e1 - e0
    dd = np.maximum((d * d).sum(1), 1e-6)
    t = np.clip(((b - e0[:, None, :]) * d[:, None, :]).sum(2) / dd[:, None], 0, 1)
    w = np.array(_W16, np.float32) / 64.0
    idx = np.abs(t[:, :, None] - w[None, None, :]).argmin(2).astype(np.int64)
    # the anchor index (pixel 0) has an implicit 0 top bit: swap the endpoints when needed
    sw = idx[:, 0] >= 8
    c0, c1 = np.where(sw[:, None], c1, c0), np.where(sw[:, None], c0, c1)
    p0, p1 = np.where(sw, p1, p0), np.where(sw, p0, p1)
    idx = np.where(sw[:, None], 15 - idx, idx)
    U = np.uint64
    lo = np.full(len(b), 1 << 6, np.uint64)
    pos = 7
    for ch in range(4):
        lo |= c0[:, ch].astype(U) << U(pos)
        lo |= c1[:, ch].astype(U) << U(pos + 7)
        pos += 14
    lo |= p0.astype(U) << U(63)
    hi = p1.astype(U).copy()
    hi |= idx[:, 0].astype(U) << U(1)
    for i in range(1, 16):
        hi |= idx[:, i].astype(U) << U(4 + 4 * (i - 1))
    out = np.zeros((len(b), 16), np.uint8)
    for j in range(8):
        out[:, j] = ((lo >> U(8 * j)) & U(255)).astype(np.uint8)
        out[:, 8 + j] = ((hi >> U(8 * j)) & U(255)).astype(np.uint8)
    return out


def write_dds(path, img, compression):
    """img: HxWx4 uint8 (RGBA). compression: "BC7_UNORM" or "BC5_UNORM" (uses R and G)"""
    import numpy as np
    img = np.asarray(img)
    h, w = img.shape[:2]
    levels = _mips(img)
    data = []
    for a in levels:
        bl = _blocks(a)
        enc = _bc7(bl[:, :, :4]) if compression == "BC7_UNORM" else _bc5(bl[:, :, :2])
        data.append(enc.tobytes())
    top = len(data[0])
    flags = 0x1 | 0x2 | 0x4 | 0x1000 | 0x20000 | 0x80000
    hdr = struct.pack("<4s7I44x", b"DDS ", 124, flags, h, w, top, 0, len(levels))
    pf = struct.pack("<2I4s5I", 32, 0x4, b"DX10", 0, 0, 0, 0, 0)
    caps = struct.pack("<4I4x", 0x8 | 0x1000 | 0x400000, 0, 0, 0)
    dx10 = struct.pack("<5I", DXGI[compression], 3, 0, 1, 0)
    with open(path, "wb") as f:
        f.write(hdr + pf + caps + dx10)
        for d in data:
            f.write(d)
    return path


def _bc1(b):
    """b: (N, 16, 3) float 0..255 -> (N, 8) uint8, opaque 4-colour mode"""
    import numpy as np
    mean = b.mean(1)
    x = b - mean[:, None, :]
    cov = np.einsum("nki,nkj->nij", x, x)
    ax = (b.max(1) - b.min(1)) + 1e-3
    for _ in range(6):
        ax = np.einsum("nij,nj->ni", cov, ax)
        ax /= np.maximum(np.linalg.norm(ax, axis=1, keepdims=True), 1e-9)
    pr = (x * ax[:, None, :]).sum(2)
    hi_v = np.clip(mean + ax * pr.max(1)[:, None], 0, 255)
    lo_v = np.clip(mean + ax * pr.min(1)[:, None], 0, 255)

    def to565(c):
        r = np.clip(np.round(c[:, 0] * 31 / 255), 0, 31).astype(np.int64)
        g = np.clip(np.round(c[:, 1] * 63 / 255), 0, 63).astype(np.int64)
        bl = np.clip(np.round(c[:, 2] * 31 / 255), 0, 31).astype(np.int64)
        return (r << 11) | (g << 5) | bl

    def from565(v):
        return np.stack([((v >> 11) & 31) * 255 / 31, ((v >> 5) & 63) * 255 / 63, (v & 31) * 255 / 31], 1)
    c0, c1 = to565(hi_v), to565(lo_v)
    sw = c0 < c1
    c0, c1 = np.where(sw, c1, c0), np.where(sw, c0, c1)
    eq = c0 == c1                       # flat block: keep 4-colour mode by nudging an endpoint
    c1 = np.where(eq & (c1 > 0), c1 - 1, c1)
    c0 = np.where(eq & (c1 == c0), c0 + 1, c0)
    e0, e1 = from565(c0), from565(c1)
    pal = np.stack([e0, e1, (2 * e0 + e1) / 3, (e0 + 2 * e1) / 3], 1)          # (N, 4, 3)
    d = ((b[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(3)
    idx = d.argmin(2).astype(np.uint64)
    bits = np.zeros(len(b), np.uint64)
    for i in range(16):
        bits |= idx[:, i] << np.uint64(2 * i)
    out = np.zeros((len(b), 8), np.uint8)
    out[:, 0] = c0 & 255
    out[:, 1] = c0 >> 8
    out[:, 2] = c1 & 255
    out[:, 3] = c1 >> 8
    for j in range(4):
        out[:, 4 + j] = ((bits >> np.uint64(8 * j)) & np.uint64(255)).astype(np.uint8)
    return out


def write_dds_single(path, img, compression="BC1_UNORM"):
    """one mip level only (UI pictures). img: HxWx3/4 uint8, sides multiples of 4"""
    import numpy as np
    img = np.asarray(img)[:, :, :3].astype(np.float32)
    h, w = img.shape[:2]
    data = _bc1(_blocks(img)).tobytes()
    flags = 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000
    hdr = struct.pack("<4s7I44x", b"DDS ", 124, flags, h, w, len(data), 0, 1)
    pf = struct.pack("<2I4s5I", 32, 0x4, b"DX10", 0, 0, 0, 0, 0)
    caps = struct.pack("<4I4x", 0x1000, 0, 0, 0)
    dx10 = struct.pack("<5I", 71, 3, 0, 1, 0)      # DXGI_FORMAT_BC1_UNORM
    with open(path, "wb") as f:
        f.write(hdr + pf + caps + dx10 + data)
    return path
