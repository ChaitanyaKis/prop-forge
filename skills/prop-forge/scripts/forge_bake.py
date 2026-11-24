"""forge_bake: give a finished prop a texture of its own, with wear that follows its shape. Called as F.bake().

Tiling photo materials can't hold anything that belongs to one spot of one object: grime in this corner, the rubbed
edge of that lid, dirt splashed up the bottom. Baking can. It
  1. joins the parts (into one object, or one per group) and unwraps them into a single atlas without overlaps,
  2. bakes what the photo materials show (colour, roughness, metal, normal) into that atlas,
  3. bakes masks from the geometry itself: ambient occlusion (crevices), convex edges, which way faces point,
     height above the floor, and two scales of noise,
  4. mixes wear from the masks into the colour and roughness (edges lighter and smoother, crevices darker, dirt low
     down, dust on top, tone variation),
  5. gives the prop one material reading the baked images (albedo, ORM with occlusion in R, normal): one draw call.

Use it for props seen up close or alone, where wear tells the story. Skip it for families drawn in great numbers
(books on shelves, planks): tiling materials shared by many props cost less memory.
"""
import math
import os

import bpy
import numpy as np

import forge as F

PRESETS = {  # how much of each kind of wear, 0..1
    "none": dict(edges=0.0, grime=0.0, ground=0.0, dust=0.0, variation=0.0),
    "light": dict(edges=0.3, grime=0.3, ground=0.15, dust=0.1, variation=0.06),
    "worn": dict(edges=0.55, grime=0.55, ground=0.3, dust=0.2, variation=0.1),
    "old": dict(edges=0.8, grime=0.8, ground=0.5, dust=0.35, variation=0.14),
}


def _setup_cycles():
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
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
                break
    except KeyError:
        pass
    if sc.world is None:
        sc.world = bpy.data.worlds.new("_bake_world")
    return sc


def _ctx(objs):
    return dict(active_object=objs[0], object=objs[0], selected_objects=objs, selected_editable_objects=objs)


def _select(objs):
    for o in bpy.context.view_layer.objects:
        o.select_set(o in objs)
    bpy.context.view_layer.objects.active = objs[0]


def _unwrap(objs, margin):
    """A second UV map, 'bake', unique across all the objects; the first stays for the photo materials to read."""
    for o in objs:
        me = o.data
        if not me.uv_layers:
            me.uv_layers.new(name="tiling")
        tiling = me.uv_layers[0]
        tiling.name = "tiling"
        b = me.uv_layers.new(name="bake")
        me.uv_layers.active = b            # baking writes through the active map...
        tiling.active_render = True        # ...while textures read the render map
    _select(objs)
    with bpy.context.temp_override(**_ctx(objs)):
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=margin, area_weight=0.0,
                                 correct_aspect=True, scale_to_bounds=False)
        try:
            bpy.ops.uv.pack_islands(margin=margin, rotate=True, shape_method="AABB")
        except TypeError:
            bpy.ops.uv.pack_islands(margin=margin, rotate=True)
        bpy.ops.object.mode_set(mode="OBJECT")


def _area(objs):
    a = 0.0
    for o in objs:
        m = np.array(o.matrix_world)
        me = o.data
        me.calc_loop_triangles()
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3) @ m[:3, :3].T
        t = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
        me.loop_triangles.foreach_get("vertices", t)
        t = t.reshape(-1, 3)
        a += float(np.linalg.norm(np.cross(co[t[:, 1]] - co[t[:, 0]], co[t[:, 2]] - co[t[:, 0]]), axis=1).sum() / 2)
    return a


def _new_image(name, size, data):
    im = bpy.data.images.new(name, size, size, alpha=False, float_buffer=False)
    im.colorspace_settings.name = "Non-Color" if data else "sRGB"
    return im


def _target(mats, image):
    """Put an image node holding `image` in each material and make it the active node (Cycles bakes into it)."""
    added = []
    for m in mats:
        nt = m.node_tree
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = image
        n.location = (-900, -600)
        for k in nt.nodes:
            k.select = False
        n.select = True
        nt.nodes.active = n
        added.append((m, n))
    return added


def _untarget(added):
    for m, n in added:
        m.node_tree.nodes.remove(n)


def _output(nt):
    outs = [n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"]
    return next((n for n in outs if n.is_active_output), outs[0] if outs else None)


def _emit(m, socket):
    """Route what feeds the Principled BSDF's `socket` into an Emission shader on the output; returns an undo."""
    nt = m.node_tree
    out = _output(nt)
    prev = out.inputs["Surface"].links[0].from_socket if out.inputs["Surface"].is_linked else None
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = 1.0
    b = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if b is None:
        c = m.diffuse_color if socket == "Base Color" else (0.0, 0.0, 0.0, 1.0)
        em.inputs["Color"].default_value = tuple(c)
    else:
        s = b.inputs[socket]
        if s.is_linked:
            nt.links.new(s.links[0].from_socket, em.inputs["Color"])
        else:
            v = s.default_value
            em.inputs["Color"].default_value = (v, v, v, 1.0) if isinstance(v, float) else tuple(v)
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return (nt, out, prev, em)


def _unemit(undo):
    nt, out, prev, em = undo
    nt.nodes.remove(em)
    if prev is not None:
        nt.links.new(prev, out.inputs["Surface"])


def _bake(objs, kind, samples, margin_px, **kw):
    sc = bpy.context.scene
    sc.cycles.samples = samples
    sc.render.bake.margin = margin_px
    sc.render.bake.use_clear = True
    _select(objs)
    with bpy.context.temp_override(**_ctx(objs)):
        bpy.ops.object.bake(type=kind, margin=margin_px, use_clear=True, target="IMAGE_TEXTURES", **kw)


def _mask_material(height, edge_width, big, small):
    """Emission of geometry facts: R convex-or-concave edge strength, G up-facing (0 down .. 1 up), B height (0 at the
    floor, 1 at `height`); a second output pair of noises is made by _noise_material."""
    m = bpy.data.materials.new("_masks")
    if m.node_tree is None:
        m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    bev = nt.nodes.new("ShaderNodeBevel")
    bev.inputs["Radius"].default_value = edge_width
    bev.samples = 16
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    nt.links.new(bev.outputs["Normal"], dot.inputs[0])
    nt.links.new(geo.outputs["Normal"], dot.inputs[1])
    edge = nt.nodes.new("ShaderNodeMath")
    edge.operation = "MULTIPLY_ADD"              # (dot * -6) + 6 = 6 (1 - dot)
    edge.use_clamp = True
    nt.links.new(dot.outputs["Value"], edge.inputs[0])
    edge.inputs[1].default_value = -6.0
    edge.inputs[2].default_value = 6.0
    sn = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Normal"], sn.inputs[0])
    up = nt.nodes.new("ShaderNodeMath")
    up.operation = "MULTIPLY_ADD"
    nt.links.new(sn.outputs["Z"], up.inputs[0])
    up.inputs[1].default_value = 0.5
    up.inputs[2].default_value = 0.5
    sp = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Position"], sp.inputs[0])
    h = nt.nodes.new("ShaderNodeMath")
    h.operation = "DIVIDE"
    h.use_clamp = True
    nt.links.new(sp.outputs["Z"], h.inputs[0])
    h.inputs[1].default_value = max(height, 1e-3)
    comb = nt.nodes.new("ShaderNodeCombineColor")
    nt.links.new(edge.outputs[0], comb.inputs[0])
    nt.links.new(up.outputs[0], comb.inputs[1])
    nt.links.new(h.outputs[0], comb.inputs[2])
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(comb.outputs[0], em.inputs["Color"])
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    # the noise material: R large patches, G fine speckle, world-space so parts share one field
    n2 = bpy.data.materials.new("_noise")
    if n2.node_tree is None:
        n2.use_nodes = True
    t = n2.node_tree
    for n in list(t.nodes):
        t.nodes.remove(n)
    o2 = t.nodes.new("ShaderNodeOutputMaterial")
    g2 = t.nodes.new("ShaderNodeNewGeometry")
    c2 = t.nodes.new("ShaderNodeCombineColor")
    for i, scale in enumerate((1.0 / big, 1.0 / small)):
        nz = t.nodes.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = scale
        nz.inputs["Detail"].default_value = 4.0
        t.links.new(g2.outputs["Position"], nz.inputs["Vector"])
        t.links.new(nz.outputs["Fac"], c2.inputs[i])
    e2 = t.nodes.new("ShaderNodeEmission")
    t.links.new(c2.outputs[0], e2.inputs["Color"])
    t.links.new(e2.outputs[0], o2.inputs["Surface"])
    return m, n2


def _px(im):
    w, h = im.size
    a = np.empty(w * h * 4, dtype=np.float32)
    im.pixels.foreach_get(a)
    return a.reshape(h, w, 4)


def _save(im, px, path, fmt):
    im.pixels.foreach_set(np.clip(px, 0, 1).astype(np.float32).ravel())
    im.filepath_raw = path
    im.file_format = fmt
    try:
        im.save(quality=92)
    except TypeError:
        im.save()


def _smooth(x, t0, t1):
    t = np.clip((x - t0) / max(t1 - t0, 1e-6), 0, 1)
    return t * t * (3 - 2 * t)


def _gltf_occlusion_group():
    g = bpy.data.node_groups.get("glTF Material Output")
    if g is None:
        g = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
        g.interface.new_socket("Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
        g.nodes.new("NodeGroupInput")
    return g


def bake(wear="worn", groups=None, density=768, size=None, edge_width=0.006, ao_distance=None,
         ground_height=None, dust_colour=(0.56, 0.53, 0.48), edge_light=0.35, samples_ao=64, margin_px=8,
         debug=False, **overrides):
    """Bake the prop's materials and its wear into one texture set and one material. Call after building every part,
    before F.export(). `wear` is a preset (none, light, worn, old) or a dict; keyword overrides adjust one kind,
    e.g. bake("worn", dust=0.4). `groups` {name: [objects]} keeps separate objects (a candle you can hide) that
    still share the atlas; default joins everything into one object named after the asset. `density` is the texel
    density aimed for (px per metre); the image size follows from the surface area (or pass `size`).
    Returns {"objects", "size", "density", "images"}."""
    w = dict(PRESETS[wear]) if isinstance(wear, str) else dict(wear)
    w.update(overrides)
    name = F.STATE["name"]
    parts = F.parts()
    if groups is None:
        groups = {name: parts}
    objs = []
    for gname, members in groups.items():
        members = [o for o in members if o is not None]
        o = F.join(members, gname) if len(members) > 1 else members[0]
        o.name = gname
        objs.append(o)
    lo, hi = F.bounds(objs)
    dims = hi - lo
    H = float(max(dims[2], 0.05))
    area = _area(objs)
    if size is None:
        size = F._pot(int(math.sqrt(area / 0.6) * density))   # nearest power of two
        size = int(min(4096, max(512, size)))
    margin = margin_px / size
    sc = _setup_cycles()
    _unwrap(objs, margin)
    mats = []
    for o in objs:
        for m in o.data.materials:
            if m and m not in mats:
                mats.append(m)
    tex = F.STATE["tex"]
    imgs = {k: _new_image("%s_%s_bake" % (name, k), size, k != "albedo") for k in
            ("albedo", "rough", "metal", "normal", "ao", "masks", "noise")}
    # what the materials show
    for kind, sock in (("albedo", "Base Color"), ("rough", "Roughness"), ("metal", "Metallic")):
        undo = [_emit(m, sock) for m in mats]
        added = _target(mats, imgs[kind])
        _bake(objs, "EMIT", 4, margin_px)
        _untarget(added)
        for u in undo:
            _unemit(u)
    added = _target(mats, imgs["normal"])
    _bake(objs, "NORMAL", 8, margin_px, normal_space="TANGENT")
    _untarget(added)
    # geometry: occlusion, edges, facing, height, noise
    sc.world.light_settings.distance = ao_distance or float(min(0.5, max(0.03, 0.2 * max(dims))))
    added = _target(mats, imgs["ao"])
    _bake(objs, "AO", samples_ao, margin_px)
    _untarget(added)
    mask_m, noise_m = _mask_material(H, edge_width, big=max(0.08, 0.3 * max(dims)), small=0.02)
    slots = [[s.material for s in o.material_slots] for o in objs]
    for mm, key in ((mask_m, "masks"), (noise_m, "noise")):
        for o in objs:
            for s in o.material_slots:
                s.material = mm
        added = _target([mm], imgs[key])
        _bake(objs, "EMIT", 16, margin_px)
        _untarget(added)
    for o, sl in zip(objs, slots):
        for s, m in zip(o.material_slots, sl):
            s.material = m
    if debug:   # the masks, for checking: <name>_debug_ao/masks/noise.png in the texture folder
        for k in ("ao", "masks", "noise"):
            imgs[k].filepath_raw = os.path.join(tex, "%s_debug_%s.png" % (name, k))
            imgs[k].file_format = "PNG"
            imgs[k].save()
    # mix the wear
    alb = _px(imgs["albedo"])[..., :3]
    rough = _px(imgs["rough"])[..., 0]
    metal = _px(imgs["metal"])[..., 0]
    ao = _px(imgs["ao"])[..., 0]
    mk = _px(imgs["masks"])
    nz = _px(imgs["noise"])
    edge, up, height = mk[..., 0], mk[..., 1], mk[..., 2]
    big, fine = nz[..., 0], nz[..., 1]
    # variation: broad patches of lighter and darker
    alb = alb * (1.0 + w["variation"] * 2.5 * (big - 0.5))[..., None]
    # crevice grime: darker, rougher where occlusion is strong
    g = np.clip(np.power(1.0 - ao, 0.8) * 2.2 * w["grime"] * (0.7 + 0.6 * fine), 0, 1)
    alb = alb * (1.0 - 0.6 * g)[..., None]
    rough = rough + (1.0 - rough) * 0.3 * g
    # dirt splashed up from the floor
    gh = ground_height or min(0.3 * H, 0.25)
    gd = np.clip((1.0 - _smooth(height * H, 0.0, gh)) * 1.4 * w["ground"] * (0.6 + 0.8 * big), 0, 1)
    earth = np.array([0.30, 0.26, 0.21], dtype=np.float32)
    alb = alb * (1.0 - 0.55 * gd)[..., None] + earth * (0.3 * gd)[..., None]
    rough = rough + (1.0 - rough) * 0.25 * gd
    # worn convex edges: lighter, less saturated, smoother (rubbed); crevices are not edges
    e = np.clip(edge * _smooth(ao, 0.5, 0.85) * 2.6 * w["edges"] * (0.5 + fine), 0, 1)
    grey = alb.mean(-1, keepdims=True)
    worn = (alb * 0.7 + grey * 0.3) * (1.0 + edge_light) + 0.02
    alb = alb + (worn - alb) * e[..., None]
    rough = rough * (1.0 - 0.3 * e)
    # dust on what faces up
    d = np.clip(_smooth(up, 0.8, 0.97) * w["dust"] * (0.5 + 0.8 * fine) * (0.6 + 0.8 * big), 0, 1)
    alb = alb + (np.array(dust_colour, dtype=np.float32) - alb) * (0.6 * d)[..., None]
    rough = rough + (0.92 - rough) * d
    # save the set: albedo (sRGB), ORM (R occlusion, G roughness, B metal), normal
    out_alb = _new_image(name + "_albedo", size, False)
    a4 = np.ones((size, size, 4), dtype=np.float32)
    a4[..., :3] = alb
    p_alb = os.path.join(tex, name + "_albedo.jpg")
    _save(out_alb, a4, p_alb, "JPEG")
    out_orm = _new_image(name + "_orm", size, True)
    o4 = np.ones((size, size, 4), dtype=np.float32)
    o4[..., 0] = 0.35 + 0.65 * ao
    o4[..., 1] = rough
    o4[..., 2] = metal
    p_orm = os.path.join(tex, name + "_orm.png")
    _save(out_orm, o4, p_orm, "PNG")
    p_nor = os.path.join(tex, name + "_normal.png")
    imgs["normal"].filepath_raw = p_nor
    imgs["normal"].file_format = "PNG"
    imgs["normal"].save()
    # the one material
    m = bpy.data.materials.new(name)
    if m.node_tree is None:
        m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    ia = bpy.data.images.load(p_alb, check_existing=False)
    ia.name = name + "_albedo"
    io = bpy.data.images.load(p_orm, check_existing=False)
    io.name = name + "_orm"
    io.colorspace_settings.name = "Non-Color"
    inn = bpy.data.images.load(p_nor, check_existing=False)
    inn.name = name + "_normal"
    inn.colorspace_settings.name = "Non-Color"
    ta = nt.nodes.new("ShaderNodeTexImage")
    ta.image = ia
    nt.links.new(ta.outputs["Color"], b.inputs["Base Color"])
    to = nt.nodes.new("ShaderNodeTexImage")
    to.image = io
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(to.outputs["Color"], sep.inputs["Color"])
    nt.links.new(sep.outputs["Green"], b.inputs["Roughness"])
    nt.links.new(sep.outputs["Blue"], b.inputs["Metallic"])
    grp = nt.nodes.new("ShaderNodeGroup")
    grp.node_tree = _gltf_occlusion_group()
    nt.links.new(sep.outputs["Red"], grp.inputs["Occlusion"])
    tn = nt.nodes.new("ShaderNodeTexImage")
    tn.image = inn
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    m["metres"] = 1.0
    for o in objs:
        me = o.data
        me.materials.clear()
        me.materials.append(m)
        me.uv_layers.remove(me.uv_layers["tiling"])
        uv = me.uv_layers["bake"]
        uv.name = "UVMap"
        me.uv_layers.active = uv
        uv.active_render = True
    for k, im in imgs.items():
        if k != "normal":
            bpy.data.images.remove(im)
    for mm in mats + [mask_m, noise_m]:
        if mm.users == 0:
            bpy.data.materials.remove(mm)
    dens = round(size * math.sqrt(0.6 / max(area, 1e-6)), 1)
    return {"objects": [o.name for o in objs], "size": size, "density_est": dens, "area_m2": round(area, 4),
            "images": [p_alb, p_orm, p_nor], "wear": w}
