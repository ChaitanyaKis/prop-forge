"""forge: building blocks for prop build scripts (Blender 5.2+, headless).

A build script imports this module, describes the prop part by part in real units, and exports it:

    import sys; sys.path.insert(0, r"<skill>/scripts"); import forge as F
    F.begin("oak_stool", out_dir)                      # empty scene, output folders
    wood = F.pbr("oak", tex="textures/oak_veneer_01", metres=1.0)
    F.box("seat", (0.34, 0.34, 0.035), (0, 0, 0.43), wood, bevel=0.004)
    ...
    F.export()                                          # GLB + manifest.json beside it

Conventions: metres, Z up, the prop's front faces -Y, origin on the floor at the middle of the footprint.
Rotations are in degrees. Every function returns the object it made, so a script can move or deform it.
Objects whose names start with "_" are helpers and are never exported.
"""
import json
import math
import os
import random
import re
import shutil

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector

STATE = {"name": None, "out": None, "tex": None, "seed": None, "max_tex": 2048}
MARK = "@@JSON@@"


# --------------------------------------------------------------------------------------------------------------- scene
def begin(name, out_dir, seed=0, max_tex=2048, force=False):
    """Start a prop: an empty scene (headless only, so a live session's work is never wiped), output folders
    <out_dir>/<name>.glb and <out_dir>/<name>_tex/ for the textures it writes."""
    if not bpy.app.background and not force:
        raise RuntimeError("forge.begin() empties the scene; run build scripts headless (blender -b), or pass force=True")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0
    os.makedirs(out_dir, exist_ok=True)
    STATE.update(name=name, out=os.path.abspath(out_dir), tex=os.path.join(os.path.abspath(out_dir), name + "_tex"),
                 seed=seed, max_tex=max_tex)
    if os.path.isdir(STATE["tex"]):
        shutil.rmtree(STATE["tex"])
    os.makedirs(STATE["tex"])
    return random.Random(seed)


def _link(obj):
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _obj(name, bm, at, rot, mat):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = _link(bpy.data.objects.new(name, me))
    o.location = Vector(at)
    o.rotation_euler = Euler([math.radians(a) for a in rot])
    if mat is not None:
        me.materials.append(mat)
    return o


# ---------------------------------------------------------------------------------------------------------- materials
KINDS = {  # map kind -> name endings, Poly Haven and ambientCG spellings (lower case, without extension)
    "albedo": ("_diff", "_diffuse", "_albedo", "_color", "_basecolor", "_base_color", "_col"),
    "normal": ("_nor_gl", "_normalgl", "_normal_gl", "_normal", "_nrm", "_nor"),
    "arm": ("_arm", "_orm"),
    "rough": ("_rough", "_roughness"),
    "metal": ("_metal", "_metallic", "_metalness"),
}


def find_maps(folder):
    """{kind: path} for the texture set in `folder`. OpenGL normals are preferred (DirectX ones are skipped)."""
    found = {}
    for f in sorted(os.listdir(folder)):
        stem, ext = os.path.splitext(f.lower())
        if ext not in (".jpg", ".jpeg", ".png", ".tga", ".tif", ".tiff", ".exr", ".webp"):
            continue
        if "nor_dx" in stem or "normaldx" in stem or "normal_dx" in stem:
            continue
        stem = re.sub(r"_(\d+k|\d+)$", "", stem)            # dark_wood_diff_2k -> dark_wood_diff
        stem = re.sub(r"_\d+k-(jpg|png)", "", stem)          # Wood049_2K-JPG_Color -> wood049_color
        for kind, ends in KINDS.items():
            if kind not in found and any(stem.endswith(e) or stem == e[1:] for e in ends):
                found[kind] = os.path.join(folder, f)
    return found


def _pot(n):
    return 1 << max(0, int(round(math.log2(max(1, n)))))


def _box_blur(a, r):
    """Box blur of an (h, w, c) array with radius r, wrapping at the edges (photo textures tile)."""
    for axis in (0, 1):
        n = a.shape[axis]
        k = min(r, n // 2 - 1)
        if k < 1:
            continue
        pad = np.concatenate([np.take(a, range(n - k - 1, n), axis=axis), a, np.take(a, range(0, k), axis=axis)],
                             axis=axis)
        cs = np.cumsum(pad, axis=axis, dtype=np.float64)
        hi = np.take(cs, range(2 * k + 1, n + 2 * k + 1), axis=axis)
        lo = np.take(cs, range(0, n), axis=axis)
        a = ((hi - lo) / (2 * k + 1)).astype(np.float32)
    return a


def _image(src, unique, non_color, tint=None, mul=None, channel=None, flatten=0.0):
    """Load `src`, optionally multiply its colour (`tint`) or a value (`mul`), make it a power of two no bigger than
    max_tex, and save it as <tex>/<unique>.<ext>: every image an asset uses gets a name of its own, because glTF
    writers rename clashing names (albedo.jpg, albedo.jpg) and can swap their contents."""
    im = bpy.data.images.load(src, check_existing=False)
    w, h = im.size
    tw, th = min(_pot(w), STATE["max_tex"]), min(_pot(h), STATE["max_tex"])
    changed = (tw, th) != (w, h) or tint is not None or mul is not None or flatten > 0
    if (tw, th) != (w, h):
        im.scale(tw, th)
    if flatten > 0:
        # take out the photo's large blotches (uneven lighting, stains) and keep its fine detail: divide by a heavy
        # blur, put the average back, and mix by `flatten`
        px = np.empty(tw * th * 4, dtype=np.float32)
        im.pixels.foreach_get(px)
        px = px.reshape(th, tw, 4)
        rgb = px[..., :3]
        low = _box_blur(_box_blur(rgb, max(2, tw // 16)), max(2, tw // 16))
        flat_rgb = rgb / np.maximum(low, 1e-3) * low.reshape(-1, 3).mean(0)
        px[..., :3] = rgb + (flat_rgb - rgb) * float(flatten)
        np.clip(px, 0, 1, out=px)
        im.pixels.foreach_set(px.ravel())
    if tint is not None or mul is not None:
        px = np.empty(tw * th * 4, dtype=np.float32)
        im.pixels.foreach_get(px)
        px = px.reshape(-1, 4)
        if tint is not None:
            px[:, :3] *= np.asarray(tint[:3], dtype=np.float32)
        if mul is not None:
            ch = slice(0, 3) if channel is None else slice(channel, channel + 1)
            px[:, ch] *= mul
        np.clip(px, 0, 1, out=px)
        im.pixels.foreach_set(px.ravel())
    ext = os.path.splitext(src)[1].lower()
    if ext == ".jpeg":
        ext = ".jpg"
    if ext not in (".jpg", ".png"):
        ext, changed = ".png", True
    dst = os.path.join(STATE["tex"], unique + ext)
    if changed:
        im.filepath_raw = dst
        im.file_format = "JPEG" if ext == ".jpg" else "PNG"
        try:
            im.save(quality=92)
        except TypeError:
            im.save()
    else:
        shutil.copyfile(src, dst)
    bpy.data.images.remove(im)
    out = bpy.data.images.load(dst, check_existing=True)
    out.name = unique
    if non_color:
        out.colorspace_settings.name = "Non-Color"
    return out


def _tex_node(nt, im, x, y):
    n = nt.nodes.new("ShaderNodeTexImage")
    n.image = im
    n.location = (x, y)
    return n


def pbr(name, tex=None, metres=1.0, tint=None, color=(0.5, 0.5, 0.5), rough=0.6, metal=0.0, normal=1.0,
        rough_mul=None, maps=None, grain="u", flatten=0.0):
    """A Principled material. With `tex` (a folder holding one texture set) or `maps` ({kind: path}) it reads the
    photographed albedo, normal and roughness (packed ARM/ORM, or a roughness map); without them it is a plain
    `color`/`rough`/`metal` surface. `metres` is how much surface one repeat of the photo covers (Poly Haven lists
    it as the texture's dimensions): UVs made by this module use it, so every part shows the grain at true size.
    `tint` multiplies the albedo and `rough_mul` the roughness; both are baked into the asset's own copies of the
    images (an engine reads plain textures, not node maths). `grain` says which way the photo's grain, weave or
    brush strokes run: "u" across the image, "v" up it. Look at the albedo once; parts lay it along their length.
    `flatten` (0..1) takes out the photo's large blotches and uneven lighting while keeping fine detail: use 0.4-0.7
    when a scan's stains or shading read as camouflage on small parts."""
    m = bpy.data.materials.new(name)
    if m.node_tree is None:
        m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (400, 0)
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    m["metres"] = float(metres)
    m["grain"] = grain
    found = dict(maps or {})
    if tex:
        found = {**find_maps(tex), **found}
    if not found:
        c = tuple(color[:3])
        if tint is not None:
            c = tuple(c[i] * tint[i] for i in range(3))
        b.inputs["Base Color"].default_value = (*c, 1.0)
        m.diffuse_color = (*c, 1.0)
        return m
    if "albedo" in found:
        im = _image(found["albedo"], name + "_albedo", False, tint=tint, flatten=flatten)
        nt.links.new(_tex_node(nt, im, -500, 300).outputs["Color"], b.inputs["Base Color"])
    if "arm" in found:
        # glTF's metallicRoughness texture is laid out like ARM (G roughness, B metal): one image serves both
        im = _image(found["arm"], name + "_arm", True, mul=rough_mul, channel=1)
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(_tex_node(nt, im, -500, 0).outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Green"], b.inputs["Roughness"])
        nt.links.new(sep.outputs["Blue"], b.inputs["Metallic"])
    elif "rough" in found:
        im = _image(found["rough"], name + "_rough", True, mul=rough_mul)
        nt.links.new(_tex_node(nt, im, -500, 0).outputs["Color"], b.inputs["Roughness"])
    if "metal" in found and "arm" not in found:
        im = _image(found["metal"], name + "_metal", True)
        nt.links.new(_tex_node(nt, im, -500, -150).outputs["Color"], b.inputs["Metallic"])
    if "normal" in found:
        im = _image(found["normal"], name + "_normal", True)
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = normal
        nt.links.new(_tex_node(nt, im, -500, -300).outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    return m


def flat(name, color, rough=0.5, metal=0.0):
    """A plain material: painted, glazed or metal surfaces that need no photo (small brass fittings, glass)."""
    return pbr(name, color=color, rough=rough, metal=metal)


# -------------------------------------------------------------------------------------------------------------- UVs
def _mat_info(obj, metres):
    mats = [m for m in obj.data.materials if m]
    m = mats[0] if mats else None
    if metres is None:
        metres = m.get("metres", 1.0) if m else 1.0
    return metres, (m.get("grain", "u") if m else "u")


def uv_box(obj, metres=None, grain="long", rng=None):
    """Box-projected UVs in the object's own space, `metres` per texture repeat (default: the material's).
    grain="long" lays the photo's grain (the material's `grain` direction) along the part's longest axis, as wood
    runs along a board; a number 0/1/2 names the axis instead, None leaves it. `rng` shifts each part to a
    different patch of the photo, so neighbouring boards don't show the same knot."""
    metres, photo = _mat_info(obj, metres)
    me = obj.data
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    ext = co.max(0) - co.min(0) if len(co) else np.ones(3)
    g = int(np.argmax(ext)) if grain == "long" else (grain if isinstance(grain, int) else None)
    off = (rng.random() * 7.3, rng.random() * 7.3) if rng else (0.0, 0.0)
    bm = bmesh.new()
    bm.from_mesh(me)
    uv = bm.loops.layers.uv.verify()
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        a, b = [(1, 2), (0, 2), (0, 1)][ax]
        if g in (a, b):                      # the long axis lies in this face: put it on the photo's grain
            other = b if g == a else a
            a, b = (g, other) if photo == "u" else (other, g)
        for lp in f.loops:
            p = lp.vert.co
            lp[uv].uv = (p[a] / metres + off[0], p[b] / metres + off[1])
    bm.to_mesh(me)
    bm.free()
    return obj


def uv_cylinder(obj, metres=None, axis=2):
    """Cylindrical UVs in metres around `axis` (turned and lathed parts), the photo's grain along the axis."""
    metres, photo = _mat_info(obj, metres)
    a, b = [(1, 2), (0, 2), (0, 1)][axis]
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    uv = bm.loops.layers.uv.verify()
    for f in bm.faces:
        c = f.calc_center_median()
        fa = math.atan2(c[b], c[a])
        for lp in f.loops:
            p = lp.vert.co
            ang = math.atan2(p[b], p[a])
            if ang - fa > math.pi:              # keep a face's loops on one side of the seam
                ang -= 2 * math.pi
            elif fa - ang > math.pi:
                ang += 2 * math.pi
            around = ang * max(math.hypot(p[a], p[b]), 1e-4) / metres
            along = p[axis] / metres
            lp[uv].uv = (along, around) if photo == "u" else (around, along)
    bm.to_mesh(obj.data)
    bm.free()
    return obj


# --------------------------------------------------------------------------------------------------------- finishing
def apply_mods(obj):
    """Apply every modifier through the data API (no operator context needed)."""
    if not obj.modifiers:
        return obj
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    old = obj.data
    obj.modifiers.clear()
    obj.data = me
    me.name = obj.name
    if old.users == 0:
        bpy.data.meshes.remove(old)
    return obj


def bevel(obj, width, segs=3, angle=30.0, harden=True):
    """Round every edge sharper than `angle` degrees. Real objects have no knife edges: a 1-4 mm bevel is what
    makes a box read as a made thing, because it catches a line of light along each edge."""
    if width <= 0:
        return obj
    mod = obj.modifiers.new("bevel", "BEVEL")
    mod.width = width
    mod.segments = segs
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(angle)
    mod.use_clamp_overlap = True
    mod.miter_outer = "MITER_ARC"
    mod.harden_normals = harden
    return apply_mods(obj)


def smooth(obj, angle=35.0):
    """Smooth shading with edges sharper than `angle` degrees kept crisp."""
    me = obj.data
    try:
        me.shade_smooth()
        me.set_sharp_from_angle(angle=math.radians(angle))
    except AttributeError:                       # older API
        for p in me.polygons:
            p.use_smooth = True
    return obj


def subdivide(obj, levels=1, simple=False):
    mod = obj.modifiers.new("sub", "SUBSURF")
    mod.levels = levels
    mod.render_levels = levels
    mod.subdivision_type = "SIMPLE" if simple else "CATMULL_CLARK"
    return apply_mods(obj)


def _finish(o, mat, bevel_w, segs, uv, rng, grain, sharp_angle=35.0):
    if bevel_w:
        # smooth first, then a bevel with hardened normals: flat faces stay flat, the rounds shade softly
        try:
            o.data.shade_smooth()
        except AttributeError:
            for p in o.data.polygons:
                p.use_smooth = True
        bevel(o, bevel_w, segs)
    else:
        smooth(o, sharp_angle)
    if mat is not None and uv == "box":
        uv_box(o, grain=grain, rng=rng)
    elif mat is not None and uv == "cyl":
        uv_cylinder(o)
    return o


# ---------------------------------------------------------------------------------------------------------- shapes
def box(name, size, at=(0, 0, 0), mat=None, bevel=0.003, segs=3, rot=(0, 0, 0), rng=None, grain="long"):
    """A block `size` (x, y, z) centred on `at`. The bevel is capped at a quarter of the thinnest side."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
    o = _obj(name, bm, at, rot, mat)
    return _finish(o, mat, min(bevel, 0.25 * min(size)), segs, "box", rng, grain)


def cyl(name, r, h, at=(0, 0, 0), mat=None, verts=None, bevel=0.002, r_top=None, rot=(0, 0, 0), rng=None,
        uv="cyl"):
    """A cylinder (or a taper, with `r_top`) standing on Z, `at` its centre. Sides follow its size: a peg 8 to 12,
    a leg 16 to 24, a barrel 48 or more, so a curve never shows facets at the distance it is seen from."""
    if verts is None:
        verts = int(min(64, max(12, round(2 * math.pi * max(r, r_top or 0) / 0.012 / 4) * 4)))
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=verts, radius1=r,
                          radius2=r if r_top is None else r_top, depth=h)
    o = _obj(name, bm, at, rot, mat)
    return _finish(o, mat, min(bevel, 0.25 * min(r, h)), 2, uv, rng, 2)


def sphere(name, r, at=(0, 0, 0), mat=None, scale=(1, 1, 1), segs=24, rot=(0, 0, 0)):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=max(8, segs // 2), radius=r)
    for v in bm.verts:
        v.co = Vector((v.co.x * scale[0], v.co.y * scale[1], v.co.z * scale[2]))
    o = _obj(name, bm, at, rot, mat)
    smooth(o, 80.0)
    if mat is not None:
        uv_cylinder(o)
    return o


def lathe(name, profile, at=(0, 0, 0), mat=None, segs=48, rot=(0, 0, 0), sharp=40.0):
    """A turned part: `profile` is a list of (radius, z) from the bottom up, revolved about Z. Go up the outside
    and back down the inside to give a cup, bowl or jug a wall; a radius of 0 at either end closes it to a point,
    any other end is capped flat. Bottles, jugs, cups, bowls, candlesticks, finials, turned legs, knobs."""
    bm = bmesh.new()
    rings = []
    for (rad, z) in profile:
        if rad <= 1e-6:
            rings.append([bm.verts.new((0.0, 0.0, z))])
        else:
            rings.append([bm.verts.new((rad * math.cos(2 * math.pi * i / segs), rad * math.sin(2 * math.pi * i / segs), z))
                          for i in range(segs)])
    for r0, r1 in zip(rings, rings[1:]):
        for i in range(segs):
            j = (i + 1) % segs
            if len(r0) == 1 and len(r1) == 1:
                continue
            if len(r0) == 1:
                bm.faces.new((r0[0], r1[i], r1[j]))
            elif len(r1) == 1:
                bm.faces.new((r0[i], r1[0], r0[j]))
            else:
                bm.faces.new((r0[i], r0[j], r1[j], r1[i]))
    if len(rings[0]) > 1:
        bm.faces.new(list(reversed(rings[0])))
    if len(rings[-1]) > 1:
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = _obj(name, bm, at, rot, mat)
    smooth(o, sharp)
    if mat is not None:
        uv_cylinder(o)
    return o


def extrude(name, outline, depth, at=(0, 0, 0), mat=None, plane="XZ", bevel=0.002, segs=2, rot=(0, 0, 0), rng=None,
            grain="long"):
    """A flat shape cut from a board: `outline` is a list of 2D points (counter-clockwise) in `plane`, extruded
    `depth` through it, centred. Chair backs, brackets, aprons with a curved underside, mouldings, shelf ends."""
    ax = {"XZ": (0, 2, 1), "XY": (0, 1, 2), "YZ": (1, 2, 0)}[plane]
    bm = bmesh.new()
    vs = []
    for (u, v) in outline:
        p = [0.0, 0.0, 0.0]
        p[ax[0]], p[ax[1]], p[ax[2]] = u, v, -depth / 2
        vs.append(bm.verts.new(p))
    f = bm.faces.new(vs)
    d = [0.0, 0.0, 0.0]
    d[ax[2]] = depth
    ext = bmesh.ops.extrude_face_region(bm, geom=[f])
    bmesh.ops.translate(bm, vec=Vector(d), verts=[e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = _obj(name, bm, at, rot, mat)
    return _finish(o, mat, min(bevel, depth * 0.25), segs, "box", rng, grain)


def soft(name, size, at=(0, 0, 0), mat=None, round=0.02, fine=2, rot=(0, 0, 0), rng=None):
    """A padded block (cushion, mattress, page block, sack, folded cloth): rounded edges and enough vertices in its
    faces to be pushed about afterwards with deform()/sag()/lumps()."""
    o = box(name, size, at, None, bevel=0, rot=rot)
    bevel(o, min(round, 0.45 * min(size)), segs=5, harden=False)
    subdivide(o, fine, simple=True)
    smooth(o, 70.0)
    if mat is not None:
        o.data.materials.append(mat)
        uv_box(o, rng=rng)
    return o


# ----------------------------------------------------------------------------------------------------------- shaping
def deform(obj, fn):
    """Move every vertex: fn receives an (N, 3) array of local positions and returns the new ones."""
    me = obj.data
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    new = np.asarray(fn(co.reshape(-1, 3)), dtype=np.float64)
    me.vertices.foreach_set("co", new.ravel())
    me.update()
    return obj


def sag(obj, amount, axis=2, along=0):
    """Let a part droop by `amount` in the middle along local axis `along` (a shelf under books, a rope, a bench)."""
    def f(co):
        lo, hi = co[:, along].min(), co[:, along].max()
        t = (co[:, along] - lo) / max(hi - lo, 1e-9)
        co[:, axis] -= amount * np.sin(np.pi * t)
        return co
    return deform(obj, f)


def lumps(obj, amp, scale=0.1, seed=0, mask=None):
    """Soft irregularity (stuffing, worn stone, hand-made pottery): a sum of a few random waves, `amp` metres
    high, `scale` metres across. `mask(co)` returns 0..1 per vertex to limit it (e.g. only the top)."""
    r = random.Random(seed)
    waves = [(np.array([r.gauss(0, 1) for _ in range(3)]), r.random() * 6.283) for _ in range(5)]
    def f(co):
        d = sum(np.sin(co @ (k / np.linalg.norm(k)) / scale * (1 + i * 0.7) + ph) / (1 + i) for i, (k, ph) in enumerate(waves))
        d = d / 2.3 * amp
        if mask is not None:
            d = d * mask(co)
        nrm = co - co.mean(0)
        nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
        return co + nrm * d[:, None]
    return deform(obj, f)


def jitter(obj, rng, move=0.002, turn=0.6):
    """Nothing made by hand sits perfectly square: shift by up to `move` metres and turn by up to `turn` degrees."""
    obj.location += Vector([rng.uniform(-move, move) for _ in range(3)])
    obj.rotation_euler.z += math.radians(rng.uniform(-turn, turn))
    obj.rotation_euler.x += math.radians(rng.uniform(-turn, turn) * 0.3)
    obj.rotation_euler.y += math.radians(rng.uniform(-turn, turn) * 0.3)
    return obj


def mirror_x(obj, name=None):
    """A copy reflected across x=0 (left and right legs, handles)."""
    o = obj.copy()
    o.data = obj.data.copy()
    o.name = name or obj.name + "_r"
    _link(o)
    o.location.x = -obj.location.x
    o.rotation_euler.y = -obj.rotation_euler.y
    o.rotation_euler.z = -obj.rotation_euler.z
    o.scale.x = -obj.scale.x
    bake_transform(o)
    return o


def bake_transform(obj):
    """Apply scale (and rotation) into the mesh; a negative scale is applied with the normals turned back out."""
    flip = obj.scale.x * obj.scale.y * obj.scale.z < 0
    m = Matrix.LocRotScale(None, obj.rotation_euler, obj.scale)
    obj.data.transform(m)
    if flip:
        obj.data.flip_normals()
    obj.rotation_euler = (0, 0, 0)
    obj.scale = (1, 1, 1)
    obj.data.update()
    return obj


def join(objs, name):
    """Merge parts into one object (fewer draw calls). Keep parts apart while building; join at the end."""
    objs = [o for o in objs if o]
    if len(objs) < 2:
        if objs:
            objs[0].name = name
        return objs[0] if objs else None
    with bpy.context.temp_override(active_object=objs[0], selected_editable_objects=objs, selected_objects=objs,
                                   object=objs[0]):
        bpy.ops.object.join()
    objs[0].name = name
    objs[0].data.name = name
    return objs[0]


def origin_bottom(obj):
    """Put the object's origin at the bottom centre of its own bounds (how engines expect a prop to stand), keeping
    it where it is. Bakes rotation and scale first."""
    bake_transform(obj)
    me = obj.data
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    lo, hi = co.min(0), co.max(0)
    piv = Vector(((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]))
    me.transform(Matrix.Translation(-piv))
    obj.location += piv
    me.update()
    return obj


def parts():
    return [o for o in bpy.context.scene.objects if o.type == "MESH" and not o.name.startswith("_")]


def bounds(objs=None):
    objs = parts() if objs is None else objs
    bpy.context.view_layer.update()
    pts = np.array([list(o.matrix_world @ Vector(c)) for o in objs for c in o.bound_box])
    return pts.min(0), pts.max(0)


def bake(wear="worn", **kw):
    """Bake the materials and wear (edges, grime, ground dirt, dust, variation) into one texture set and one
    material on a unique UV atlas. See forge_bake.py. Call after the last part, before export()."""
    import forge_bake
    return forge_bake.bake(wear, **kw)


# ------------------------------------------------------------------------------------------------------------ export
def tris(objs=None):
    n = 0
    dg = bpy.context.evaluated_depsgraph_get()
    for o in parts() if objs is None else objs:
        me = o.evaluated_get(dg).to_mesh()
        me.calc_loop_triangles()
        n += len(me.loop_triangles)
        o.evaluated_get(dg).to_mesh_clear()
    return n


def export(name=None, fmt="GLB", notes=None):
    """Write <out>/<name>.glb (or .gltf with its textures beside it) and <name>.manifest.json: size, triangles,
    parts, materials and images, which check.py compares with what an importer reads back."""
    name = name or STATE["name"]
    out = STATE["out"]
    obs = parts()
    lo, hi = bounds(obs)
    for o in bpy.context.scene.objects:
        o.select_set(o in obs)
    path = os.path.join(out, name + (".glb" if fmt == "GLB" else ".gltf"))
    kw = dict(filepath=path, export_format="GLB" if fmt == "GLB" else "GLTF_SEPARATE", use_selection=True,
              export_apply=True, export_yup=True, export_image_format="AUTO")
    if fmt != "GLB":
        kw["export_texture_dir"] = name + "_tex"
    bpy.ops.export_scene.gltf(**kw)
    mats = {}
    for o in obs:
        for m in o.data.materials:
            if m and m.name not in mats:
                ims = [n.image for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image] if m.node_tree else []
                mats[m.name] = {"metres": m.get("metres"), "images": {i.name: list(i.size) for i in ims}}
    man = {"name": name, "file": os.path.basename(path), "units": "metres, Z up, front -Y",
           "size": [round(float(v), 4) for v in (hi - lo)], "min": [round(float(v), 4) for v in lo],
           "max": [round(float(v), 4) for v in hi], "tris": tris(obs), "parts": len(obs),
           "materials": mats, "seed": STATE["seed"], "notes": notes or ""}
    with open(os.path.join(out, name + ".manifest.json"), "w") as f:
        json.dump(man, f, indent=1)
    print(MARK + json.dumps({"ok": True, "exported": path, "size": man["size"], "tris": man["tris"],
                             "parts": man["parts"], "materials": list(mats)}), flush=True)
    return path
