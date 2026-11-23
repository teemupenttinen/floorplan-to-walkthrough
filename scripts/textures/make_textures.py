"""
Texture sets graded to a photo: tileable scans (ambientCG, CC0) recoloured to the mean colour of the matching patch
of a listing or product photo, plus a few operations scans need (boards turned vertical, tile joints, a plank floor
built from a wood scan). Runs in Blender's Python (numpy and image IO, no PIL):

  blender -b --factory-startup --python-exit-code 1 --python scripts/textures/make_textures.py -- \
      recipes.json textures/src textures

recipes.json (see recipes.example.json):
  {"OakPlank": {"src": "Wood058", "ops": ["planks", ["sat", 0.85]], "target": [208, 181, 150], "size": 2048}, ...}
  src     scan folder in <src dir> (files <set>_Color.jpg or ambientCG's <set>_1K-JPG_Color.jpg)
  ops     "T" transpose (horizontal boards -> vertical); ["sat", s] saturation; ["contrast", c] pull toward the mean;
          ["grid", n, width px, darkness] n x n tile joints; "planks" or ["planks", n, tile m] a one-strip floor
  target  mean sRGB 0..255 after grading
  size    output size in px (a power of two: Unreal gives other sizes no mip maps)
Writes <out dir>/<Name>/<Name>_Color.jpg, the layout materials.mat_tex() reads.

How to pick the target: take the mean colour of a flat patch of the photo, then correct it for the photo's exposure and
white balance with a surface of known colour in the same photo (white wall or ceiling paint): target = patch x
(known / measured). Check the result in the renderer it is for: the same image reads about 10 % more yellow and
saturated under Unreal's filmic tone map than under three.js Neutral.
"""
import json
import os
import sys

import bpy
import numpy as np

ARGS = sys.argv[sys.argv.index("--") + 1:]
RECIPES, SRC, OUT = ARGS[0], ARGS[1], ARGS[2]
RNG = np.random.default_rng(7)


def load(path, size=None):
    img = bpy.data.images.load(path)
    if size and tuple(img.size) != (size, size):
        img.scale(size, size)
    a = np.empty(img.size[0] * img.size[1] * 4, dtype=np.float32)
    img.pixels.foreach_get(a)
    w, h = img.size
    bpy.data.images.remove(img)
    return a.reshape(h, w, 4)[..., :3].copy()


def save(rgb, path):
    h, w = rgb.shape[:2]
    img = bpy.data.images.new("tex", w, h, alpha=False)
    img.colorspace_settings.name = "sRGB"
    px = np.ones((h, w, 4), dtype=np.float32)
    px[..., :3] = np.clip(rgb, 0, 1)
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = path
    img.file_format = "JPEG"
    bpy.context.scene.render.image_settings.quality = 92
    img.save()
    bpy.data.images.remove(img)


def planks(src, size, n=13, tile=2.4, lengths=(0.9, 2.4)):
    """One-strip plank floor from a wood scan: n planks across the tile (13 on a 2.4 m tile = 18.5 cm planks),
    random lengths in metres, per-plank tone, dark joints. Planks run along the image's v axis (model x on floors,
    see export_manifest.box_uvs). Wraps in both directions."""
    wood = load(src, size)                    # grain runs along v (rows)
    out = np.empty_like(wood)
    edges = np.round(np.linspace(0, size, n + 1)).astype(int)
    for i in range(n):
        x0, x1 = edges[i], edges[i + 1]
        y0 = int(RNG.integers(0, size))
        done = 0
        while done < size:
            length = min(int(RNG.uniform(*lengths) / tile * size), size - done)
            sx = int(RNG.integers(0, size - (x1 - x0)))
            sy = int(RNG.integers(0, size))
            tone = RNG.uniform(0.92, 1.06) * np.array([1.0, RNG.uniform(0.985, 1.01), RNG.uniform(0.97, 1.01)])
            k = np.arange(length)
            out[(y0 + done + k) % size, x0:x1] = wood[(sy + k) % size, sx:sx + (x1 - x0)] * tone
            out[(y0 + done) % size, x0:x1] *= 0.55     # end joint
            done += length
        out[:, x0] *= 0.55                              # long joint
    return out


def grade(rgb, target):
    mean = rgb.reshape(-1, 3).mean(axis=0)
    return rgb * (np.array(target) / 255.0) / np.maximum(mean, 1e-4)


def find_color(set_name):
    folder = os.path.join(SRC, set_name)
    for f in sorted(os.listdir(folder)):
        if f.startswith(set_name + "_") and os.path.splitext(f)[0].endswith("_Color"):
            return os.path.join(folder, f)
    raise FileNotFoundError(folder + ": no <set>_..._Color image")


def main():
    for name, r in json.load(open(RECIPES)).items():
        src, ops, size = find_color(r["src"]), r.get("ops", []), r.get("size", 1024)
        plank = next((o for o in ops if o == "planks" or (isinstance(o, list) and o[0] == "planks")), None)
        if plank is None:
            rgb = load(src, size)
        else:
            rgb = planks(src, size, *(plank[1:] if isinstance(plank, list) else []))
        for op in ops:
            if op == "T":
                rgb = rgb.transpose(1, 0, 2).copy()
            elif isinstance(op, list) and op[0] == "sat":
                lum = rgb @ np.array([0.2126, 0.7152, 0.0722])
                rgb = lum[..., None] + (rgb - lum[..., None]) * op[1]
            elif isinstance(op, list) and op[0] == "contrast":
                m = rgb.reshape(-1, 3).mean(axis=0)
                rgb = m + (rgb - m) * op[1]
            elif isinstance(op, list) and op[0] == "grid":
                _, k, wpx, dark = op
                h, w = rgb.shape[:2]
                for j in range(k):
                    rgb[int(j * h / k):int(j * h / k) + wpx, :] *= dark
                    rgb[:, int(j * w / k):int(j * w / k) + wpx] *= dark
        rgb = grade(rgb, r["target"])
        d = os.path.join(OUT, name)
        os.makedirs(d, exist_ok=True)
        save(rgb, os.path.join(d, name + "_Color.jpg"))
        print("[tex] %-13s from %-13s %d px  mean %s" % (name, r["src"], size,
              tuple(int(v) for v in np.clip(rgb, 0, 1).reshape(-1, 3).mean(axis=0) * 255)))


main()
