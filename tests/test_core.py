"""Checks of the generator core (no Blender, no game files needed).

    python -m pytest tests      or      python tests/test_core.py
"""
import io
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "blender_addon", "pc2_tribune_builder"))

import numpy as np  # noqa: E402

from core import assemble, dds, geom, navcheck, textures  # noqa: E402

SHAPES = {
    "straight": [{"kind": "straight", "length": 16, "turn": 0}],
    "corner": [{"kind": "straight", "length": 14, "turn": 0}, {"kind": "straight", "length": 14, "turn": 90}],
    "arena": [{"kind": "straight", "length": 3, "turn": 0}, {"kind": "arc", "radius": 10, "angle": 180, "turn": 0},
              {"kind": "straight", "length": 3, "turn": 0}],
    "wings": [{"kind": "straight", "length": 10, "turn": 0}, {"kind": "straight", "length": 10, "turn": 30},
              {"kind": "straight", "length": 10, "turn": 30}],
}


def params(**kw):
    t = assemble.seat_template()
    p = dict(seat_width=t["width"], seat_depth=t["depth"], sit=t["sit"], seat_bottom=t["bottom"])
    p.update(kw)
    return t, p


def test_every_seat_is_reachable():
    for name, segs in SHAPES.items():
        for extra in ({}, {"access_left": "RAMP", "access_right": "STAIRS"}, {"front_path": False, "rows": 8}):
            _t, p = params(segments=segs, **extra)
            r = geom.generate(p)
            rep = navcheck.check(r["nav"]["verts"], r["nav"]["tris"], r["outline"]["poly"], r["outline"]["kinds"], r["seats"])
            assert not rep["errors"], (name, extra, rep["errors"])
            assert rep["ok_seats"] == sum(1 for s in r["seats"] if not s["free"])


def test_model_normals_point_outwards():
    t, p = params(segments=SHAPES["arena"], rail_infill=True)
    r = geom.generate(p)
    parts, bounds = assemble.model_parts(r, t)
    assert bounds is not None
    for name, V, N, _U, T in parts:
        V, N, T = np.array(V), np.array(N), np.array(T)
        fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
        assert ((fn * N[T].mean(1)).sum(1) < 0).sum() == 0, name


def test_seat_feet_stay_on_the_floor():
    t, p = params(seat_height=-0.04)
    r = geom.generate(p)
    inst = assemble.seat_instances(r, t)
    floor = r["seats"][0]["origin"][2] + 0.04
    per_seat = len(inst["TB Seat frame"][0]) // len(r["seats"])
    assert abs(inst["TB Seat frame"][0][:per_seat, 2].min() - floor) < 1e-6


def test_dds_files_decode():
    from PIL import Image
    tex = textures.floor_textures("DIAMOND", 256)["pnormaltexture"]
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp.dds")
    try:
        dds.write_dds(path, tex, "BC7_UNORM")
        img = np.asarray(Image.open(path).convert("RGBA")).astype(int)
        assert np.abs(img - tex).mean() < 3
    finally:
        if os.path.exists(path):
            os.remove(path)


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
