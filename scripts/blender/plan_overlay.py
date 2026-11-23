"""
Plan overlay check: an orthographic top view of the model at plan-pixel scale, blended over the plan image.
Every misplaced wall, window or door shows at once (0.6 s), before any camera matching against photos.

  blender -b model.blend --python-exit-code 1 --python scripts/blender/plan_overlay.py -- \
      --plan sources/floorplan.png --px-per-m 54.72 --origin 221 953 --out overlay.png

--px-per-m   plan pixels per metre; --origin   plan pixel of the model origin (x right, y down in the image,
model +y = up in the image), as in the build's PX(). The camera cuts the model at --cut metres (default 1.0) like a
plan section, so door and full-height window openings show as gaps; flat slabs (floors, ground) are hidden. The model is drawn half transparent in its viewport
colours; the plan shows through. Needs ffmpeg for the blend (without it, only the top view is written).
"""
import os
import shutil
import subprocess
import sys

import bpy

A = sys.argv[sys.argv.index("--") + 1:]


def arg(name, n=1):
    i = A.index(name)
    return A[i + 1] if n == 1 else A[i + 1:i + 1 + n]


plan = os.path.abspath(arg("--plan"))
S = float(arg("--px-per-m"))
OX, OY = map(float, arg("--origin", 2))
out = os.path.abspath(arg("--out"))
cut = float(arg("--cut")) if "--cut" in A else 1.0
img = bpy.data.images.load(plan)
W, H = img.size

for ob in bpy.data.objects:
    if ob.type != "MESH":
        continue
    zs = [(ob.matrix_world @ v.co).z for v in ob.data.vertices] if ob.data.vertices else [0.0]
    if max(zs) - min(zs) < 0.15 or max(zs) < 0.0:
        ob.hide_render = True

sc = bpy.context.scene
cam = bpy.data.objects.new("Plan overlay camera", bpy.data.cameras.new("Plan overlay camera"))
sc.collection.objects.link(cam)
cam.data.type = "ORTHO"
cam.data.ortho_scale = max(W, H) / S
cam.data.clip_start = 0.001
cam.data.clip_end = 100
cam.location = ((W / 2 - OX) / S, (OY - H / 2) / S, cut)
cam.rotation_euler = (0, 0, 0)
sc.camera = cam
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = W, H, 100
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "FLAT"
sc.display.shading.color_type = "MATERIAL"
sc.render.film_transparent = True
top = out[:-4] + "_top.png"
sc.render.filepath = top
bpy.ops.render.render(write_still=True)
if shutil.which("ffmpeg"):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", plan, "-i", top, "-filter_complex",
                    "[1]format=rgba,colorchannelmixer=aa=0.55[o];[0][o]overlay", out], check=True)
    print("[overlay] wrote", out)
else:
    print("[overlay] no ffmpeg: top view only", top)
