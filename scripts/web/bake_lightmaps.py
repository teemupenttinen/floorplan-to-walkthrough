"""
Light-map bake for the browser walkthrough (scripts/web/viewer/index.html).

Run headless on a saved model, never in the Blender session you are working in. The script changes the
scene and does not save it:

  blender -b model.blend --python-exit-code 1 --python bake_lightmaps.py
  blender -b model.blend --python-exit-code 1 --python bake_lightmaps.py -- --reuse
  blender -b model.blend --python-exit-code 1 --python bake_lightmaps.py -- --only floor1 --only floor2
  blender -b model.blend --python-exit-code 1 --python bake_lightmaps.py -- --albedo

  --reuse     keep light maps already in <out>/build when the atlas size and object count are the same
              (the unwrap is deterministic, so the same geometry gives the same UVs)
  --only G    bake and write only group G (repeatable); the other groups still cast light and shadow
  --albedo    also bake the surface colour into a second atlas. Use this when the materials are procedural
              (noise, box mapping): the glTF exporter cannot export them, the baked colour can.
  --config F  a Python file run after the CONFIG block below: a project sets GROUPS, INTERIOR_BOXES, LOOK ...
              there instead of editing this script.

What it writes (default <folder of the .blend>/web, or $WEB_OUT):
  mesh/<group>.glb       UV 0 = the material UVs, UV 1 = the light map atlas ('Bake' layer).
                         Node extras: src (source object), lm (atlas name or none), door (see DOORS).
  lm/lm_<group>.png      sRGB(light / scale): Cycles diffuse light, direct + indirect, no surface colour,
                         denoised with the baked normals as a guide. 'scale' is in scene.json.
  lm/lm_<group>.ktx2     the same as UASTC KTX2 when basisu is installed ($BASISU or on PATH)
  lm/al_<group>.png      baked surface colour (only with --albedo)
  scene.json             groups, spots, start, floors, labels (read by the viewer)
  build/                 PNG light maps and their meta files, kept for --reuse
  index.html             a copy of viewer/index.html next to the data

Tools (optional, each step is skipped with a warning when the tool is missing):
  basisu    $BASISU or PATH      KTX2 textures. Light maps: UASTC level 3 without RDO (RDO makes visible blocks
                                 in smooth light gradients).
  gltfpack  $GLTFPACK or PATH    meshopt compression: -cc -kn -km -ke -kv -noq. -kv keeps the UVs of materials
                                 without textures (else UV 1 is dropped); -noq because box-projected UVs run
                                 to hundreds of tiles and quantization breaks them.

Set the CONFIG block for your model with --config project_bake.py (preferred) or edit it here.
"""

import json
import math
import os
import shutil
import subprocess
import sys
import time

import bpy
import bmesh
import numpy as np
from mathutils import Vector

# ---------------------------------------------------------------------------
# CONFIG

# Group name -> the collections it bakes, light map texels per metre, and Cycles samples per texel.
# Rooms lit by daylight through windows need many samples (indirect light); outdoor groups need few.
GROUPS = {
    "floor1": {"collections": ["Floor 1"], "density": 64, "samples": 2048},
    "floor2": {"collections": ["Floor 2"], "density": 64, "samples": 2048},
    "site": {"collections": ["Site"], "density": 12, "samples": 256},
}

GLASS_MATERIALS = ("Glass",)            # name prefixes: window panes (light portals; no light map of their own)
LAMP_MATERIALS = ("Lamp", "Downlight")  # name prefixes: emission off during the bake when LAMPS_OFF
LAMPS_OFF = True                        # bake the daytime state: ceiling lamps off, as the viewer starts
HIDE_DURING_BAKE = ()                   # name prefixes of objects to hide (an alternative furniture set:
                                        # a hidden set that still renders shadows into the visible one)
# Boxes (xmin, ymin, zmin, xmax, ymax, zmax) in model metres that are "inside". A window pane with inside on one
# side and outside on the other gets a Cycles light portal, which takes most of the noise out of rooms lit only
# by daylight. Empty = no portals.
INTERIOR_BOXES = []

# Doors the viewer can open (E key). Read from the model: every object with a "door" property (JSON, radians,
# see docs/00-interfaces.md; build_template.py writes it). Entries here (degrees) add to or override those:
# source object name -> hinge (model metres), angles in degrees about +z (counter-clockwise seen from above): open,
# closed, and the angle the leaf has in the model ("baked"). The light map is baked in the modelled pose.
DOORS = {
    # "Door bedroom leaf": {"hinge": [2.10, 5.80, 0.0], "open": 90.0, "closed": 0.0, "baked": 0.0},
}

# Eye position (model metres) and yaw (degrees, ccw from +x). None = from the empties "Start" and "Spot <name>"
# in the model (spots in name order; list them here for another order).
START = None
SPOTS = None
EYE_HEIGHT = 1.6                                    # added to the empties (on the floor); the viewer's EYE
FLOORS = [0.0, 3.0, 6.0]                            # floor levels (model z), for the dollhouse cut
LABELS = "labels.json"                              # copied next to scene.json when it is beside the .blend
# Viewer look, written to scene.json. tone "agx" (as the bake's view transform) or "neutral" (keeps hue and
# saturation: warm wood, an orange sauna and white walls stay as in listing photos); ev = default exposure.
LOOK = {"tone": "agx", "ev": -1.0}

MAX_ATLAS = 4096
MIN_ATLAS = 1024
PACKING = 0.6           # share of the atlas the island packer is expected to fill
MARGIN_PX = 8           # texels between islands (bilinear filtering and 4x4 compression blocks)
DENSE_FACES = 150       # objects with more faces than this ...
DENSE_AREA = 0.4        # ... and less surface (m2) get no light map (potted plants: thousands of tiny islands)

# ---------------------------------------------------------------------------

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if "--config" in ARGS:
    _cfg = os.path.abspath(ARGS[ARGS.index("--config") + 1])
    exec(compile(open(_cfg).read(), _cfg, "exec"), globals())
    print("[bake] config", _cfg, flush=True)
REUSE = "--reuse" in ARGS
ALBEDO = "--albedo" in ARGS
ONLY = [ARGS[i + 1] for i, a in enumerate(ARGS) if a == "--only" and i + 1 < len(ARGS)]

BLEND_DIR = bpy.path.abspath("//") or os.getcwd()
OUT = os.environ.get("WEB_OUT") or os.path.join(BLEND_DIR, "web")
BUILD = os.path.join(OUT, "build")
MESH_DIR = os.path.join(OUT, "mesh")
LM_DIR = os.path.join(OUT, "lm")
HERE = os.path.dirname(os.path.abspath(__file__))
BASISU = os.environ.get("BASISU") or shutil.which("basisu")
GLTFPACK = os.environ.get("GLTFPACK") or shutil.which("gltfpack")


def log(*a):
    print("[bake]", *a, flush=True)


# Optional: the material description and box UVs of the Unreal export (scripts/blender/export_manifest.py), so
# that UV 0 is the same box mapping as in Cycles and Unreal. Without it, UV 0 is whatever the mesh has.
EM = {}
_em_path = os.path.join(HERE, "..", "blender", "export_manifest.py")
if os.path.exists(_em_path) and not os.environ.get("NO_BOX_UVS"):
    try:
        EM = {"__name__": "export_manifest", "NO_MAIN": True}
        exec(open(_em_path).read(), EM)
        if "box_uvs" not in EM or "describe" not in EM:
            EM = {}
        else:
            EM["_copy_tex"] = lambda path: os.path.basename(path) if path else None    # no export/tex copies here
    except Exception as e:          # the exporter may expect its own scene layout
        log("export_manifest.py not usable here (%s): UV 0 stays as modelled" % e)
        EM = {}


# ---------------------------------------------------------------------------
# Scene preparation

def setup_cycles():
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for kind in ("OPTIX", "CUDA", "METAL", "HIP", "ONEAPI"):
            try:
                prefs.compute_device_type = kind
            except TypeError:
                continue
            prefs.get_devices()
            devs = [d for d in prefs.devices if d.type == kind]
            if devs:
                for d in devs:
                    d.use = True
                sc.cycles.device = "GPU"
                log("Cycles on", kind)
                break
    except Exception as e:
        log("GPU setup failed, CPU bake:", e)
    sc.cycles.use_denoising = False


def starts(name, prefixes):
    return bool(prefixes) and name.startswith(tuple(prefixes))


NORMAL_STRENGTH = {}        # (material, node) -> strength before the bake, restored for the glTF export


def prepare_materials():
    """Flat normals (a normal map baked into the light map doubles with the one the viewer applies) and lamps off:
    lamp materials dark, and every light object except the sun hidden (room lights are for the evening)."""
    if LAMPS_OFF:
        for ob in bpy.data.objects:
            if ob.type == "LIGHT" and ob.data.type != "SUN":
                ob.hide_render = True
    for m in bpy.data.materials:
        if not m.use_nodes or m.node_tree is None:
            continue
        for n in m.node_tree.nodes:
            if n.type == "NORMAL_MAP":
                NORMAL_STRENGTH[(m.name, n.name)] = n.inputs["Strength"].default_value
                n.inputs["Strength"].default_value = 0.0
            elif n.type == "BUMP":
                n.inputs["Strength"].default_value = 0.0
            if LAMPS_OFF and starts(m.name, LAMP_MATERIALS):
                if n.type == "BSDF_PRINCIPLED":
                    n.inputs["Emission Strength"].default_value = 0.0
                elif n.type == "EMISSION":
                    n.inputs["Strength"].default_value = 0.0


def bake_collection():
    c = bpy.data.collections.get("WEB bake")
    if c is None:
        c = bpy.data.collections.new("WEB bake")
        bpy.context.scene.collection.children.link(c)
    return c


def realize():
    """World-space mesh copies of every visible mesh in each group (modifiers applied). The originals are hidden,
    so each surface renders once; objects outside the groups stay as they are and still cast light and shadow."""
    dg = bpy.context.evaluated_depsgraph_get()
    coll = bake_collection()
    made, originals = {}, []
    for ob in bpy.data.objects:
        if starts(ob.name, HIDE_DURING_BAKE):
            ob.hide_render = True
    for group, cfg in GROUPS.items():
        made[group] = []
        seen = set()
        for cname in cfg["collections"]:
            c = bpy.data.collections.get(cname)
            if c is None:
                log("WARNING: no collection %r (group %s)" % (cname, group))
                continue
            for ob in c.all_objects:
                if ob.type != "MESH" or ob.hide_render or ob.name in seen:
                    continue
                seen.add(ob.name)
                ev = ob.evaluated_get(dg)
                me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
                if not me.polygons:
                    bpy.data.meshes.remove(me)
                    continue
                me.transform(ob.matrix_world)
                if ob.matrix_world.determinant() < 0:
                    me.flip_normals()
                new = bpy.data.objects.new("WEB " + ob.name, me)
                new["src"] = ob.name
                coll.objects.link(new)
                made[group].append(new)
                originals.append(ob)
        log("group %-10s %4d objects" % (group, len(made[group])))
    for ob in originals:
        ob.hide_render = True
    bpy.context.view_layer.update()
    return made


def mesh_area(ob):
    return sum(p.area for p in ob.data.polygons)


def is_glass(ob):
    mats = [s.material for s in ob.material_slots if s.material]
    return bool(mats) and all(starts(m.name, GLASS_MATERIALS) for m in mats)


def dense_decor(ob):
    return len(ob.data.polygons) > DENSE_FACES and mesh_area(ob) < DENSE_AREA


def prep_uvs(ob):
    """UV 0 = material UVs (the render UV layer, or box UVs from the Unreal exporter), UV 1 = 'Bake'. glTF writes
    the layers in order, so every other layer is removed."""
    me = ob.data
    keep = next((l.name for l in me.uv_layers if l.active_render), None)
    for name in [l.name for l in me.uv_layers if l.name != keep]:
        me.uv_layers.remove(me.uv_layers[name])
    if EM:
        try:
            EM["box_uvs"](me, [EM["describe"](s.material) for s in ob.material_slots] or [EM["describe"](None)])
        except Exception as e:
            log("box_uvs failed on %s: %s" % (ob["src"], e))
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")


# ---------------------------------------------------------------------------
# Light map atlas

def pow2(n):
    return 1 << max(0, math.ceil(math.log2(max(1, n))))


def atlas_size(objs, density):
    area = sum(mesh_area(o) for o in objs)
    return int(min(MAX_ATLAS, max(MIN_ATLAS, pow2(math.sqrt(area * density * density / PACKING)))))


def uv_density(me, size):
    """Texels per metre: sqrt(UV area x size^2 / surface area), over the 'Bake' layer."""
    uv = np.empty(len(me.loops) * 2, dtype=np.float64)
    me.uv_layers["Bake"].data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    uv_area = 0.0
    for p in me.polygons:
        pts = uv[p.loop_start:p.loop_start + p.loop_total]
        x, y = pts[:, 0], pts[:, 1]
        uv_area += 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
    area = sum(p.area for p in me.polygons)
    return math.sqrt(uv_area * size * size / area) if area > 0 else 0.0


def select_only(ob):
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob


def unwrap_atlas(objs, size, density, name):
    """One 'Bake' UV layer over all objects of an atlas. The objects are unwrapped as one concatenated mesh
    (multi-object edit mode skipped some objects) and the UVs are copied back loop by loop."""
    for ob in objs:
        uv = ob.data.uv_layers.get("Bake") or ob.data.uv_layers.new(name="Bake")
        ob.data.uv_layers.active = uv
    bm = bmesh.new()
    counts = []
    for ob in objs:
        counts.append(len(ob.data.loops))
        bm.from_mesh(ob.data)
    tmp_me = bpy.data.meshes.new("WEB unwrap")
    bm.to_mesh(tmp_me)
    bm.free()
    if len(tmp_me.loops) != sum(counts):
        raise RuntimeError("unwrap %s: %d loops joined, %d expected" % (name, len(tmp_me.loops), sum(counts)))
    for layer in list(tmp_me.uv_layers):
        tmp_me.uv_layers.remove(layer)
    tmp_me.uv_layers.new(name="Bake")
    tmp = bpy.data.objects.new("WEB unwrap", tmp_me)
    bake_collection().objects.link(tmp)
    select_only(tmp)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), margin_method="FRACTION", island_margin=MARGIN_PX / size,
                             area_weight=0.0, correct_aspect=True, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    base = np.empty(len(tmp_me.loops) * 2, dtype=np.float32)
    tmp_me.uv_layers["Bake"].data.foreach_get("uv", base)
    bad = ~np.isfinite(base)
    if bad.any():              # degenerate faces get NaN UVs, and one NaN island makes the whole pack NaN
        log("%s: %d NaN UV values zeroed" % (name, int(bad.sum())))
        base[bad] = 0.0
    margin_px = MARGIN_PX
    # Margins are absolute: with thousands of islands the packer shrinks every island (or overflows). Grow the
    # atlas until the texel density reaches 40 % of the goal. Each try packs the smart-project UVs again, because
    # a collapsed pack cannot be scaled back up.
    while True:
        tmp_me.uv_layers["Bake"].data.foreach_set("uv", base)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.uv.select_all(action="SELECT")
        bpy.ops.uv.pack_islands(rotate=True, rotate_method="CARDINAL", scale=True, margin_method="FRACTION",
                                margin=margin_px / size, shape_method="AABB")
        bpy.ops.object.mode_set(mode="OBJECT")
        uv = np.empty(len(tmp_me.loops) * 2, dtype=np.float32)
        tmp_me.uv_layers["Bake"].data.foreach_get("uv", uv)
        if not np.isfinite(uv).all():
            raise RuntimeError("unwrap %s: NaN UVs after packing" % name)
        fits = uv.max() <= 1.0005 and uv.min() >= -0.0005
        dens = uv_density(tmp_me, size) if fits else 0.0
        if fits and dens >= 0.4 * density:
            break
        if size < MAX_ATLAS:
            size *= 2
            log("%s grows to %d px (%s)" % (name, size, "%.1f px/m of %d" % (dens, density) if fits else "islands did not fit"))
            continue
        if margin_px > 2:
            margin_px = 2
            log("%s: 2 px margins (%.1f px/m of %d)" % (name, dens, density))
            continue
        if not fits:
            uv = (uv - uv.min()) / (uv.max() - uv.min())
            log("WARNING: %s overflows at %d px, islands squeezed" % (name, size))
        else:
            log("WARNING: %s density %.1f px/m of %d at %d px" % (name, dens, density, size))
        break
    uv = uv.reshape(-1, 2)
    at = 0
    for ob, n in zip(objs, counts):
        ob.data.uv_layers["Bake"].data.foreach_set("uv", uv[at:at + n].ravel())
        at += n
    bpy.data.objects.remove(tmp)
    bpy.data.meshes.remove(tmp_me)
    return size


def inside(p):
    return any(b[0] <= p.x <= b[3] and b[1] <= p.y <= b[4] and b[2] <= p.z <= b[5] for b in INTERIOR_BOXES)


def add_portals(objs):
    """A Cycles light portal on every vertical window pane between inside and outside."""
    if not INTERIOR_BOXES:
        return 0
    seen, n = set(), 0
    for ob in objs:
        for si, slot in enumerate(ob.material_slots):
            if slot.material is None or not starts(slot.material.name, GLASS_MATERIALS):
                continue
            for p in ob.data.polygons:
                if p.material_index != si or len(p.vertices) != 4 or p.area < 0.15 or abs(p.normal.z) > 0.3:
                    continue
                c, nrm = p.center.copy(), p.normal.copy()
                key = (round(c.x / 0.05), round(c.y / 0.05), round(c.z / 0.05))
                if key in seen:
                    continue
                a, b = inside(c + 0.4 * nrm), inside(c - 0.4 * nrm)
                if a == b:
                    continue
                seen.add(key)
                inward = nrm if a else -nrm
                u = Vector((0, 0, 1)).cross(inward).normalized()
                pts = [ob.data.vertices[v].co for v in p.vertices]
                light = bpy.data.lights.new("WEB portal", "AREA")
                light.shape = "RECTANGLE"
                light.size = max(pt.dot(u) for pt in pts) - min(pt.dot(u) for pt in pts)
                light.size_y = max(pt.z for pt in pts) - min(pt.z for pt in pts)
                light.cycles.is_portal = True
                lo = bpy.data.objects.new("WEB portal", light)
                lo.location = c + 0.02 * inward
                lo.rotation_euler = (-inward).to_track_quat("Z", "Y").to_euler()     # area lights shine along -Z
                bake_collection().objects.link(lo)
                n += 1
    log("%d light portals" % n)
    return n


# ---------------------------------------------------------------------------
# Bake

def pixels(img):
    a = np.empty(img.size[0] * img.size[1] * 4, dtype=np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(img.size[1], img.size[0], 4)


def set_target(ob, img):
    """Every material of the object gets an active, unconnected Image Texture node with the target image."""
    fallback = None
    for slot in ob.material_slots:
        if slot.material is None:
            fallback = fallback or bpy.data.materials.get("WEB default") or bpy.data.materials.new("WEB default")
            fallback.use_nodes = True
            slot.material = fallback
        m = slot.material
        m.use_nodes = True
        node = m.node_tree.nodes.get("WEB target") or m.node_tree.nodes.new("ShaderNodeTexImage")
        node.name = "WEB target"
        node.image = img
        m.node_tree.nodes.active = node
        node.select = True
    if not ob.material_slots:
        m = bpy.data.materials.get("WEB default") or bpy.data.materials.new("WEB default")
        m.use_nodes = True
        ob.data.materials.append(m)
        set_target(ob, img)


def clear_targets():
    for m in bpy.data.materials:
        if m.use_nodes and m.node_tree and "WEB target" in m.node_tree.nodes:
            m.node_tree.nodes.remove(m.node_tree.nodes["WEB target"])


def denoise(light, normal):
    """OpenImageDenoise through the compositor of a scratch scene, with the baked normals as a guide (so that
    neighbouring atlas islands of other surfaces do not blur into each other). Returns (h, w, 4) floats."""
    sc = bpy.data.scenes.get("WEB denoise") or bpy.data.scenes.new("WEB denoise")
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 1
    sc.render.resolution_x, sc.render.resolution_y = light.size
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = True
    sc.render.image_settings.file_format = "OPEN_EXR"
    sc.render.image_settings.color_depth = "32"
    sc.view_settings.view_transform = "Standard"
    if sc.camera is None:
        cam = bpy.data.objects.new("WEB denoise camera", bpy.data.cameras.new("WEB denoise camera"))
        sc.collection.objects.link(cam)
        sc.camera = cam
    if hasattr(sc, "compositing_node_group"):          # Blender 5: compositor node groups
        ng = bpy.data.node_groups.get("WEB denoise") or bpy.data.node_groups.new("WEB denoise", "CompositorNodeTree")
        ng.nodes.clear()
        if not ng.interface.items_tree:
            ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        out = ng.nodes.new("NodeGroupOutput")
        sc.compositing_node_group = ng
        tree = ng
    else:                                               # Blender 4: the scene's node tree
        sc.use_nodes = True
        tree = sc.node_tree
        tree.nodes.clear()
        out = tree.nodes.new("CompositorNodeComposite")
    src = tree.nodes.new("CompositorNodeImage")
    src.image = light
    nrm = tree.nodes.new("CompositorNodeImage")
    nrm.image = normal
    dn = tree.nodes.new("CompositorNodeDenoise")
    tree.links.new(src.outputs["Image"], dn.inputs["Image"])
    tree.links.new(nrm.outputs["Image"], dn.inputs["Normal"])
    tree.links.new(dn.outputs["Image"], out.inputs[0])
    sc.render.use_compositing = True
    path = os.path.join(bpy.app.tempdir or BUILD, "web_denoise.exr")
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True, scene=sc.name)
    res = bpy.data.images.load(path, check_existing=False)
    res.colorspace_settings.name = "Linear Rec.709"
    px = pixels(res).copy()
    bpy.data.images.remove(res)
    return px


def srgb_encode(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def save_png(path, rgb):
    """(h, w, 3) floats in 0..1 as an 8-bit PNG, without colour conversion (row 0 = bottom, as Blender)."""
    h, w = rgb.shape[:2]
    img = bpy.data.images.new("WEB png", w, h, alpha=False, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    px = np.ones((h, w, 4), dtype=np.float32)
    px[..., :3] = rgb
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


def joined_copy(objs):
    """Cycles bakes selected objects one after another over the whole image, so the atlas is baked from one
    joined copy (same 'Bake' UVs) while the originals are hidden: about 6x faster with 40 objects."""
    copies = []
    for ob in objs:
        c = ob.copy()
        c.data = ob.data.copy()
        c.hide_render = False
        for name in [l.name for l in c.data.uv_layers if l.name != "Bake"]:
            c.data.uv_layers.remove(c.data.uv_layers[name])    # join() mixes other layers into 'Bake'
        bake_collection().objects.link(c)
        copies.append(c)
    with bpy.context.temp_override(active_object=copies[0], selected_editable_objects=copies):
        bpy.ops.object.join()
    j = copies[0]
    j.data.uv_layers.active = j.data.uv_layers["Bake"]
    return j


def bake_group(group, objs, size, samples):
    """Light map (and with --albedo the colour) of one atlas. Returns (light png, albedo png or None, scale)."""
    os.makedirs(BUILD, exist_ok=True)
    path = os.path.join(BUILD, "lm_%s.png" % group)
    apath = os.path.join(BUILD, "al_%s.png" % group)
    meta = path[:-4] + ".json"
    if REUSE and os.path.exists(path) and os.path.exists(meta) and (not ALBEDO or os.path.exists(apath)):
        info = json.load(open(meta))
        if info["size"] == size and info["count"] == len(objs):
            log("reuse light map %-12s %d px" % (group, size))
            return path, apath if ALBEDO else None, info["scale"]
    t0 = time.time()
    joined = joined_copy(objs)
    hidden = [(ob, ob.hide_render) for ob in objs]
    for ob in objs:
        ob.hide_render = True
    sc = bpy.context.scene
    select_only(joined)

    if size > 2048:
        samples = max(768, int(samples * (2048 / size) ** 2))      # keep the bake time per atlas about the same
    img = bpy.data.images.new("WEB light " + group, size, size, float_buffer=True)
    set_target(joined, img)
    sc.cycles.samples = samples
    bpy.ops.object.bake(type="DIFFUSE", pass_filter={"DIRECT", "INDIRECT"}, margin=MARGIN_PX,
                        margin_type="EXTEND", use_clear=True, target="IMAGE_TEXTURES")
    # The denoiser's guide: world normals (the copies are in world space), -1..1.
    nimg = bpy.data.images.new("WEB normal " + group, size, size, float_buffer=True)
    set_target(joined, nimg)
    sc.cycles.samples = 4
    bpy.ops.object.bake(type="NORMAL", normal_space="OBJECT", margin=MARGIN_PX, margin_type="EXTEND",
                        use_clear=True, target="IMAGE_TEXTURES")
    npx = pixels(nimg)
    npx[..., :3] = npx[..., :3] * 2.0 - 1.0
    nimg.pixels.foreach_set(npx.ravel())
    if ALBEDO:
        aimg = bpy.data.images.new("WEB albedo " + group, size, size, float_buffer=True)
        set_target(joined, aimg)
        sc.cycles.samples = 4
        bpy.ops.object.bake(type="DIFFUSE", pass_filter={"COLOR"}, margin=MARGIN_PX, margin_type="EXTEND",
                            use_clear=True, target="IMAGE_TEXTURES")
        save_png(apath, srgb_encode(pixels(aimg)[..., :3]))
        bpy.data.images.remove(aimg)
    clear_targets()
    me = joined.data
    bpy.data.objects.remove(joined)
    bpy.data.meshes.remove(me)
    for ob, h in hidden:
        ob.hide_render = h

    raw = pixels(img)
    if float(raw[..., :3].max()) <= 1e-6:
        # Almost always collapsed or broken UVs (see uv_density), not missing light.
        log("WARNING: %s baked black" % group)
    try:
        light = denoise(img, nimg)[..., :3]
    except Exception as e:
        log("denoise failed (%s): raw light map" % e)
        light = raw[..., :3]
    bpy.data.images.remove(img)
    bpy.data.images.remove(nimg)
    peak = light.max(axis=2)
    lit = peak[peak > 1e-5]
    scale = max(float(np.percentile(lit, 99.8) * 1.1) if len(lit) else 1.0, 1e-3)
    save_png(path, srgb_encode(np.maximum(light, 0.0) / scale))
    json.dump({"size": size, "count": len(objs), "scale": scale}, open(meta, "w"))
    log("baked %-12s %4d px %4d objects %8.1f m2 scale %.3f %6.1f s"
        % (group, size, len(objs), sum(mesh_area(o) for o in objs), scale, time.time() - t0))
    return path, apath if ALBEDO else None, scale


# ---------------------------------------------------------------------------
# Output

def basisu(src, dst, kind):
    if not BASISU:
        return None
    if kind == "lightmap":
        args = [BASISU, "-ktx2", "-uastc", "-uastc_level", "3", "-srgb"]        # no RDO: it makes blocks
    elif kind == "normal":
        args = [BASISU, "-ktx2", "-uastc", "-uastc_rdo_l", "1.0", "-normal_map", "-linear", "-mipmap"]
    else:
        args = [BASISU, "-ktx2", "-uastc", "-uastc_rdo_l", "1.0", "-srgb", "-mipmap"]
    r = subprocess.run(args + [src, "-output_file", dst], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(dst):
        log("basisu failed for %s: %s" % (os.path.basename(src), (r.stdout + r.stderr)[-300:]))
        return None
    return dst


def prepare_export():
    """Material state for the glTF export. Box UVs (UV 0) are already in texture tiles, so the Mapping node's
    1/tile scale must not also go out as KHR_texture_transform (the texture would be scaled twice); and the normal
    maps flattened for the bake get their strength back (else normalTexture.scale is 0 and the viewer never
    applies them). glTF still drops Hue/Saturation and Mix tints: grade the images on disk instead.
    Returns the changed inputs and their bake values: restore_export() puts them back, so the next group's box
    UVs (which read the Mapping scale) and bake (flat normals) see the bake state again."""
    saved = []
    for m in bpy.data.materials:
        if not m.use_nodes or m.node_tree is None:
            continue
        for n in m.node_tree.nodes:
            if n.type == "MAPPING" and EM:
                inp, value = n.inputs["Scale"], (1.0, 1.0, 1.0)
            elif n.type == "NORMAL_MAP":
                inp, value = n.inputs["Strength"], NORMAL_STRENGTH.get((m.name, n.name), 1.0)
            else:
                continue
            saved.append((inp, tuple(inp.default_value) if n.type == "MAPPING" else inp.default_value))
            inp.default_value = value
    return saved


def restore_export(saved):
    for inp, value in saved:
        inp.default_value = value


def export_glb(objs, path):
    saved = prepare_export()
    try:
        _export_glb(objs, path)
    finally:
        restore_export(saved)


def _export_glb(objs, path):
    bpy.ops.object.select_all(action="DESELECT")
    for ob in objs:
        ob.hide_viewport = False
        ob.hide_set(False)
        ob.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    raw = path[:-4] + ".raw.glb" if GLTFPACK else path
    bpy.ops.export_scene.gltf(filepath=raw, export_format="GLB", use_selection=True, export_yup=True,
                              export_extras=True, export_texcoords=True, export_normals=True)
    if GLTFPACK:
        r = subprocess.run([GLTFPACK, "-i", raw, "-o", path, "-cc", "-kn", "-km", "-ke", "-kv", "-noq"],
                           capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(path):
            log("gltfpack failed, uncompressed:", r.stderr[-300:])
            shutil.copy2(raw, path)
        os.remove(raw)
    log("wrote %s %.1f MB" % (os.path.relpath(path, OUT), os.path.getsize(path) / 1e6))


def doors_from_model():
    """The "door" property of every leaf (radians) as viewer door data (degrees), plus the DOORS entries."""
    out = {}
    for ob in bpy.data.objects:
        if "door" not in ob.keys():
            continue
        d = json.loads(ob["door"]) if isinstance(ob["door"], str) else dict(ob["door"])
        closed = d.get("closed", 0.0)
        out[ob.name] = {"hinge": list(d["hinge"]), "open": math.degrees(d["open"]), "closed": math.degrees(closed),
                        "baked": math.degrees(d.get("baked", closed))}
    out.update(DOORS)
    return out


def markers_from_model():
    """The empties stand on the floor (build_template.py, docs/00-interfaces.md); the viewer wants the eye."""
    def entry(ob, name):
        x, y, z = ob.matrix_world.translation
        return {"name": name, "loc": [round(x, 3), round(y, 3), round(z + EYE_HEIGHT, 3)],
                "yaw": round(math.degrees(ob.matrix_world.to_euler().z), 2)}
    spots = SPOTS
    if spots is None:
        spots = [entry(ob, ob.name[5:]) for ob in sorted(bpy.data.objects, key=lambda o: o.name)
                 if ob.name.startswith("Spot ")]
    start = START
    if start is None:
        ob = bpy.data.objects.get("Start")
        start = entry(ob, "Start") if ob else (spots[0] if spots else {"loc": [0.0, 0.0, 1.6], "yaw": 0.0})
    return start, spots


def main():
    for d in (OUT, BUILD, MESH_DIR, LM_DIR):
        os.makedirs(d, exist_ok=True)
    doors = doors_from_model()
    start, spots = markers_from_model()
    log("%d doors, %d spots" % (len(doors), len(spots)))
    setup_cycles()
    prepare_materials()
    made = realize()
    add_portals([o for objs in made.values() for o in objs])
    scene_path = os.path.join(OUT, "scene.json")
    old = json.load(open(scene_path)) if os.path.exists(scene_path) else {}
    groups = {g["name"]: g for g in old.get("groups", [])}

    for group, cfg in GROUPS.items():
        if ONLY and group not in ONLY:
            continue
        objs = made[group]
        if not objs:
            continue
        for ob in objs:
            prep_uvs(ob)
            ob["lm"] = ""
            if ob["src"] in doors:
                ob["door"] = doors[ob["src"]]
        baked = [o for o in objs if not is_glass(o) and not dense_decor(o)]
        entry = {"name": group, "file": "mesh/%s.glb" % group}
        if baked:
            size = unwrap_atlas(baked, atlas_size(baked, cfg["density"]), cfg["density"], group)
            for ob in baked:
                ob["lm"] = group
            light, albedo, scale = bake_group(group, baked, size, cfg.get("samples", 1024))
            entry["scale"] = scale
            for src, key, kind in ((light, "lightmap", "lightmap"), (albedo, "albedo", "color")):
                if not src:
                    continue
                png = os.path.join(LM_DIR, os.path.basename(src))
                shutil.copy2(src, png)
                ktx = basisu(png, png[:-4] + ".ktx2", kind)
                entry[key] = os.path.relpath(ktx or png, OUT)
        export_glb(objs, os.path.join(MESH_DIR, group + ".glb"))
        groups[group] = entry

    labels = os.path.join(BLEND_DIR, LABELS)
    if os.path.exists(labels):
        shutil.copy2(labels, os.path.join(OUT, "labels.json"))
    viewer = os.path.join(HERE, "viewer", "index.html")
    if os.path.exists(viewer):
        shutil.copy2(viewer, os.path.join(OUT, "index.html"))
    data = {"units": "model metres, z up (the viewer converts to y up)",
            "groups": [groups[g] for g in GROUPS if g in groups],
            "start": start, "spots": spots, "floors": FLOORS, "look": LOOK,
            "labels": "labels.json" if os.path.exists(os.path.join(OUT, "labels.json")) else None}
    json.dump(data, open(scene_path, "w"), indent=1)
    log("done:", scene_path)


main()
