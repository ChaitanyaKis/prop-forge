"""check: read an exported prop back the way an engine would, and test it. Reimports the file into an empty
scene, so what is checked is what was written, not the build scene.

  blender -b --factory-startup --python-exit-code 1 -P check.py -- MODEL.glb [--expect X,Y,Z] [--tol 0.05]
      [--max-tris N] [--min-density 256] [--floor-tol 0.002]

Errors (pass is false until they are fixed):
  size        overall size differs from --expect (metres, x y z) by more than --tol (a fraction)
  manifest    size or triangles differ from <name>.manifest.json written by forge.export (lost parts, unapplied
              modifiers, wrong scale on export)
  ground      the lowest point is not on z=0 (the prop floats or sinks when placed)
  floating    a separate piece touches nothing and isn't on the floor
  inside_out  a closed piece's normals point inward (it renders black or invisible in an engine)
  image_swap  an image wired as a normal map doesn't look like one, or a colour image looks like a normal map
              (glTF writers renaming same-named images have swapped their contents)
  missing     a texture an engine needs is missing or empty
  tris        more triangles than --max-tris
Warnings: non-power-of-two images, texel density below --min-density px/m or uneven between materials (2x),
degenerate faces, open edges on pieces meant to be solid. Prints one line @@JSON@@{...}.
"""
import argparse
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

MARK = "@@JSON@@"


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("model")
    p.add_argument("--expect", default="")
    p.add_argument("--tol", type=float, default=0.05)
    p.add_argument("--max-tris", type=int, default=0)
    p.add_argument("--min-density", type=float, default=256.0)
    p.add_argument("--floor-tol", type=float, default=0.002)
    p.add_argument("--touch-tol", type=float, default=0.003)
    return p.parse_args(a)


def world_co(o):
    me = o.data
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    m = np.array(o.matrix_world)
    return co @ m[:3, :3].T + m[:3, 3]


def islands(n, edges):
    """Island id per vertex (union-find over edges)."""
    parent = np.arange(n)

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for a, b in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    return np.array([find(i) for i in range(n)])


def linked_image(sock, depth=4):
    """The image feeding a socket, through Mix / Normal Map / Separate nodes."""
    if depth < 0 or not sock.is_linked:
        return None
    n = sock.links[0].from_node
    if n.type == "TEX_IMAGE":
        return n.image
    for s in n.inputs:
        if s.is_linked:
            im = linked_image(s, depth - 1)
            if im:
                return im
    return None


def mean_rgb(im, n=64):
    w, h = im.size
    if w == 0 or h == 0:
        return None
    px = np.empty(w * h * 4, dtype=np.float32)
    im.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)[:: max(1, h // n), :: max(1, w // n), :3]
    return px.reshape(-1, 3).mean(0), px.reshape(-1, 3).std(0)


def looks_normal(mean):
    return mean[2] > 0.7 and abs(mean[0] - 0.5) < 0.12 and abs(mean[1] - 0.5) < 0.12


def main():
    a = args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    path = os.path.abspath(a.model)
    bpy.ops.import_scene.gltf(filepath=path)
    sc = bpy.context.scene
    obs = [o for o in sc.objects if o.type == "MESH"]
    bpy.context.view_layer.update()
    errors, warnings = [], []
    if not obs:
        raise RuntimeError("no meshes in " + path)

    allco = np.vstack([world_co(o) for o in obs])
    lo, hi = allco.min(0), allco.max(0)
    size = hi - lo
    tris = 0
    for o in obs:
        o.data.calc_loop_triangles()
        tris += len(o.data.loop_triangles)
    info = {"size": [round(float(v), 4) for v in size], "min": [round(float(v), 4) for v in lo], "tris": tris,
            "objects": len(obs)}

    if a.expect:
        exp = [float(v) for v in a.expect.split(",")]
        for i, axis in enumerate("xyz"):
            if exp[i] > 0 and abs(size[i] - exp[i]) > a.tol * exp[i]:
                errors.append("size: %s is %.3f m, expected %.3f (tolerance %d%%)" % (axis, size[i], exp[i], a.tol * 100))
    man_path = os.path.splitext(path)[0] + ".manifest.json"
    if os.path.exists(man_path):
        man = json.load(open(man_path))
        for i, axis in enumerate("xyz"):
            if abs(man["size"][i] - size[i]) > 0.002 + 0.01 * man["size"][i]:
                errors.append("manifest: %s reads back %.4f m, built %.4f" % (axis, size[i], man["size"][i]))
        if abs(man["tris"] - tris) > max(4, 0.01 * man["tris"]):
            errors.append("manifest: %d triangles read back, %d built" % (tris, man["tris"]))
        info["manifest"] = "compared"
    if abs(lo[2]) > a.floor_tol:
        errors.append("ground: lowest point is z=%.4f, not 0 (%s)" % (lo[2], "floats" if lo[2] > 0 else "sinks"))
    if a.max_tris and tris > a.max_tris:
        errors.append("tris: %d, budget %d" % (tris, a.max_tris))

    # pieces: floating, inside out, open, degenerate
    pieces = []
    for o in obs:
        me = o.data
        co = world_co(o)
        # an importer splits vertices along UV seams and hard edges: weld by position to see the real pieces
        _, weld = np.unique(np.round(co / 1e-5).astype(np.int64), axis=0, return_inverse=True)
        weld = weld.ravel()
        tri_v = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
        me.loop_triangles.foreach_get("vertices", tri_v)
        tw = weld[tri_v.reshape(-1, 3)]
        e = np.sort(np.vstack([tw[:, [0, 1]], tw[:, [1, 2]], tw[:, [2, 0]]]), axis=1)
        ue, cnt = np.unique(e, axis=0, return_counts=True)
        nw = int(weld.max()) + 1
        wco = np.zeros((nw, 3))
        wco[weld] = co
        isl = islands(nw, ue)
        open_isl = set(isl[ue[cnt == 1][:, 0]].tolist())
        p0, p1, p2 = wco[tw[:, 0]], wco[tw[:, 1]], wco[tw[:, 2]]
        area2 = np.linalg.norm(np.cross(p1 - p0, p2 - p0), axis=1)
        degenerate = int((area2 < 2e-10).sum())
        if degenerate:
            warnings.append("degenerate: %s has %d zero-area triangles" % (o.name, degenerate))
        vol = np.einsum("ij,ij->i", p0, np.cross(p1, p2)) / 6.0
        tri_isl = isl[tw[:, 0]]
        for k in np.unique(isl):
            vi = np.where(isl == k)[0]
            if len(vi) < 3:
                continue
            pc = wco[vi]
            closed = k not in open_isl
            if closed and float(vol[tri_isl == k].sum()) < -1e-9:
                errors.append("inside_out: a piece of %s around %s" % (o.name, np.round(pc.mean(0), 3).tolist()))
            pieces.append({"obj": o.name, "lo": pc.min(0), "hi": pc.max(0), "closed": closed})
    floating = []
    t = a.touch_tol
    for i, p in enumerate(pieces):
        if p["lo"][2] <= lo[2] + a.floor_tol:
            continue
        touch = any(j != i and np.all(p["lo"] - t <= q["hi"]) and np.all(q["lo"] - t <= p["hi"]) for j, q in enumerate(pieces))
        if not touch:
            floating.append(p)
            errors.append("floating: a piece of %s at %s touches nothing" % (p["obj"], np.round((p["lo"] + p["hi"]) / 2, 3).tolist()))
    info["pieces"] = len(pieces)
    open_n = sum(1 for p in pieces if not p["closed"])
    if open_n:
        warnings.append("open: %d of %d pieces have open edges (fine for cards and cloth, not for solid parts)" % (open_n, len(pieces)))

    # materials and images
    mats, densities = {}, {}
    for o in obs:
        for m in o.data.materials:
            if not m or m.name in mats or not m.node_tree:
                continue
            b = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if b is None:
                continue
            rec = {}
            for role, sock in (("base", "Base Color"), ("rough", "Roughness"), ("metal", "Metallic"), ("normal", "Normal")):
                im = linked_image(b.inputs[sock])
                if im is None:
                    continue
                w, h = im.size
                rec[role] = {"image": im.name, "size": [w, h]}
                if w == 0 or h == 0:
                    errors.append("missing: %s's %s image %s is empty or missing" % (m.name, role, im.name))
                    continue
                if (w & (w - 1)) or (h & (h - 1)):
                    warnings.append("pot: %s is %dx%d, not a power of two (no mipmaps in some engines)" % (im.name, w, h))
                mr = mean_rgb(im)
                if mr is not None:
                    mean = mr[0]
                    if role == "normal" and not looks_normal(mean):
                        errors.append("image_swap: %s's normal map %s averages %s, not a normal map's (0.5, 0.5, 1)"
                                      % (m.name, im.name, np.round(mean, 2).tolist()))
                    if role == "base" and looks_normal(mean) and mr[1].max() < 0.2:
                        errors.append("image_swap: %s's colour image %s looks like a normal map" % (m.name, im.name))
            mats[m.name] = rec
    # texel density per material: sqrt(uv area * pixels / world area)
    for o in obs:
        me = o.data
        uvl = me.uv_layers.active
        if uvl is None:
            continue
        uv = np.empty(len(me.loops) * 2)
        uvl.data.foreach_get("uv", uv)
        uv = uv.reshape(-1, 2)
        co = world_co(o)
        tl = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
        me.loop_triangles.foreach_get("loops", tl)
        tl = tl.reshape(-1, 3)
        tv = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
        me.loop_triangles.foreach_get("vertices", tv)
        tv = tv.reshape(-1, 3)
        tm = np.empty(len(me.loop_triangles), dtype=np.int64)
        me.loop_triangles.foreach_get("material_index", tm)
        wa = np.linalg.norm(np.cross(co[tv[:, 1]] - co[tv[:, 0]], co[tv[:, 2]] - co[tv[:, 0]]), axis=1) / 2
        u0, u1, u2 = uv[tl[:, 0]], uv[tl[:, 1]], uv[tl[:, 2]]
        ua = np.abs((u1[:, 0] - u0[:, 0]) * (u2[:, 1] - u0[:, 1]) - (u2[:, 0] - u0[:, 0]) * (u1[:, 1] - u0[:, 1])) / 2
        for mi, m in enumerate(me.materials):
            if not m or m.name not in mats or "base" not in mats[m.name]:
                continue
            w, h = mats[m.name]["base"]["size"]
            sel = (tm == mi) & (wa > 1e-8)
            if sel.sum() == 0:
                continue
            d = np.sqrt(ua[sel].sum() * w * h / wa[sel].sum())
            densities.setdefault(m.name, []).append(float(d))
    dens = {k: round(float(np.mean(v)), 1) for k, v in densities.items()}
    for k, v in dens.items():
        if v < a.min_density:
            warnings.append("density: %s shows %.0f px per metre, under %d (blurry up close)" % (k, v, a.min_density))
    if len(dens) > 1 and max(dens.values()) > 2 * min(dens.values()):
        warnings.append("density: uneven between materials %s (sharp next to blurry reads as fake)" % dens)
    info["materials"] = mats
    info["texel_density"] = dens
    out = {"ok": True, "pass": not errors, "errors": errors, "warnings": warnings, "info": info}
    print(MARK + json.dumps(out, default=lambda x: x.tolist() if hasattr(x, "tolist") else str(x)), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(MARK + json.dumps({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}), flush=True)
        sys.exit(1)
