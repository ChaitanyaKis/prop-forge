"""measure: take real proportions from a reference model (a CC0 scan of a similar object, or any glTF/GLB), as
numbers to put in a brief and copy into a build script.

  blender -b --factory-startup --python-exit-code 1 -P measure.py -- REF.gltf [--bands 12] [--object NAME]

For the whole model and each object in it: size (x width, y depth, z height, metres), lowest point, and a profile in
height bands from the floor up. Each band gives its width and depth (the extent of the surface in that slice) and
its radius (the farthest point from the vertical axis through the object's centre): for turned things (candlesticks,
bottles, legs, balusters) the radius column is the lathe profile. Prints one line @@JSON@@{...}.
"""
import argparse
import json
import os
import sys

import bpy
import numpy as np

MARK = "@@JSON@@"


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("model")
    p.add_argument("--bands", type=int, default=12)
    p.add_argument("--object", default="")
    return p.parse_args(a)


def points(o):
    me = o.data
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    m = np.array(o.matrix_world)
    return co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]


def profile(pts, n):
    lo, hi = pts.min(0), pts.max(0)
    c = (lo + hi) / 2
    out = []
    for i in range(n):
        z0 = lo[2] + (hi[2] - lo[2]) * i / n
        z1 = lo[2] + (hi[2] - lo[2]) * (i + 1) / n
        sel = pts[(pts[:, 2] >= z0) & (pts[:, 2] <= z1)]
        if len(sel) == 0:
            out.append({"z": [round(z0, 4), round(z1, 4)], "width": 0, "depth": 0, "radius": 0})
            continue
        r = np.hypot(sel[:, 0] - c[0], sel[:, 1] - c[1]).max()
        out.append({"z": [round(float(z0), 4), round(float(z1), 4)],
                    "width": round(float(sel[:, 0].max() - sel[:, 0].min()), 4),
                    "depth": round(float(sel[:, 1].max() - sel[:, 1].min()), 4), "radius": round(float(r), 4)})
    return out


def summary(pts, n):
    lo, hi = pts.min(0), pts.max(0)
    return {"size": [round(float(v), 4) for v in hi - lo], "min": [round(float(v), 4) for v in lo],
            "max": [round(float(v), 4) for v in hi], "bands": profile(pts, n)}


def main():
    a = args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=os.path.abspath(a.model))
    bpy.context.view_layer.update()
    obs = [o for o in bpy.context.scene.objects if o.type == "MESH" and (not a.object or o.name == a.object)]
    if not obs:
        raise RuntimeError("no meshes" + (" named " + a.object if a.object else ""))
    allp = np.vstack([points(o) for o in obs])
    res = {"ok": True, "model": os.path.abspath(a.model), "whole": summary(allp, a.bands),
           "objects": {o.name: summary(points(o), a.bands) for o in obs} if len(obs) > 1 else {}}
    print(MARK + json.dumps(res), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(MARK + json.dumps({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}), flush=True)
        sys.exit(1)
