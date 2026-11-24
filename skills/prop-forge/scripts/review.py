"""review: a photographic review sheet of exported props, rendered in Cycles the way a lead artist would look at
them. It reads the exported files (what the engine will receive), not the build scene.

  blender -b --factory-startup --python-exit-code 1 -P review.py -- MODEL.glb [MODEL2.glb ...] --out sheet.png
      [--views three_quarter,front,side,top,detail] [--clay] [--light studio|warm|dim]
      [--game DIST,HEIGHT,VFOV,SCREEN_H] [--ruler] [--res 640] [--samples 48] [--gap 0.25]

Several models stand side by side along X (a family of variants, or a model next to the reference scan it copies).
Tiles are laid out left to right, top to bottom, in the order of --views, then "game", then "scale":
  three_quarter  from the front right and above: the hero view
  front, side, back, top   straight views, to judge proportions
  detail         close on the top front corner: edges, bevels, texture scale
  game           (--game) seen from the game's camera at the size the player sees it, pixels enlarged
  scale          (--ruler) beside a 1.75 m figure
--clay renders everything in plain grey, to judge form alone. The floor is at z=0 and catches shadows: a part that
floats or sinks shows. Each tile is also saved beside the sheet. Prints one line @@JSON@@{...}.
"""
import argparse
import json
import math
import os
import sys

import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

MARK = "@@JSON@@"
DIRS = {"three_quarter": (0.75, -1.0, 0.6), "front": (0.0, -1.0, 0.12), "side": (1.0, 0.0, 0.12),
        "back": (-0.5, 1.0, 0.35), "top": (0.0, -0.3, 1.0), "left": (-1.0, 0.0, 0.12)}
LIGHTS = {  # key colour, key power scale, fill colour, fill scale, rim scale, world grey
    "studio": ((1.0, 0.96, 0.9), 1.0, (0.88, 0.94, 1.0), 0.3, 0.6, 0.06),
    "warm": ((1.0, 0.72, 0.45), 0.8, (0.45, 0.55, 0.8), 0.12, 0.25, 0.012),
    "dim": ((0.9, 0.85, 0.8), 0.25, (0.6, 0.7, 0.9), 0.08, 0.15, 0.006),
}


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("models", nargs="+")
    p.add_argument("--out", required=True)
    p.add_argument("--views", default="three_quarter,front,side,top,detail")
    p.add_argument("--clay", action="store_true")
    p.add_argument("--light", default="studio", choices=sorted(LIGHTS))
    p.add_argument("--game", default="")
    p.add_argument("--ruler", action="store_true")
    p.add_argument("--res", type=int, default=640)
    p.add_argument("--samples", type=int, default=48)
    p.add_argument("--gap", type=float, default=0.25)
    p.add_argument("--cols", type=int, default=3)
    return p.parse_args(a)


def gpu(sc):
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
    except KeyError:
        return "CPU"
    for t in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
        try:
            prefs.compute_device_type = t
        except TypeError:
            continue
        try:
            prefs.refresh_devices()
        except Exception:
            prefs.get_devices()
        if any(d.type == t for d in prefs.devices):
            for d in prefs.devices:
                d.use = d.type == t
            sc.cycles.device = "GPU"
            return t
    return "CPU"


def mat(name, col, rough):
    m = bpy.data.materials.new(name)
    if m.node_tree is None:
        m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*col, 1.0)
    b.inputs["Roughness"].default_value = rough
    return m


def bounds(objs):
    bpy.context.view_layer.update()
    pts = np.array([list(o.matrix_world @ Vector(c)) for o in objs for c in o.bound_box])
    return Vector(pts.min(0)), Vector(pts.max(0))


def area(name, at, target, power, size, col):
    d = bpy.data.lights.new(name, "AREA")
    d.energy = power
    d.size = size
    d.color = col
    o = bpy.data.objects.new(name, d)
    bpy.context.scene.collection.objects.link(o)
    o.location = at
    o.rotation_euler = (Vector(target) - Vector(at)).to_track_quat("-Z", "Y").to_euler()
    return o


def aim(cam, at, target):
    cam.location = at
    cam.rotation_euler = (Vector(target) - Vector(at)).to_track_quat("-Z", "Y").to_euler()


def load_px(path):
    im = bpy.data.images.load(path, check_existing=False)
    w, h = im.size
    px = np.empty(w * h * 4, dtype=np.float32)
    im.pixels.foreach_get(px)
    bpy.data.images.remove(im)
    return px.reshape(h, w, 4)


def save_px(px, path):
    h, w = px.shape[:2]
    im = bpy.data.images.new("sheet_out", w, h, alpha=False)
    im.pixels.foreach_set(px.astype(np.float32).ravel())
    im.filepath_raw = path
    im.file_format = "PNG"
    im.save()
    bpy.data.images.remove(im)


def main():
    a = args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    models, x = [], 0.0
    for path in a.models:
        before = set(sc.objects)
        bpy.ops.import_scene.gltf(filepath=os.path.abspath(path))
        new = [o for o in sc.objects if o not in before]
        meshes = [o for o in new if o.type == "MESH"]
        if not meshes:
            raise RuntimeError("no meshes in " + path)
        lo, hi = bounds(meshes)
        for o in new:
            if o.parent is None:
                o.location.x += x - lo.x
        models.append({"file": path, "size": [round(v, 4) for v in (hi - lo)], "min_z": round(lo.z, 4)})
        x += (hi.x - lo.x) + a.gap
    props = [o for o in sc.objects if o.type == "MESH"]
    lo, hi = bounds(props)
    c = (lo + hi) / 2
    R = max((hi - lo).length / 2, 0.05)

    floor = bpy.data.objects.new("_floor", bpy.data.meshes.new("_floor"))
    s = max(20.0, R * 40)
    floor.data.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    floor.data.materials.append(mat("_floor", (0.18, 0.18, 0.18), 0.8))
    sc.collection.objects.link(floor)

    key_c, key_k, fill_c, fill_k, rim_k, world = LIGHTS[a.light]
    d = R * 4
    p = 60.0 * d * d
    area("_key", c + Vector((-0.8, -1.0, 1.1)) * d, c, p * key_k, R * 1.5, key_c)
    area("_fill", c + Vector((1.2, -0.7, 0.4)) * d, c, p * fill_k, R * 2.5, fill_c)
    area("_rim", c + Vector((0.6, 1.1, 0.9)) * d, c, p * rim_k, R * 1.2, (1.0, 1.0, 1.0))
    w = bpy.data.worlds.new("_world")
    sc.world = w
    w.color = (world, world, world)
    if w.node_tree is not None:
        bg = next((n for n in w.node_tree.nodes if n.type == "BACKGROUND"), None)
        if bg:
            bg.inputs["Color"].default_value = (world, world, world, 1.0)
            bg.inputs["Strength"].default_value = 1.0

    if a.clay:
        bpy.context.view_layer.material_override = mat("_clay", (0.42, 0.42, 0.42), 0.6)

    fig = None
    if a.ruler:
        r = 0.16
        fig = bpy.data.objects.new("_figure", bpy.data.meshes.new("_figure"))
        import bmesh
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=24, radius1=r, radius2=r, depth=1.75 - 2 * r)
        bmesh.ops.translate(bm, vec=Vector((0, 0, 0.875)), verts=bm.verts)
        for z in (r, 1.75 - r):
            g = bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12, radius=r)
            bmesh.ops.translate(bm, vec=Vector((0, 0, z)), verts=g["verts"])
        bm.to_mesh(fig.data)
        bm.free()
        fig.data.materials.append(mat("_figure", (0.55, 0.5, 0.45), 0.7))
        fig.location = (hi.x + 0.45, c.y, 0)
        sc.collection.objects.link(fig)
        fig.hide_render = True

    sc.render.engine = "CYCLES"
    device = gpu(sc)
    sc.cycles.samples = a.samples
    sc.cycles.use_denoising = True
    sc.view_settings.view_transform = "AgX"
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    cam_d = bpy.data.cameras.new("_cam")
    cam_d.lens = 50
    cam_d.clip_start = 0.005
    cam_d.clip_end = 500
    cam = bpy.data.objects.new("_cam", cam_d)
    sc.collection.objects.link(cam)
    sc.camera = cam
    half = math.atan(18.0 / 50.0)

    stem = os.path.splitext(os.path.abspath(a.out))[0]
    tiles = []

    def shot(view, res_x, res_y):
        sc.render.resolution_x, sc.render.resolution_y = res_x, res_y
        sc.render.resolution_percentage = 100
        path = "%s_%s.png" % (stem, view)
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        tiles.append({"view": view, "file": path})
        return path

    for view in [v.strip() for v in a.views.split(",") if v.strip()]:
        cam_d.type = "PERSP"
        sc.render.use_border = False
        if view == "detail":
            # close on the top front right corner, where edges and texture scale show
            t = Vector((c.x + (hi.x - c.x) * 0.55, lo.y, hi.z))
            aim(cam, t + Vector((0.5, -1.0, 0.7)).normalized() * max(R * 0.7, 0.12), t)
        else:
            if view not in DIRS:
                raise ValueError("unknown view %r (choose from %s, detail)" % (view, ", ".join(DIRS)))
            dist = R / math.sin(half) * 1.08
            aim(cam, c + Vector(DIRS[view]).normalized() * dist, c)
        shot(view, a.res, a.res)

    game = {}
    if a.game:
        dist, height, vfov, screen_h = [float(v) for v in a.game.split(",")]
        cam_d.sensor_fit = "VERTICAL"
        cam_d.angle_y = math.radians(vfov)
        aim(cam, Vector((c.x, c.y - dist, height)), c)
        W, H = int(screen_h * 16 / 9), int(screen_h)
        sc.render.resolution_x, sc.render.resolution_y = W, H
        bpy.context.view_layer.update()
        pts = [world_to_camera_view(sc, cam, o.matrix_world @ Vector(k)) for o in props for k in o.bound_box]
        x0, x1 = min(q.x for q in pts), max(q.x for q in pts)
        y0, y1 = min(q.y for q in pts), max(q.y for q in pts)
        px_h = (y1 - y0) * H
        m = 0.15 * max(x1 - x0, y1 - y0)
        sc.render.use_border = True
        sc.render.use_crop_to_border = True
        sc.render.border_min_x, sc.render.border_max_x = max(0, x0 - m), min(1, x1 + m)
        sc.render.border_min_y, sc.render.border_max_y = max(0, y0 - m), min(1, y1 + m)
        sc.render.filepath = stem + "_game.png"
        bpy.ops.render.render(write_still=True)
        sc.render.use_border = False
        cam_d.sensor_fit = "AUTO"
        cam_d.lens = 50
        tiles.append({"view": "game", "file": stem + "_game.png"})
        game = {"height_px": round(px_h, 1), "px_per_metre": round(px_h / max(hi.z - lo.z, 1e-6), 1)}

    if fig is not None:
        fig.hide_render = False
        l2, h2 = bounds(props + [fig])
        c2 = (l2 + h2) / 2
        R2 = (h2 - l2).length / 2
        aim(cam, c2 + Vector((0.0, -1.0, 0.1)).normalized() * (R2 / math.sin(half) * 1.05), c2)
        shot("scale", a.res, a.res)
        fig.hide_render = True

    # the sheet: tiles left to right, top to bottom; the small game picture enlarged with whole pixels
    res, cols = a.res, max(1, min(a.cols, len(tiles)))
    rows = (len(tiles) + cols - 1) // cols
    sheet = np.full((rows * res, cols * res, 4), 0.11, dtype=np.float32)
    sheet[..., 3] = 1.0
    for i, t in enumerate(tiles):
        px = load_px(t["file"])
        h, w = px.shape[:2]
        if (w, h) != (res, res):
            k = max(1, min(res // max(w, 1), res // max(h, 1)))
            px = np.repeat(np.repeat(px, k, axis=0), k, axis=1)[:res, :res]
            h, w = px.shape[:2]
        r, cc = i // cols, i % cols
        y0 = (rows - 1 - r) * res + (res - h) // 2
        x0 = cc * res + (res - w) // 2
        sheet[y0:y0 + h, x0:x0 + w] = px
    save_px(sheet, os.path.abspath(a.out))
    print(MARK + json.dumps({"ok": True, "sheet": os.path.abspath(a.out), "order": [t["view"] for t in tiles],
                             "tiles": [t["file"] for t in tiles], "models": models, "device": device,
                             "light": a.light, "clay": a.clay, "game": game}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(MARK + json.dumps({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}), flush=True)
        sys.exit(1)
