"""
Export a Blender model for Unreal: one FBX per object plus manifest.json (format: docs/00-interfaces.md),
read by scripts/unreal/Python/import_manifest.py.

Run headless on a saved .blend (it changes the scene and does not save it):
  blender -b model.blend --python-exit-code 1 --python export_manifest.py -- [--out] <out dir>
Default out dir: <blend dir>/export.

Nothing is baked: Unreal lights the scene itself (Lumen). Instead each material is described in the manifest
(describe()), and the faces get UVs that reproduce Cycles' world box mapping (box_uvs()), so tiling scans look
the same in Cycles, Unreal and the browser.

Conventions it relies on (set by build_template.py, easy to follow in your own build):
- GROUPS below: which collections are exported, and whether their boxes get a small bevel.
- Door leaves: objects with a custom property "door" = JSON {"hinge": [x, y, z], "open": rad, "closed": rad},
  modelled closed in world space. The mesh origin moves to the hinge.
- Area lights: room lights (kind rect). Point/spot lights: kept as they are.
- Collection instances (trees, chairs, grass clumps): one prototype mesh each, plus instance transforms.
- Empties "Start" and "Spot <name>": player start and teleport points.
"""

import json
import math
import os
import re
import shutil
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
BLEND_DIR = os.path.dirname(bpy.data.filepath) or os.getcwd()
if "--out" in ARGS:
    OUT_DIR = os.path.abspath(ARGS[ARGS.index("--out") + 1])
elif ARGS and not ARGS[0].startswith("--"):
    OUT_DIR = os.path.abspath(ARGS[0])
else:
    OUT_DIR = os.path.join(BLEND_DIR, "export")
MESH_DIR = os.path.join(OUT_DIR, "meshes")
TEX_OUT = os.path.join(OUT_DIR, "tex")

# Collection name -> (export group, bevel). Objects in no listed collection are skipped.
GROUPS = {
    "Shell": ("shell", True),
    "Windows": ("windows", False),
    "Doors": ("doors", True),
    "Furniture": ("furniture", True),
    "Site": ("site", False),
}
BEVEL_WIDTH = 0.003        # 3 mm rounded edges catch the light like real joinery; 0 turns the bevel off
THIN_BEVEL = 0.001
NO_BEVEL = ("Plant", "Lamp", "Tap")        # name prefixes that must not be bevelled (organic or tiny parts)
SMOOTH_MATERIALS = set()                    # material names that should shade smooth (round lamps, ceramics)


def log(*a):
    print("[export]", *a, flush=True)


def safe(name):
    return re.sub(r"[^A-Za-z0-9_]", "_", name).strip("_")


# ---------------------------------------------------------------------------
# Materials

def _upstream(sock, types):
    """First node of one of `types` that feeds a socket, through any nodes in between."""
    seen, todo = set(), [sock]
    while todo:
        s = todo.pop()
        for link in s.links:
            n = link.from_node
            if n.name in seen:
                continue
            seen.add(n.name)
            if n.type in types:
                return n
            todo.extend(i for i in n.inputs if i.is_linked)
    return None


def _image_path(node):
    if node is None or node.image is None:
        return None
    path = bpy.path.abspath(node.image.filepath, library=node.image.library)
    return os.path.normpath(path) if os.path.exists(path) else None


def _copy_tex(path):
    """Copy a texture into the export once; returns its file name. Overridable (the web bake records maps here)."""
    if path is None:
        return None
    os.makedirs(TEX_OUT, exist_ok=True)
    name = os.path.basename(path)
    dst = os.path.join(TEX_OUT, name)
    if not os.path.exists(dst):
        shutil.copy2(path, dst)
    return name


def describe(mat):
    """The manifest entry of one Blender material (see docs/00-interfaces.md)."""
    if mat is None or not mat.use_nodes or mat.node_tree is None:
        col = list(mat.diffuse_color[:3]) if mat else [0.7, 0.7, 0.7]
        return {"kind": "flat", "color": col, "rough": 0.5, "metal": 0.0}
    nodes = mat.node_tree.nodes
    types = {n.type for n in nodes}
    bsdf = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
    if "BSDF_GLOSSY" in types and "BSDF_TRANSPARENT" in types:
        tint = next(n for n in nodes if n.type == "BSDF_TRANSPARENT").inputs["Color"].default_value[:3]
        return {"kind": "glass", "tint": list(tint)}
    if bsdf is None:
        return {"kind": "flat", "color": list(mat.diffuse_color[:3]), "rough": 0.5, "metal": 0.0}

    rough_in, metal_in = bsdf.inputs["Roughness"], bsdf.inputs["Metallic"]
    d = {"rough": rough_in.default_value, "metal": 0.0 if metal_in.is_linked else metal_in.default_value}
    emit = bsdf.inputs["Emission Strength"].default_value
    if emit > 0:
        d["emit"] = [c * emit for c in bsdf.inputs["Emission Color"].default_value[:3]]

    img = _upstream(bsdf.inputs["Base Color"], {"TEX_IMAGE"})
    if _image_path(img) is None:
        base = bsdf.inputs["Base Color"]
        d.update(kind="flat", color=list(mat.diffuse_color[:3]) if base.is_linked else list(base.default_value[:3]))
        return d

    # Alpha-masked leaves and grass cards: kind leaf_tex (two-sided foliage in Unreal).
    if bsdf.inputs["Alpha"].is_linked:
        mask = _upstream(bsdf.inputs["Alpha"], {"TEX_IMAGE"})
        if mask is not None and mat.name.lower().startswith(("leaf", "grass", "foliage")):
            return {"kind": "leaf_tex", "color_tex": _copy_tex(_image_path(img)),
                    "mask_tex": _copy_tex(_image_path(mask)), "tint": [1.0, 1.0, 1.0]}
        d["masked"] = True

    # World box mapping (materials.mat_tex) or the mesh's own UVs (downloaded models).
    geo = _upstream(img.inputs["Vector"], {"NEW_GEOMETRY", "TEX_COORD"}) if img.inputs["Vector"].is_linked else None
    if geo is not None and geo.type == "TEX_COORD":
        geo = None if img.projection != "BOX" else geo
    d["kind"] = "tex" if geo is not None else "uv"
    d["color_tex"] = _copy_tex(_image_path(img))
    if d["kind"] == "tex":
        mapping = next((n for n in nodes if n.type == "MAPPING"), None)
        d["size"] = [1.0 / s for s in mapping.inputs["Scale"].default_value] if mapping else [1.0, 1.0, 1.0]
    hs = next((n for n in nodes if n.type == "HUE_SAT"), None)
    if hs is not None:
        d["saturation"] = hs.inputs["Saturation"].default_value
        d["value"] = hs.inputs["Value"].default_value
    mix = next((n for n in nodes if n.type == "MIX" and n.data_type == "RGBA"), None)
    if mix is not None:
        b = [i for i in mix.inputs if i.type == "RGBA"][1]
        if not b.is_linked:
            d["tint"] = list(b.default_value[:3])
            d["tint_mix"] = mix.inputs["Factor"].default_value
    if rough_in.is_linked:
        r = _upstream(rough_in, {"TEX_IMAGE"})
        if _image_path(r):
            d["rough_tex"] = _copy_tex(_image_path(r))
    nm = _upstream(bsdf.inputs["Normal"], {"NORMAL_MAP"})
    if nm is not None:
        n = _upstream(nm.inputs["Color"], {"TEX_IMAGE"})
        if _image_path(n):
            d["normal_tex"] = _copy_tex(_image_path(n))
            d["normal"] = nm.inputs["Strength"].default_value
    return d


# ---------------------------------------------------------------------------
# UVs: box projection in world space, like the Image Texture node's BOX mode in Cycles

def box_uvs(me, mats):
    """Write UVs into UV layer 0: texture tiles for 'tex' materials, metres for faces of other materials
    that have no UVs. Faces of 'uv' and 'leaf_tex' materials keep the UVs the mesh has.
    The mesh must be in world space (realize() makes it so)."""
    had_uv = len(me.uv_layers) > 0
    uv = me.uv_layers[0] if had_uv else me.uv_layers.new(name="UVMap")
    me.uv_layers.active_index = 0
    n_loops = len(me.loops)
    if n_loops == 0:
        return
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    lv = np.empty(n_loops, dtype=np.int64)
    me.loops.foreach_get("vertex_index", lv)
    p = co[lv]
    fn = np.empty(len(me.polygons) * 3)
    me.polygons.foreach_get("normal", fn)
    fn = fn.reshape(-1, 3)
    fmat = np.empty(len(me.polygons), dtype=np.int64)
    me.polygons.foreach_get("material_index", fmat)
    lt = np.empty(len(me.polygons), dtype=np.int64)
    me.polygons.foreach_get("loop_total", lt)
    face_of_loop = np.repeat(np.arange(len(me.polygons)), lt)
    n = fn[face_of_loop]
    m = fmat[face_of_loop]
    out = np.empty(n_loops * 2)
    uv.data.foreach_get("uv", out)
    out = out.reshape(-1, 2)
    for i, d in enumerate(mats):
        sel = m == i
        if not sel.any() or (d["kind"] in ("uv", "leaf_tex") and had_uv):
            continue
        q = p[sel] / np.array(d.get("size", [1.0, 1.0, 1.0]))
        nn = n[sel]
        axis = np.argmax(np.abs(nn), axis=1)
        res = np.empty((len(q), 2))
        x, y, z = axis == 0, axis == 1, axis == 2
        res[x, 0] = np.where(nn[x, 0] < 0, 1 - q[x, 1], q[x, 1])
        res[x, 1] = q[x, 2]
        res[y, 0] = np.where(nn[y, 1] > 0, 1 - q[y, 0], q[y, 0])
        res[y, 1] = q[y, 2]
        res[z, 0] = np.where(nn[z, 2] > 0, 1 - q[z, 1], q[z, 1])
        res[z, 1] = q[z, 0]
        out[sel] = res
    uv.data.foreach_set("uv", out.ravel())


# ---------------------------------------------------------------------------
# Geometry

def world_mesh(ob, dg, matrix=None):
    """The evaluated mesh (modifiers applied) of an object, in world space (or `matrix`)."""
    ev = ob.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
    me.transform(matrix if matrix is not None else ob.matrix_world)
    if (matrix if matrix is not None else ob.matrix_world).determinant() < 0:
        me.flip_normals()
    return me


def realize():
    """World-space copies of every visible mesh of the GROUPS, in a scratch collection. Returns
    {group: [objects]}; each copy has ob['src'] = source name, ob['bevel'] = bool."""
    dg = bpy.context.evaluated_depsgraph_get()
    scratch = bpy.data.collections.new("EXPORT")
    bpy.context.scene.collection.children.link(scratch)
    made = {}
    for cname, (group, bevel) in GROUPS.items():
        c = bpy.data.collections.get(cname)
        if c is None:
            continue
        for ob in c.all_objects:
            if ob.type != "MESH" or ob.hide_render or ob.hide_get():
                continue
            me = world_mesh(ob, dg)
            if not me.polygons:
                continue
            new = bpy.data.objects.new("EXPORT " + ob.name, me)
            new["src"] = ob.name
            new["bevel"] = bevel and BEVEL_WIDTH > 0 and not ob.name.startswith(NO_BEVEL)
            if "door" in ob:
                new["door"] = ob["door"]
            scratch.objects.link(new)
            made.setdefault(group, []).append(new)
    return made


def add_bevel(ob, width):
    """Round sharp edges by `width`, like Cycles' Bevel shader. Every crease is marked sharp first, and harden
    normals keeps flat faces flat: only the narrow bevel strips shade round, so edges catch the light."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    for e in bm.edges:
        e.smooth = not (len(e.link_faces) != 2 or e.calc_face_angle(0.0) > math.radians(1))
    for f in bm.faces:
        f.smooth = True
    bm.to_mesh(ob.data)
    bm.free()
    mod = ob.modifiers.new("Bevel", "BEVEL")
    mod.width = width
    mod.segments = 2
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(30)
    mod.use_clamp_overlap = True
    mod.harden_normals = True
    mod.miter_outer = "MITER_ARC"


def safe_bevel(ob):
    """The bevel modifier sometimes throws a few vertices 1e20 m away (random, same mesh, other runs fine).
    Unreal then gets NaN bounds and slivers with collision across the room. If any evaluated vertex leaves the
    unbevelled bounds by more than 5 cm, try THIN_BEVEL, then no bevel."""
    def far():
        lo = [min(v.co[i] for v in ob.data.vertices) - 0.05 for i in range(3)]
        hi = [max(v.co[i] for v in ob.data.vertices) + 0.05 for i in range(3)]
        ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
        return any(not (lo[i] <= v.co[i] <= hi[i]) for v in ev.vertices for i in range(3))
    mod = ob.modifiers.get("Bevel")
    if mod is None or not far():
        return
    if mod.width > THIN_BEVEL:
        mod.width = THIN_BEVEL
        if not far():
            log("bevel of %s threw vertices away: %.0f mm instead" % (ob["src"], THIN_BEVEL * 1000))
            return
    ob.modifiers.remove(mod)
    log("bevel of %s threw vertices away: no bevel" % ob["src"])


def export_fbx(ob, path):
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    # FBX_SCALE_NONE + -Z forward / Y up: Unreal reads metres as centimetres x 100 itself (1 unit = 1 m).
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={"MESH"},
                             apply_scale_options="FBX_SCALE_NONE", axis_forward="-Z", axis_up="Y",
                             mesh_smooth_type="FACE", use_mesh_modifiers=True, use_tspace=False,
                             path_mode="STRIP", embed_textures=False, bake_anim=False)


def mesh_entry(ob, materials, file):
    names = []
    for slot in ob.data.materials:
        key = slot.name if slot else "None"
        if key not in materials:
            materials[key] = describe(slot)
        names.append(key)
    box_uvs(ob.data, [materials[k] for k in names])
    smooth = {i for i, k in enumerate(names) if k in SMOOTH_MATERIALS}
    for p in ob.data.polygons:
        if p.material_index in smooth:
            p.use_smooth = True
    if ob.get("bevel") and not any(materials[k]["kind"] in ("uv", "leaf_tex", "glass") for k in names):
        add_bevel(ob, BEVEL_WIDTH)
        safe_bevel(ob)
    export_fbx(ob, os.path.join(MESH_DIR, file + ".fbx"))
    ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
    return {"file": file, "materials": names, "tris": sum(len(p.vertices) - 2 for p in ev.polygons)}


def ue_yaw(rad):
    """A turn about z in Blender (counter-clockwise, radians) as an Unreal yaw in degrees."""
    return -math.degrees(rad)


# ---------------------------------------------------------------------------
# Lights, instances, markers, sun

def export_lights():
    out = []
    for ob in bpy.data.objects:
        if ob.type != "LIGHT" or ob.hide_render or ob.data.type == "SUN":
            continue
        L, loc = ob.data, list(ob.matrix_world.translation)
        name = ob.get("room", ob.name)
        if L.type == "AREA":
            sy = L.size_y if L.shape in ("RECTANGLE", "ELLIPSE") else L.size
            # Room light: about 100 lm per m2 of room (the light is 0.6 x the room in each direction).
            lumens = ob.get("lumens", 100.0 * (L.size * sy) / 0.36)
            out.append({"kind": "rect", "name": name, "loc": loc, "size": [L.size, sy], "lumens": lumens})
        elif L.type == "SPOT":
            out.append({"kind": "spot", "name": name, "loc": loc, "lumens": ob.get("lumens", 450.0)})
        else:
            out.append({"kind": "point", "name": name, "loc": loc, "radius": L.shadow_soft_size,
                        "lumens": ob.get("lumens", 250.0)})
    return out


def export_instances(materials):
    """Collection instances (trees, chairs, scattered clumps): one prototype mesh per collection, joined and
    centred on the collection's instance offset, plus one transform per instance."""
    dg = bpy.context.evaluated_depsgraph_get()
    scratch = bpy.data.collections["EXPORT"]
    protos, inst = {}, []
    for e in bpy.data.objects:
        if e.instance_type != "COLLECTION" or e.instance_collection is None or e.hide_render:
            continue
        c = e.instance_collection
        if c.name not in protos:
            off = Matrix.Translation(-c.instance_offset)
            parts = []
            for ob in c.all_objects:
                if ob.type == "MESH":
                    new = bpy.data.objects.new("EXPORT proto " + ob.name, world_mesh(ob, dg, off @ ob.matrix_world))
                    new["src"] = "proto " + c.name
                    scratch.objects.link(new)
                    parts.append(new)
            if not parts:
                continue
            with bpy.context.temp_override(active_object=parts[0], selected_editable_objects=parts):
                bpy.ops.object.join()
            protos[c.name] = mesh_entry(parts[0], materials, "SM_proto_" + safe(c.name))
        loc, rot, scale = e.matrix_world.decompose()
        inst.append({"proto": c.name, "loc": [round(v, 4) for v in loc], "yaw": round(math.degrees(rot.to_euler().z), 2),      # model degrees (CCW)
                     "scale": [round(v, 4) for v in scale]})
    return protos, inst


def export_markers():
    def entry(ob):
        return {"name": ob.name[5:] if ob.name.startswith("Spot ") else ob.name,
                "loc": list(ob.matrix_world.translation), "yaw": math.degrees(ob.matrix_world.to_euler().z)}
    start = bpy.data.objects.get("Start")
    spots = [entry(ob) for ob in sorted(bpy.data.objects, key=lambda o: o.name) if ob.name.startswith("Spot ")]
    return (entry(start) if start else None), spots


def export_sun():
    sun = next((o for o in bpy.data.objects if o.type == "LIGHT" and o.data.type == "SUN"), None)
    if sun is None:
        return {"to_sun": [0.3, -0.5, 0.8], "lux": 75000}
    to_sun = (sun.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized()
    return {"to_sun": list(to_sun), "lux": 75000}


# ---------------------------------------------------------------------------

def main():
    for d in (MESH_DIR, TEX_OUT):
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(d)
    made = realize()
    materials, meshes, doors = {}, [], []
    for group, objs in made.items():
        for ob in objs:
            src = ob["src"]
            if ob.get("door"):
                info = json.loads(ob["door"])
                hx, hy, hz = info["hinge"]
                ob.data.transform(Matrix.Translation((-hx, -hy, -hz)))        # origin on the hinge
                e = mesh_entry(ob, materials, "SM_door_" + safe(src))
                e.update(name=src, hinge=[hx, hy, hz], open_yaw=ue_yaw(info["open"]), closed_yaw=ue_yaw(info["closed"]))
                doors.append(e)
            else:
                e = mesh_entry(ob, materials, "SM_" + safe(src))
                e.update(name=src, group=group)
                if ob.get("tags"):
                    e["tags"] = list(ob["tags"])
                meshes.append(e)
            log("%-48s %8d tris" % (e["file"], e["tris"]))
    protos, inst = export_instances(materials)
    start, spots = export_markers()
    manifest = {
        "units": "metres, z up; Unreal = (100 x, -100 y, 100 z)",
        "materials": materials, "meshes": meshes, "doors": doors,
        "protos": protos, "instances": inst,
        "lights": export_lights(), "sun": export_sun(),
        "player_start": start, "spots": spots,
    }
    with open(os.path.join(OUT_DIR, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    labels = os.path.join(BLEND_DIR, "labels.json")
    if os.path.exists(labels):
        shutil.copy2(labels, os.path.join(OUT_DIR, "labels.json"))
    log("done: %d meshes, %d doors, %d materials, %d prototypes, %d instances -> %s"
        % (len(meshes), len(doors), len(materials), len(protos), len(inst), OUT_DIR))


if __name__ == "__main__" and not globals().get("NO_MAIN"):
    main()
