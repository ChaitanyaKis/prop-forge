"""silhouette: measure a model's outline against a reference, as numbers rather than an impression.

  blender -b --factory-startup --python-exit-code 1 -P silhouette.py -- MODEL.glb
      (--ref-model SCAN.gltf | --ref-image PHOTO.png) [--view front|side|top] [--out compare.png] [--res 512]

--ref-model  another 3D model (a CC0 scan of a similar object, an earlier version): both are drawn with the same
             orthographic camera at true size, so sizes compare in metres.
--ref-image  a photo, drawing or render of the object from the same side, on a plain background. It has no scale,
             so it is fitted to the model's height first and only proportions compare.
Reports IoU (1.0 is identical) and the outline's width in ten bands from the bottom up, as a fraction of the
height, for both; the overlay picture shows the model alone in red, the reference alone in blue, both in white.
Typical gates: blockout IoU >= 0.85 and every band within 0.05; finished form IoU >= 0.9 and bands within 0.03.
Prints one line @@JSON@@{...}.
"""
import argparse
import json
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

MARK = "@@JSON@@"
VIEWS = {"front": ((0, -1, 0), 0, 2), "side": ((1, 0, 0), 1, 2), "top": ((0, 0, 1), 0, 1)}


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("model")
    p.add_argument("--ref-model", default="")
    p.add_argument("--ref-image", default="")
    p.add_argument("--view", default="front", choices=sorted(VIEWS))
    p.add_argument("--out", default="")
    p.add_argument("--res", type=int, default=512)
    return p.parse_args(a)


def load(path):
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.abspath(path))
    new = [o for o in bpy.context.scene.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH"]
    bpy.context.view_layer.update()
    pts = np.array([list(o.matrix_world @ Vector(c)) for o in meshes for c in o.bound_box])
    lo, hi = pts.min(0), pts.max(0)
    shift = Vector((-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]))   # centred, standing on z=0
    for o in new:
        if o.parent is None:
            o.location += shift
    return meshes, hi - lo


def read_png(path):
    im = bpy.data.images.load(path, check_existing=False)
    w, h = im.size
    px = np.empty(w * h * 4, dtype=np.float32)
    im.pixels.foreach_get(px)
    bpy.data.images.remove(im)
    return px.reshape(h, w, 4)[::-1]          # top row first


def write_png(rgb, path):
    h, w = rgb.shape[:2]
    im = bpy.data.images.new("cmp", w, h, alpha=False)
    px = np.ones((h, w, 4), dtype=np.float32)
    px[..., :3] = rgb[::-1]
    im.pixels.foreach_set(px.ravel())
    im.filepath_raw = path
    im.file_format = "PNG"
    im.save()


def mask_render(objs_on, objs_all, cam, res, path):
    for o in objs_all:
        o.hide_render = o not in objs_on
    sc = bpy.context.scene
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return read_png(path)[..., 0] > 0.5


def crop(m):
    ys, xs = np.where(m)
    if len(ys) == 0:
        raise RuntimeError("empty silhouette")
    return m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def resize(m, h, w):
    yi = (np.arange(h) * m.shape[0] / h).astype(int)
    xi = (np.arange(w) * m.shape[1] / w).astype(int)
    return m[yi][:, xi]


def bands(m, n=10):
    """Width of the outline in n bands from the bottom up, as a fraction of its height."""
    h = m.shape[0]
    out = []
    for i in range(n):
        rows = m[h - (i + 1) * h // n: h - i * h // n]
        if rows.size == 0:
            out.append(0.0)
            continue
        cols = np.where(rows.any(0))[0]
        out.append(round(float(cols.max() - cols.min() + 1) / h, 4) if len(cols) else 0.0)
    return out


def main():
    a = args()
    if not (a.ref_model or a.ref_image):
        raise ValueError("give --ref-model or --ref-image")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    model, msize = load(a.model)
    ref, rsize = (load(a.ref_model) if a.ref_model else ([], None))
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading
    sh.light = "FLAT"
    sh.color_type = "SINGLE"
    sh.single_color = (1, 1, 1)
    w = bpy.data.worlds.new("w")
    w.color = (0, 0, 0)
    sc.world = w
    sc.view_settings.view_transform = "Standard"
    sc.render.film_transparent = False
    sc.render.resolution_x = sc.render.resolution_y = a.res
    sc.render.image_settings.file_format = "PNG"
    d, ui, vi = VIEWS[a.view]
    ext = np.maximum(msize, rsize) if rsize is not None else msize
    cam_d = bpy.data.cameras.new("cam")
    cam_d.type = "ORTHO"
    cam_d.ortho_scale = float(max(ext[ui], ext[vi])) * 1.1
    cam = bpy.data.objects.new("cam", cam_d)
    sc.collection.objects.link(cam)
    sc.camera = cam
    centre = Vector((0, 0, ext[2] / 2)) if a.view != "top" else Vector((0, 0, 0))
    cam.location = centre + Vector(d) * (float(ext.max()) * 3 + 1)
    cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
    stem = os.path.splitext(os.path.abspath(a.out or os.path.splitext(a.model)[0] + "_silhouette.png"))[0]
    every = model + ref
    mm = mask_render(model, every, cam, a.res, stem + "_model_mask.png")
    if ref:
        rm = mask_render(ref, every, cam, a.res, stem + "_ref_mask.png")
        A, B = mm, rm
        scale_note = "same camera, true size"
    else:
        px = read_png(os.path.abspath(a.ref_image))
        rgb = px[..., :3]
        border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
        bg = np.median(border, axis=0)
        rmask = np.linalg.norm(rgb - bg, axis=2) > 0.12
        if px.shape[2] == 4 and px[..., 3].min() < 0.5:
            rmask = px[..., 3] > 0.5
        mc, rc = crop(mm), crop(rmask)
        H = mc.shape[0]
        rw = max(1, int(round(rc.shape[1] * H / rc.shape[0])))
        rc = resize(rc, H, rw)
        W = max(mc.shape[1], rw)
        A = np.zeros((H, W), bool)
        B = np.zeros((H, W), bool)
        A[:, (W - mc.shape[1]) // 2:(W - mc.shape[1]) // 2 + mc.shape[1]] = mc
        B[:, (W - rw) // 2:(W - rw) // 2 + rw] = rc
        scale_note = "photo fitted to the model's height; proportions only"
    inter, union = (A & B).sum(), (A | B).sum()
    iou = float(inter) / max(1, union)
    ba, bb = bands(crop(A)), bands(crop(B))
    diff = [round(x - y, 4) for x, y in zip(ba, bb)]
    rgb = np.zeros(A.shape + (3,), np.float32)
    rgb[A & ~B] = (0.9, 0.15, 0.1)
    rgb[B & ~A] = (0.15, 0.35, 0.95)
    rgb[A & B] = (1, 1, 1)
    out = stem + ".png"
    write_png(rgb, out)
    res = {"ok": True, "iou": round(iou, 4), "bands_model": ba, "bands_ref": bb, "band_diff": diff,
           "worst_band": int(np.argmax(np.abs(diff))), "view": a.view, "overlay": out, "scale": scale_note,
           "model_size": [round(float(v), 4) for v in msize]}
    if rsize is not None:
        res["ref_size"] = [round(float(v), 4) for v in rsize]
    print(MARK + json.dumps(res), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(MARK + json.dumps({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}), flush=True)
        sys.exit(1)
