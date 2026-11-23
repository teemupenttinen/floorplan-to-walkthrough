"""
Material helpers for Cycles that the exporters can read back (export_manifest.describe()).

Use them from a build script (shares its globals):

    TEX_DIR = "/path/to/textures"     # <Name>/<Name>_Color.jpg, _NormalGL.jpg, _Roughness.jpg (ambientCG layout)
    exec(open(os.path.join(KIT, "blender", "materials.py")).read(), globals())
    M = {
        "wall":  mat_flat("Wall white", "#F2EFE8", rough=0.8),
        "floor": mat_tex("Oak floor", "WoodFloor051", tile=(1.2, 1.2, 1.2), rough=0.45),
        "glass": mat_glass("Glass"),
        "lamp":  mat_emit("Globe lamp", "#FFE8C8", 8.0),
    }

Why this shape:
- The exporters only understand a few node layouts. Keep every material to one of them: Principled BSDF with a flat
  colour, or with image maps on world-box-projected coordinates ("tex"), or on the mesh UVs ("uv"), or the glass
  mix of Glossy + Transparent. Then the same material looks the same in Cycles, Unreal and the browser.
- Box projection in world space (Image Texture node in BOX mode on Geometry > Position) means no UV work on
  architectural boxes, and the exporters can write the same mapping into UVs (box_uvs()).
- Colours from photos and product pages are sRGB: convert them to linear first (srgb()). Typing an sRGB value into
  a Blender colour field makes it too light and washed out.

Textures: ambientCG and Poly Haven are CC0. Download the 1K or 2K JPG sets.
"""

import os

import bpy


def srgb(hex_or_rgb):
    """'#RRGGBB' or (r, g, b) in 0..255 or 0..1 sRGB -> linear (r, g, b)."""
    if isinstance(hex_or_rgb, str):
        h = hex_or_rgb.lstrip("#")
        c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    else:
        c = [v / 255.0 if max(hex_or_rgb) > 1.0 else v for v in hex_or_rgb]
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c)


def _new(name):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (400, 0)
    return m, nt, out


def mat_flat(name, color, rough=0.5, metal=0.0):
    m, nt, out = _new(name)
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    col = srgb(color) if isinstance(color, str) else color
    b.inputs["Base Color"].default_value = (*col, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    nt.links.new(b.outputs[0], out.inputs[0])
    m.diffuse_color = (*col, 1.0)        # viewport colour; the exporters fall back to it
    return m


def mat_emit(name, color, strength):
    """A lamp surface. The exporters turn it into an emissive material; add a real light for the illumination."""
    m, nt, out = _new(name)
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    col = srgb(color) if isinstance(color, str) else color
    b.inputs["Base Color"].default_value = (*col, 1.0)
    b.inputs["Emission Color"].default_value = (*col, 1.0)
    b.inputs["Emission Strength"].default_value = strength
    nt.links.new(b.outputs[0], out.inputs[0])
    return m


def mat_glass(name, tint=(0.95, 0.98, 0.97)):
    """Thin window glass: Glossy + Transparent by Fresnel. Cheap and noise-free in Cycles, and the exporters
    recognise the pair as kind 'glass'. Real-time engines draw it as translucent with a black base colour."""
    m, nt, out = _new(name)
    gl = nt.nodes.new("ShaderNodeBsdfGlossy")
    gl.inputs["Roughness"].default_value = 0.0
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    tr.inputs["Color"].default_value = (*tint, 1.0)
    fr = nt.nodes.new("ShaderNodeFresnel")
    fr.inputs["IOR"].default_value = 1.5
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(fr.outputs[0], mix.inputs[0])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(gl.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])
    return m


def _image(path, non_color=False):
    img = bpy.data.images.load(path, check_existing=True)
    if non_color:
        img.colorspace_settings.name = "Non-Color"
    return img


def mat_tex(name, set_name, tile=(1.0, 1.0, 1.0), rough=None, normal=1.0, saturation=1.0, value=1.0,
            tint=None, tint_mix=0.0, tex_dir=None):
    """Tiling image maps on world box projection. set_name is an ambientCG folder in TEX_DIR:
    <set>/<set>_Color.jpg, _NormalGL.jpg, _Roughness.jpg (or ambientCG's <set>_1K-JPG_Color.jpg ...).
    tile: tile size in metres (x, y, z). Delete the .blend/.usdc/.mtlx files that come in the zips unread.
    saturation / value / tint adjust a scan to a product colour without editing the image."""
    tex_dir = tex_dir or globals().get("TEX_DIR") or os.environ.get("TEX_DIR", "textures")
    base = os.path.join(tex_dir, set_name, set_name + "_")
    m, nt, out = _new(name)
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(b.outputs[0], out.inputs[0])
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.0 / tile[0], 1.0 / tile[1], 1.0 / tile[2])
    nt.links.new(geo.outputs["Position"], mp.inputs["Vector"])

    def find(suffix):
        """<set>_Color.jpg, or the names ambientCG downloads use now: <set>_1K-JPG_Color.jpg, _2K-PNG_ ..."""
        folder = os.path.dirname(base)
        for ext in (".jpg", ".png"):
            if os.path.exists(base + suffix + ext):
                return base + suffix + ext
        if os.path.isdir(folder):
            hits = sorted(f for f in os.listdir(folder) if f.startswith(set_name + "_") and
                          os.path.splitext(f)[0].endswith("_" + suffix) and f.lower().endswith((".jpg", ".png")))
            if hits:
                return os.path.join(folder, hits[0])
        return None

    def img_node(suffix, non_color):
        p = find(suffix)
        if p is None:
            return None
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = _image(p, non_color)
        n.projection = "BOX"
        n.projection_blend = 0.15
        nt.links.new(mp.outputs[0], n.inputs["Vector"])
        return n

    col = img_node("Color", False)
    if col is None:
        raise FileNotFoundError(base + "Color.jpg")
    c_out = col.outputs["Color"]
    if saturation != 1.0 or value != 1.0:
        hs = nt.nodes.new("ShaderNodeHueSaturation")
        hs.inputs["Saturation"].default_value = saturation
        hs.inputs["Value"].default_value = value
        nt.links.new(c_out, hs.inputs["Color"])
        c_out = hs.outputs["Color"]
    if tint is not None:
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.inputs["Factor"].default_value = tint_mix
        t = srgb(tint) if isinstance(tint, str) else tint
        nt.links.new(c_out, mix.inputs[6])
        mix.inputs[7].default_value = (*t, 1.0)
        c_out = mix.outputs[2]
    nt.links.new(c_out, b.inputs["Base Color"])
    r = img_node("Roughness", True)
    if r is not None and rough is None:
        nt.links.new(r.outputs["Color"], b.inputs["Roughness"])
    else:
        b.inputs["Roughness"].default_value = 0.5 if rough is None else rough
    n = img_node("NormalGL", True)
    if n is not None and normal > 0:
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = normal
        nt.links.new(n.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    return m


def mat_uv(name, color_path, rough=0.5, normal_path=None):
    """Image maps on the mesh's own UVs (downloaded models). The exporters read this as kind 'uv'."""
    m, nt, out = _new(name)
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(b.outputs[0], out.inputs[0])
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = _image(color_path)
    nt.links.new(t.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = rough
    if normal_path:
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = _image(normal_path, True)
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(n.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    return m
