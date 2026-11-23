"""
Build the walkthrough level from export/ (written by scripts/blender/export_manifest.py in Blender).

Run with the editor CLOSED (a commandlet cannot write assets the open editor holds):
  "$UE_ROOT/Engine/Binaries/Mac/UnrealEditor-Cmd" <abs>/Walkthrough.uproject \
      -run=pythonscript -script=<abs>/Content/Python/import_manifest.py
or inside the editor: Tools > Execute Python Script.

Environment:
  WALK_EXPORT=<dir>   the export folder (default: ../export next to the project folder)
  LEVEL_ONLY=1        only rebuild the level from assets that an earlier import made
  WALK_LEVEL=/Game/Maps/Walkthrough   level path

Steps: textures, master materials, one material instance per Blender material, meshes, doors, instance
prototypes, then a new level with the meshes, doors, scatter actors, lights, sun, sky, post process and a
player start. Spots (teleport points for keys 1..9) go to Content/Data/spots.json for AWalkCharacter.

Coordinates (docs/00-interfaces.md): model metres (x, y, z) -> Unreal cm (100 x, -100 y, 100 z).
A model yaw of a degrees (counter-clockwise about z) is Unreal yaw -a.

Gotchas are commented where they bite. Two general ones:
  - print() from a commandlet does not reach the log file; log() below uses unreal.log_warning.
  - The editor scripting subsystems refuse to spawn actors in a commandlet, so everything is spawned through
    the C++ helper UWalkScripting::SpawnInWorld (Python: unreal.WalkScripting.spawn_in_world).
"""

import json
import math
import os
import re
import unreal

PROJECT_DIR = os.path.normpath(unreal.Paths.project_dir())
EXPORT = os.environ.get("WALK_EXPORT") or os.path.normpath(os.path.join(PROJECT_DIR, "..", "export"))
ROOT = "/Game/Walkthrough"
LEVEL = os.environ.get("WALK_LEVEL", "/Game/Maps/Walkthrough")
DATA_DIR = os.path.join(PROJECT_DIR, "Content", "Data")

tools = unreal.AssetToolsHelpers.get_asset_tools()
mel = unreal.MaterialEditingLibrary
eal = unreal.EditorAssetLibrary

# Optional world-space weathering: a grey-scale streak mask (for example an ambientCG "Leaking" set). If the
# export has a texture with this name, M_Textured gets a "Weather" parameter (0 = clean) and WEATHER below
# sets it per material.
LEAK_MASK = "leak_mask.png"

# Weather amount by material name (first substring match wins). Facades, roads and roofs most, floors a little.
WEATHER = [("asphalt", 0.8), ("paving", 0.6), ("plinth", 0.6), ("render", 0.55), ("brick", 0.45),
           ("roof", 0.5), ("deck", 0.3), ("concrete floor", 0.12), ("carpet", 0.1), ("floor", 0.05)]


def log(*a):
    unreal.log_warning("[walkthrough] " + " ".join(str(x) for x in a))


def ue(x, y, z):
    return unreal.Vector(x * 100.0, -y * 100.0, z * 100.0)


def asset_name(s):
    return re.sub(r"[^A-Za-z0-9_]", "_", s).strip("_")


def norm(s):
    """Slot names change on the way through FBX (spaces, dots, case): compare them normalised."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def weather_of(name):
    n = name.lower()
    return next((w for k, w in WEATHER if k in n), 0.0)


def import_files(paths, dest):
    tasks = []
    for p in paths:
        t = unreal.AssetImportTask()
        t.filename = p
        t.destination_path = dest
        t.automated = True
        t.replace_existing = True
        t.save = True
        tasks.append(t)
    tools.import_asset_tasks(tasks)
    return {p: [unreal.load_asset(o) for o in t.imported_object_paths] for p, t in zip(paths, tasks)}


# ---------------------------------------------------------------------------
# Textures

def import_textures():
    folder = os.path.join(EXPORT, "tex")
    files = sorted(os.path.join(folder, f) for f in os.listdir(folder)) if os.path.isdir(folder) else []
    res = import_files(files, ROOT + "/Textures")
    tex = {}
    for path, objs in res.items():
        t = next((o for o in objs if isinstance(o, unreal.Texture2D)), None)
        if t is None:
            log("texture failed", path)
            continue
        name = os.path.basename(path).lower()
        if "normal" in name or "_nor" in name:
            t.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
            t.set_editor_property("srgb", False)
            # Most free scan libraries ship OpenGL normal maps (green up); Unreal expects DirectX.
            t.set_editor_property("flip_green_channel", True)
        elif "rough" in name:
            t.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
            t.set_editor_property("srgb", False)
        elif any(k in name for k in ("mask", "opacity", "alpha")):
            t.set_editor_property("srgb", False)
        # Sizes must be powers of two: other sizes get no mip maps, and distant surfaces shimmer.
        eal.save_loaded_asset(t)
        tex[os.path.basename(path)] = t
    log("textures", len(tex))
    return tex


# ---------------------------------------------------------------------------
# Material graph helpers

def new_material(name):
    """An empty material graph. An existing material is cleared, not deleted, so the instances and meshes
    that use it stay linked across re-imports."""
    m = unreal.load_asset(ROOT + "/Materials/" + name)
    if m is not None:
        mel.delete_all_material_expressions(m)
        return m
    return tools.create_asset(name, ROOT + "/Materials", unreal.Material, unreal.MaterialFactoryNew())


def lights_collection():
    """MPC_Lights.LightsOn (0 or 1): AWalkSun::SetLamps sets it together with the lamp actors, so lamp
    shades glow only while the lights are on."""
    path = ROOT + "/Materials/MPC_Lights"
    mpc = unreal.load_asset(path)
    if mpc is None:
        mpc = tools.create_asset("MPC_Lights", ROOT + "/Materials", unreal.MaterialParameterCollection,
                                 unreal.MaterialParameterCollectionFactoryNew())
    params = mpc.get_editor_property("scalar_parameters")
    if not any(str(p.get_editor_property("parameter_name")) == "LightsOn" for p in params):
        p = unreal.CollectionScalarParameter()
        p.set_editor_property("parameter_name", "LightsOn")
        p.set_editor_property("default_value", 0.0)
        mpc.set_editor_property("scalar_parameters", list(params) + [p])
    eal.save_loaded_asset(mpc)
    return mpc


def expr(mat, cls, x, y, **props):
    e = mel.create_material_expression(mat, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def scalar(mat, name, value, x, y):
    return expr(mat, unreal.MaterialExpressionScalarParameter, x, y, parameter_name=name, default_value=value)


def vector(mat, name, value, x, y):
    return expr(mat, unreal.MaterialExpressionVectorParameter, x, y, parameter_name=name,
                default_value=unreal.LinearColor(value[0], value[1], value[2], 1.0))


def link(a, out, b, inp):
    if not mel.connect_material_expressions(a, out, b, inp):
        log("link failed: %s.%s -> %s.%s" % (a.get_class().get_name(), out, b.get_class().get_name(), inp))


def lerp(mat, a, a_out, b, b_out, alpha, alpha_out, x, y):
    e = expr(mat, unreal.MaterialExpressionLinearInterpolate, x, y)
    link(a, a_out, e, "A")
    link(b, b_out, e, "B")
    link(alpha, alpha_out, e, "Alpha")
    return e


def placeholder(tex, *preferred, suffix=""):
    """A texture to put in a parameter node by default (instances override it)."""
    for p in preferred:
        if p in tex:
            return tex[p]
    for k, v in tex.items():
        if k.lower().endswith(suffix):
            return v
    return next(iter(tex.values()), None)


# ---------------------------------------------------------------------------
# Master materials

def master_textured(tex, mpc):
    """M_Textured: image maps on UV 0 (box-projected texture tiles, or the asset's own UVs).
    Colour steps as in the Blender material: Saturation and Value, then a Tint mix."""
    m = new_material("M_Textured")
    m.set_editor_property("used_with_instanced_static_meshes", True)
    color = expr(m, unreal.MaterialExpressionTextureSampleParameter2D, -1400, -300, parameter_name="Color",
                 texture=placeholder(tex, suffix="color.jpg"))
    lum = expr(m, unreal.MaterialExpressionDotProduct, -1100, -200)
    link(color, "RGB", lum, "A")
    w = expr(m, unreal.MaterialExpressionConstant3Vector, -1300, -100,
             constant=unreal.LinearColor(0.2126, 0.7152, 0.0722, 1))
    link(w, "", lum, "B")
    sat = lerp(m, lum, "", color, "RGB", scalar(m, "Saturation", 1.0, -1100, -50), "", -900, -250)
    val = expr(m, unreal.MaterialExpressionMultiply, -700, -250)
    link(sat, "", val, "A")
    link(scalar(m, "Value", 1.0, -900, -50), "", val, "B")
    base = lerp(m, val, "", vector(m, "Tint", (1, 1, 1), -700, -100), "",
                scalar(m, "TintMix", 0.0, -700, 50), "", -450, -250)
    leak = tex.get(LEAK_MASK)
    if leak is not None:
        base = weathering(m, base, leak)
    mel.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)

    # The RoughnessMap sampler (Masks) needs a linear roughness texture as its default. Without one in the export,
    # any other texture there (an sRGB colour map) fails the sampler check, the whole master material fails to
    # compile, and every textured surface draws the grey default checker (the error is only in the game log).
    rough_default = next((t for k, t in tex.items() if "rough" in k.lower()), None)
    if rough_default is not None:
        rough_t = expr(m, unreal.MaterialExpressionTextureSampleParameter2D, -1400, 200, parameter_name="RoughnessMap",
                       texture=rough_default, sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
        rough = lerp(m, scalar(m, "Roughness", 0.5, -1100, 150), "", rough_t, "R",
                     scalar(m, "UseRoughnessMap", 0.0, -1100, 300), "", -800, 200)
    else:
        log("no roughness maps in the export: M_Textured uses the Roughness value only")
        rough = scalar(m, "Roughness", 0.5, -1100, 150)
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(scalar(m, "Metallic", 0.0, -800, 400), "", unreal.MaterialProperty.MP_METALLIC)

    normal_tex = placeholder(tex, suffix="normalgl.jpg")
    if normal_tex is not None and normal_tex.get_editor_property("compression_settings") == unreal.TextureCompressionSettings.TC_NORMALMAP:
        normal_t = expr(m, unreal.MaterialExpressionTextureSampleParameter2D, -1400, 600, parameter_name="NormalMap",
                        texture=normal_tex, sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
        flat = expr(m, unreal.MaterialExpressionConstant3Vector, -1100, 500, constant=unreal.LinearColor(0, 0, 1, 1))
        normal = lerp(m, flat, "", normal_t, "RGB", scalar(m, "NormalStrength", 0.0, -1100, 750), "", -800, 600)
        mel.connect_material_property(normal, "", unreal.MaterialProperty.MP_NORMAL)
    else:
        scalar(m, "NormalStrength", 0.0, -1100, 750)       # keep the parameter so instances can set it

    # Emission glows only while the lamps are on (lamp shades, LED strips).
    on = expr(m, unreal.MaterialExpressionCollectionParameter, -1000, 1000, collection=mpc)
    on.set_editor_property("parameter_name", "LightsOn")
    glow = expr(m, unreal.MaterialExpressionMultiply, -800, 900)
    link(vector(m, "Emissive", (0, 0, 0), -1000, 850), "", glow, "A")
    link(on, "", glow, "B")
    mel.connect_material_property(glow, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    return m


def weathering(m, color, leak):
    """Dirt (parameter Weather, 0 = none): the leak mask projected in world space, as rain streaks on walls
    (3.2 m tiles, running down), as blotches on floors and roads (4.5 m tiles), and as a slow 30 m variation
    that breaks up texture repeats. The colour is pulled toward a grey-brown grime."""
    wp = expr(m, unreal.MaterialExpressionWorldPosition, -2600, 1000)
    nrm = expr(m, unreal.MaterialExpressionVertexNormalWS, -2600, 1300)

    def comp(src, r, g, b, x, y):
        e = expr(m, unreal.MaterialExpressionComponentMask, x, y, r=r, g=g, b=b, a=False)
        link(src, "", e, "")
        return e

    def div(e, k, x, y):
        d = expr(m, unreal.MaterialExpressionDivide, x, y, const_b=k)
        link(e, "", d, "A")
        return d

    def sample(uv, x, y):
        t = expr(m, unreal.MaterialExpressionTextureSample, x, y, texture=leak,
                 sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
        link(uv, "", t, "UVs")
        return comp(t, True, False, False, x + 150, y)

    wx, wy, wz = comp(wp, True, False, False, -2400, 900), comp(wp, False, True, False, -2400, 1000), comp(wp, False, False, True, -2400, 1100)
    along = expr(m, unreal.MaterialExpressionAdd, -2200, 900)
    link(wx, "", along, "A")
    link(wy, "", along, "B")
    down = expr(m, unreal.MaterialExpressionMultiply, -2200, 1100, const_b=-1.0)
    link(wz, "", down, "A")
    wall_uv = expr(m, unreal.MaterialExpressionAppendVector, -2000, 1000)
    link(div(along, 320.0, -2100, 900), "", wall_uv, "A")
    link(div(down, 320.0, -2100, 1100), "", wall_uv, "B")
    ground = expr(m, unreal.MaterialExpressionAppendVector, -2000, 1300)
    link(wx, "", ground, "A")
    link(wy, "", ground, "B")
    wall_t = sample(wall_uv, -1800, 1000)
    ground_t = sample(div(ground, 450.0, -1900, 1300), -1800, 1300)
    slow_t = sample(div(ground, 3000.0, -1900, 1500), -1800, 1500)
    up = expr(m, unreal.MaterialExpressionAbs, -2200, 1300)
    link(comp(nrm, False, False, True, -2400, 1300), "", up, "")
    streak = lerp(m, wall_t, "", ground_t, "", up, "", -1600, 1100)
    weather = scalar(m, "Weather", 0.0, -1600, 1300)
    amount = expr(m, unreal.MaterialExpressionMultiply, -1400, 1100)
    link(streak, "", amount, "A")
    link(weather, "", amount, "B")
    slow = expr(m, unreal.MaterialExpressionMultiply, -1400, 1400, const_b=0.35)
    link(slow_t, "", slow, "A")
    slow_w = expr(m, unreal.MaterialExpressionMultiply, -1300, 1400)
    link(slow, "", slow_w, "A")
    link(weather, "", slow_w, "B")
    total = expr(m, unreal.MaterialExpressionAdd, -1200, 1200)
    link(amount, "", total, "A")
    link(slow_w, "", total, "B")
    sat = expr(m, unreal.MaterialExpressionSaturate, -1100, 1200)
    link(total, "", sat, "")
    grime = expr(m, unreal.MaterialExpressionMultiply, -1000, 1000)
    link(color, "", grime, "A")
    link(expr(m, unreal.MaterialExpressionConstant3Vector, -1200, 950,
              constant=unreal.LinearColor(0.48, 0.44, 0.38, 1)), "", grime, "B")
    return lerp(m, color, "", grime, "", sat, "", -800, 1000)


def master_flat(mpc):
    m = new_material("M_Flat")
    # Instanced (HISM) meshes fall back to the grey default material without this flag.
    m.set_editor_property("used_with_instanced_static_meshes", True)
    mel.connect_material_property(vector(m, "Color", (0.7, 0.7, 0.7), -500, -200), "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(scalar(m, "Roughness", 0.5, -500, 0), "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(scalar(m, "Metallic", 0.0, -500, 100), "", unreal.MaterialProperty.MP_METALLIC)
    on = expr(m, unreal.MaterialExpressionCollectionParameter, -700, 400, collection=mpc)
    on.set_editor_property("parameter_name", "LightsOn")
    glow = expr(m, unreal.MaterialExpressionMultiply, -300, 300)
    link(vector(m, "Emissive", (0, 0, 0), -700, 250), "", glow, "A")
    link(on, "", glow, "B")
    mel.connect_material_property(glow, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    return m


def master_glass():
    """Thin window glass. The base colour is BLACK: a lit, light glass draws a milky veil over the window view.
    Opacity only darkens (raise it for smoked glass); the reflections come from the specular, stronger at
    grazing angles (fresnel). Needs Lumen front-layer translucency reflections (DefaultEngine.ini)."""
    m = new_material("M_Glass")
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    m.set_editor_property("translucency_lighting_mode", unreal.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
    m.set_editor_property("two_sided", True)
    vector(m, "Tint", (0.95, 0.98, 0.97), -900, -300)          # kept for the instances, not wired
    black = expr(m, unreal.MaterialExpressionConstant3Vector, -350, -200, constant=unreal.LinearColor(0, 0, 0, 1))
    mel.connect_material_property(black, "", unreal.MaterialProperty.MP_BASE_COLOR)
    fres = expr(m, unreal.MaterialExpressionFresnel, -600, 100, exponent=5.0, base_reflect_fraction=0.04)
    opac = lerp(m, scalar(m, "Opacity", 0.03, -800, 0), "", expr(m, unreal.MaterialExpressionConstant, -800, 200, r=0.5), "",
                fres, "", -350, 50)
    mel.connect_material_property(opac, "", unreal.MaterialProperty.MP_OPACITY)
    mel.connect_material_property(expr(m, unreal.MaterialExpressionConstant, -350, 250, r=0.02), "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(expr(m, unreal.MaterialExpressionConstant, -350, 350, r=1.0), "", unreal.MaterialProperty.MP_SPECULAR)
    mel.recompile_material(m)
    return m


def master_leaf_tex(tex):
    """M_LeafTex: leaf cards and grass clumps with a photo atlas: Color x Tint, cut out by Mask.
    Two Sided Foliage lets light through from behind (also good for paper, curtains, lamp shades)."""
    m = new_material("M_LeafTex")
    m.set_editor_property("used_with_instanced_static_meshes", True)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_TWO_SIDED_FOLIAGE)
    m.set_editor_property("two_sided", True)
    color = expr(m, unreal.MaterialExpressionTextureSampleParameter2D, -900, -300, parameter_name="Color",
                 texture=placeholder(tex, suffix="color.png"))
    mask = expr(m, unreal.MaterialExpressionTextureSampleParameter2D, -900, 200, parameter_name="Mask",
                texture=placeholder(tex, suffix="opacity.png"), sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    mel.connect_material_property(mask, "R", unreal.MaterialProperty.MP_OPACITY_MASK)
    tinted = expr(m, unreal.MaterialExpressionMultiply, -600, -300)
    link(color, "RGB", tinted, "A")
    link(vector(m, "Tint", (1, 1, 1), -800, -100), "", tinted, "B")
    mel.connect_material_property(tinted, "", unreal.MaterialProperty.MP_BASE_COLOR)
    sss = expr(m, unreal.MaterialExpressionMultiply, -400, 0)
    link(tinted, "", sss, "A")
    link(expr(m, unreal.MaterialExpressionConstant, -600, 100, r=0.8), "", sss, "B")
    mel.connect_material_property(sss, "", unreal.MaterialProperty.MP_SUBSURFACE_COLOR)
    mel.connect_material_property(expr(m, unreal.MaterialExpressionConstant, -400, 300, r=0.55), "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.recompile_material(m)
    return m


# ---------------------------------------------------------------------------
# Material instances

def instance(name, parent):
    path = ROOT + "/Materials/Instances/MI_" + asset_name(name)
    mi = unreal.load_asset(path)
    if mi is None:
        mi = tools.create_asset("MI_" + asset_name(name), ROOT + "/Materials/Instances",
                                unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(mi, parent)
    return mi


def set_s(mi, k, v):
    mel.set_material_instance_scalar_parameter_value(mi, k, float(v))


def set_v(mi, k, v):
    mel.set_material_instance_vector_parameter_value(mi, k, unreal.LinearColor(v[0], v[1], v[2], 1.0))


def set_t(mi, k, t):
    if t is not None:
        mel.set_material_instance_texture_parameter_value(mi, k, t)


def make_instances(materials, masters, tex):
    out = {}
    for name, d in materials.items():
        kind = d.get("kind", "flat")
        if kind in ("tex", "uv") and d.get("color_tex") in tex:
            mi = instance(name, masters["tex"])
            set_t(mi, "Color", tex[d["color_tex"]])
            set_s(mi, "Saturation", d.get("saturation", 1.0))
            set_s(mi, "Value", d.get("value", 1.0))
            if "tint" in d:
                set_v(mi, "Tint", d["tint"])
                set_s(mi, "TintMix", d.get("tint_mix", 0.0))
            set_s(mi, "Roughness", d.get("rough", 0.5))
            set_s(mi, "Metallic", d.get("metal", 0.0))
            if d.get("rough_tex") in tex:          # (the parameter exists only when the export has roughness maps)
                set_t(mi, "RoughnessMap", tex[d["rough_tex"]])
                set_s(mi, "UseRoughnessMap", 1.0)
            if d.get("normal_tex") in tex:
                set_t(mi, "NormalMap", tex[d["normal_tex"]])
                set_s(mi, "NormalStrength", d.get("normal", 1.0))
            if "emit" in d:
                set_v(mi, "Emissive", d["emit"])
            if LEAK_MASK in tex:
                set_s(mi, "Weather", weather_of(name))
            if d.get("masked"):
                # Single-sheet assets (grass blades, plant leaves): draw both sides, cut out by alpha.
                ov = mi.get_editor_property("base_property_overrides")
                ov.set_editor_property("override_two_sided", True)
                ov.set_editor_property("two_sided", True)
                mi.set_editor_property("base_property_overrides", ov)
        elif kind == "leaf_tex" and d.get("color_tex") in tex:
            mi = instance(name, masters["leaf_tex"])
            set_t(mi, "Color", tex[d["color_tex"]])
            set_t(mi, "Mask", tex.get(d.get("mask_tex")))
            set_v(mi, "Tint", d.get("tint", (1, 1, 1)))
        elif kind == "glass":
            mi = instance(name, masters["glass"])
            tint = d.get("tint", (0.95, 0.98, 0.97))
            set_v(mi, "Tint", tint)
            if min(tint) < 0.8:
                set_s(mi, "Opacity", 0.4)          # smoked glass
        else:
            mi = instance(name, masters["flat"])
            set_v(mi, "Color", d.get("color", (0.7, 0.7, 0.7)))
            set_s(mi, "Roughness", d.get("rough", 0.5))
            set_s(mi, "Metallic", d.get("metal", 0.0))
            if "emit" in d:
                set_v(mi, "Emissive", d["emit"])
        # Always save without the "only if dirty" check: an instance whose only change is a new parent is
        # not marked dirty and would otherwise be skipped.
        eal.save_loaded_asset(mi, False)
        out[name] = mi
    log("material instances", len(out))
    return out


# ---------------------------------------------------------------------------
# Meshes

def import_meshes(entries, mis, dest):
    files = [os.path.join(EXPORT, "meshes", e["file"] + ".fbx") for e in entries]
    files = [f for f in files if os.path.exists(f)]
    res = import_files(files, dest) if files else {}
    meshes = {}
    for e in entries:
        f = os.path.join(EXPORT, "meshes", e["file"] + ".fbx")
        sm = next((o for o in res.get(f, []) if isinstance(o, unreal.StaticMesh)), None)
        if sm is None:
            log("mesh failed", f)
            continue
        by_norm = {norm(k): mis[k] for k in e["materials"] if k in mis}
        slots = sm.get_editor_property("static_materials")
        for i, slot in enumerate(slots):
            mi = by_norm.get(norm(str(slot.get_editor_property("material_slot_name"))))
            if mi is None and len(slots) == len(e["materials"]):
                mi = mis.get(e["materials"][i])           # same count: trust the order
            if mi is None:
                log("no material for slot", slot.get_editor_property("material_slot_name"), "in", e["file"])
                continue
            sm.set_material(i, mi)
        # Nanite off: room-scale meshes are small, and the Nanite fallback mesh (drawn on some GPUs and in
        # -game runs) simplifies thin parts away: lamp wires, taps, handles, window reveals.
        ns = sm.get_editor_property("nanite_settings")
        ns.set_editor_property("enabled", False)
        sm.set_editor_property("nanite_settings", ns)
        body = sm.get_editor_property("body_setup")
        if body is not None:
            # Walls, stairs and furniture collide with their real triangles: no hand-made collision needed.
            body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        eal.save_loaded_asset(sm)
        meshes[e["file"]] = sm
    log("meshes", len(meshes), "into", dest)
    return meshes


def load_meshes(entries, dest):
    out = {}
    for e in entries:
        sm = unreal.load_asset(dest + "/" + e["file"])
        if sm is not None:
            out[e["file"]] = sm
    return out


def check_bounds(meshes, limit_m=5000.0):
    """A bevel that went wrong in Blender can throw vertices 1e20 m away: the mesh then gets NaN bounds and
    slivers with collision cross the level. Check by script instead of rendering."""
    bad = 0
    for name, sm in meshes.items():
        b = sm.get_bounding_box()
        ext = max(abs(v) for v in (b.min.x, b.min.y, b.min.z, b.max.x, b.max.y, b.max.z))
        if not math.isfinite(ext) or ext > limit_m * 100:
            log("BOUNDS PROBLEM", name, b.min, b.max)
            bad += 1
    log("bounds check: %d of %d meshes out of range" % (bad, len(meshes)))


# ---------------------------------------------------------------------------
# Level

def spawn(world, cls, loc, label, folder, rot=None, scale=None):
    xf = unreal.Transform(loc, rot or unreal.Rotator(0, 0, 0), scale or unreal.Vector(1, 1, 1))
    a = unreal.WalkScripting.spawn_in_world(world, cls, xf)
    if a is None:
        raise RuntimeError("could not spawn " + label)
    a.set_actor_label(label)
    a.set_folder_path(folder)
    return a


def spawn_mesh(world, mesh, loc, label, folder, rot=None, scale=None):
    a = spawn(world, unreal.StaticMeshActor, loc, label, folder, rot, scale)
    a.static_mesh_component.set_static_mesh(mesh)
    return a


def sun_rotation(to_sun):
    """Directional light rotation from the model's direction toward the sun (the light travels away from it)."""
    d = unreal.Vector(-to_sun[0], to_sun[1], -to_sun[2])       # model -> Unreal axes, then reversed
    yaw = math.degrees(math.atan2(d.y, d.x))
    pitch = math.degrees(math.atan2(d.z, math.hypot(d.x, d.y)))
    return unreal.Rotator(roll=0.0, pitch=pitch, yaw=yaw)


def build_lights(world, lights):
    """Room lights, hidden at the start (daytime). AWalkSun::SetLamps switches every actor tagged
    CeilingLight; the second tag names the room. Warm white 3000 K, in lumens."""
    down = unreal.Rotator(roll=0.0, pitch=-90.0, yaw=0.0)
    for i, L in enumerate(lights):
        loc = ue(*L["loc"])
        kind = L.get("kind", "point")
        if kind == "rect":
            a = spawn(world, unreal.RectLight, loc - unreal.Vector(0, 0, 1), L.get("name", "Room light"), "Lighting/Lamps", down)
            c = a.get_component_by_class(unreal.RectLightComponent)
            sx, sy = L.get("size", [0.6, 0.6])
            c.set_editor_property("source_width", sy * 100)        # local y = world y, local z = world x
            c.set_editor_property("source_height", sx * 100)
            c.set_editor_property("barn_door_angle", 70.0)
            c.set_editor_property("barn_door_length", 10.0)
            c.set_editor_property("specular_scale", 0.3)         # no bright panel mirrored in glossy floors
            lumens = L.get("lumens", 100.0 * sx * sy / 0.36)     # ~100 lm per m2 of a room 1/0.6 the light's size
            radius = 120.0 + 100.0 * max(sx, sy) / 0.6
        elif kind == "spot":
            a = spawn(world, unreal.SpotLight, loc, "%s %d" % (L.get("name", "Spot"), i), "Lighting/Lamps", down)
            c = a.get_component_by_class(unreal.SpotLightComponent)
            c.set_editor_property("inner_cone_angle", 25.0)
            c.set_editor_property("outer_cone_angle", 50.0)
            c.set_editor_property("source_radius", 3.0)
            # A short reach: many overlapping lights overflow a cell of the forward light grid, which shows
            # as bright or dark rectangles on walls. See r.Forward.MaxCulledLightsPerCell in the ini snippet.
            lumens, radius = L.get("lumens", 450.0), 420.0
        else:
            a = spawn(world, unreal.PointLight, loc, "%s %d" % (L.get("name", "Lamp"), i), "Lighting/Lamps")
            c = a.get_component_by_class(unreal.PointLightComponent)
            c.set_editor_property("source_radius", L.get("radius", 0.05) * 100)
            lumens, radius = L.get("lumens", 250.0), 400.0
        c.set_mobility(unreal.ComponentMobility.MOVABLE)
        c.set_editor_property("intensity_units", unreal.LightUnits.LUMENS)
        c.set_editor_property("intensity", lumens)
        c.set_editor_property("attenuation_radius", radius)
        c.set_editor_property("use_temperature", True)
        c.set_editor_property("temperature", 3000.0)
        c.set_editor_property("visible", False)
        a.set_editor_property("tags", [unreal.Name("CeilingLight"), unreal.Name(L.get("name", "Room"))])
    log("lights", len(lights))


# Exposure for rooms with bright windows: meter the room and ignore the brightest 35 % (the windows), then
# local exposure compresses the window view and lifts dark corners. The minimum brightness keeps a dark room
# dark at night. Physical units throughout: the sun is 75 000 lux.
POST = (
    ("auto_exposure_method", unreal.AutoExposureMethod.AEM_HISTOGRAM),
    ("auto_exposure_min_brightness", 4.0), ("auto_exposure_max_brightness", 15.0),
    ("auto_exposure_bias", 1.3), ("auto_exposure_low_percent", 10.0), ("auto_exposure_high_percent", 65.0),
    ("auto_exposure_speed_up", 2.0), ("auto_exposure_speed_down", 1.5),
    ("local_exposure_highlight_contrast_scale", 0.18), ("local_exposure_shadow_contrast_scale", 0.85),
    ("local_exposure_detail_strength", 1.0), ("local_exposure_blurred_luminance_blend", 0.6),
    ("lumen_final_gather_quality", 2.0), ("lumen_scene_detail", 2.0),
    ("lumen_scene_lighting_quality", 2.0), ("lumen_reflection_quality", 2.0),
    ("vignette_intensity", 0.25), ("bloom_intensity", 0.4),
    ("motion_blur_amount", 0.2), ("motion_blur_max", 2.0),          # slight; the engine default is 0.5 / 5 %
    # A little more colour. Leave these out if a green lawn outside tints white walls olive.
    ("color_saturation", unreal.Vector4(1.1, 1.1, 1.1, 1.0)), ("lumen_diffuse_color_boost", 1.2),
)


def apply_post(ppv):
    """Unbound post process volume with POST. Returns the settings this engine version does not have."""
    ppv.set_editor_property("unbound", True)
    s = ppv.get_editor_property("settings")
    missing = []
    for k, v in POST:
        try:
            s.set_editor_property(k, v)
            s.set_editor_property("override_" + k, True)
        except Exception:
            missing.append(k)
    ppv.set_editor_property("settings", s)
    if missing:
        log("post settings not in this engine:", ", ".join(missing))


def write_spots(man):
    """Teleport points for keys 1..9 (AWalkCharacter reads Content/Data/spots.json), in Unreal units."""
    os.makedirs(DATA_DIR, exist_ok=True)
    spots = []
    for s in man.get("spots", []):
        p = ue(*s["loc"])
        spots.append({"name": s.get("name", ""), "loc": [p.x, p.y, p.z], "yaw": -float(s.get("yaw", 0.0))})
    json.dump({"spots": spots}, open(os.path.join(DATA_DIR, "spots.json"), "w"), indent=1)
    log("spots", len(spots))


def build_level(man, meshes, door_meshes, proto_meshes):
    if eal.does_asset_exist(LEVEL):
        eal.delete_asset(LEVEL)
    # new_blank_map works in a commandlet; new_level does not set the editor world there.
    world = unreal.EditorLoadingAndSavingUtils.new_blank_map(False)

    for e in man.get("meshes", []):
        if e["file"] not in meshes:
            continue
        a = spawn_mesh(world, meshes[e["file"]], unreal.Vector(0, 0, 0), e.get("name", e["file"]),
                       "Model/" + e.get("group", "misc"))
        if e.get("tags"):
            # Tagged actors are switched at run time (furniture sets, options): they must be movable.
            a.static_mesh_component.set_mobility(unreal.ComponentMobility.MOVABLE)
            a.set_editor_property("tags", [unreal.Name(t) for t in e["tags"]])

    door_class = unreal.load_class(None, "/Script/Walkthrough.WalkDoor")
    for e in man.get("doors", []):
        if e["file"] not in door_meshes:
            continue
        d = spawn(world, door_class, ue(*e["hinge"]), e.get("name", e["file"]), "Model/Doors")
        d.get_editor_property("leaf").set_static_mesh(door_meshes[e["file"]])
        d.set_editor_property("closed_yaw", float(e["closed_yaw"]))
        d.set_editor_property("open_yaw", float(e["open_yaw"]))
        d.set_editor_property("open", bool(e.get("open", False)))

    # Instances (trees, grass clumps, cars): one AWalkScatter (hierarchical instanced mesh) per prototype.
    scatter_class = unreal.load_class(None, "/Script/Walkthrough.WalkScatter")
    by_proto = {}
    for t in man.get("instances", []):
        by_proto.setdefault(t["proto"], []).append(t)
    for proto, items in by_proto.items():
        info = man.get("protos", {}).get(proto)
        mesh = proto_meshes.get(info["file"]) if info else None
        if mesh is None:
            continue
        xfs = []
        for t in items:
            s = t.get("scale", [1, 1, 1])
            if not isinstance(s, (list, tuple)):
                s = [s, s, s]
            xfs.append(unreal.Transform(ue(*t["loc"]), unreal.Rotator(roll=0.0, pitch=0.0, yaw=-float(t.get("yaw", 0.0))),
                                        unreal.Vector(*s)))
        small = info.get("small", "grass" in proto.lower())
        a = spawn(world, scatter_class, unreal.Vector(0, 0, 0), "Scatter " + proto, "Site/Scatter")
        # Grass: short cull distance and no shadows (millions of triangles otherwise). Trees: far, with shadows.
        if small:
            a.set_instances(mesh, xfs, 3000.0, 4500.0, False)
        else:
            a.set_instances(mesh, xfs, 45000.0, 60000.0, True)
    log("scatter actors", len(by_proto), "instances", len(man.get("instances", [])))

    # Sun and sky: physical sky lit by the sun of the Blender scene.
    sun_info = man.get("sun", {"to_sun": [0.3, -0.5, 0.8]})
    sun = spawn(world, unreal.DirectionalLight, unreal.Vector(0, 0, 2000), "Sun", "Lighting", sun_rotation(sun_info["to_sun"]))
    lc = sun.get_component_by_class(unreal.DirectionalLightComponent)
    lc.set_mobility(unreal.ComponentMobility.MOVABLE)
    lc.set_editor_property("intensity", float(sun_info.get("lux", 75000.0)))
    lc.set_editor_property("atmosphere_sun_light", True)
    lc.set_editor_property("light_source_angle", 0.5357)        # the real sun disc: soft shadow ends
    lc.set_editor_property("use_temperature", True)
    lc.set_editor_property("temperature", 5600.0)
    spawn(world, unreal.SkyAtmosphere, unreal.Vector(0, 0, 0), "Sky atmosphere", "Lighting")
    sky = spawn(world, unreal.SkyLight, unreal.Vector(0, 0, 500), "Sky light", "Lighting")
    sc = sky.get_component_by_class(unreal.SkyLightComponent)
    sc.set_mobility(unreal.ComponentMobility.MOVABLE)
    sc.set_editor_property("real_time_capture", True)          # follows the sun when the hour changes
    spawn(world, unreal.VolumetricCloud, unreal.Vector(0, 0, 0), "Clouds", "Lighting")
    fog = spawn(world, unreal.ExponentialHeightFog, unreal.Vector(0, 0, 0), "Height fog", "Lighting")
    fc = fog.get_component_by_class(unreal.ExponentialHeightFogComponent)
    fc.set_editor_property("fog_density", 0.002)
    fc.set_editor_property("start_distance", 1500.0)           # no haze inside the rooms
    ppv = spawn(world, unreal.PostProcessVolume, unreal.Vector(0, 0, 0), "Post process", "Lighting")
    apply_post(ppv)

    # The sun controller of the C++ module: hour, day, exposure, white balance, lamps.
    sun_class = unreal.load_class(None, "/Script/Walkthrough.WalkSun")
    if sun_class is not None:
        spawn(world, sun_class, unreal.Vector(0, 0, 0), "Sun controller", "Lighting")

    build_lights(world, man.get("lights", []))
    ps = man.get("player_start") or {"loc": [0, 0, 0], "yaw": 0.0}      # the exporter writes null without a "Start" empty
    # The player start stands at capsule centre height: eye on the floor + ~0.95 m. If its capsule touches
    # geometry the pawn does not spawn ("SpawnActor failed because of collision" in the log), and the game
    # runs at ~2 fps with a fallback camera. Keep it in open floor space.
    p = ps["loc"]
    spawn(world, unreal.PlayerStart, ue(p[0], p[1], p[2] + 0.95), "Player start", "",
          unreal.Rotator(roll=0.0, pitch=0.0, yaw=-float(ps.get("yaw", 0.0))))
    unreal.EditorLoadingAndSavingUtils.save_map(world, LEVEL)
    log("level saved", LEVEL)


def import_all(man):
    tex = import_textures()
    mpc = lights_collection()
    masters = {"tex": master_textured(tex, mpc), "flat": master_flat(mpc), "glass": master_glass(),
               "leaf_tex": master_leaf_tex(tex)}
    for m in masters.values():
        eal.save_loaded_asset(m)          # the instances depend on them: save before anything can fail
    mis = make_instances(man.get("materials", {}), masters, tex)
    meshes = import_meshes(man.get("meshes", []), mis, ROOT + "/Meshes")
    doors = import_meshes(man.get("doors", []), mis, ROOT + "/Doors")
    protos = import_meshes(list(man.get("protos", {}).values()), mis, ROOT + "/Protos")
    return meshes, doors, protos


def main():
    man = json.load(open(os.path.join(EXPORT, "manifest.json")))
    log("export", EXPORT)
    if os.environ.get("LEVEL_ONLY"):
        meshes = load_meshes(man.get("meshes", []), ROOT + "/Meshes")
        doors = load_meshes(man.get("doors", []), ROOT + "/Doors")
        protos = load_meshes(list(man.get("protos", {}).values()), ROOT + "/Protos")
    else:
        meshes, doors, protos = import_all(man)
    check_bounds({**meshes, **doors})
    write_spots(man)
    build_level(man, meshes, doors, protos)
    eal.save_directory(ROOT)
    log("done")


if not globals().get("NO_MAIN"):
    main()
