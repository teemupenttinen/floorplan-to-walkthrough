"""
Photo | render pairs for the photo-matching check: one row per view, the reference photo left and the still
(from scripts/routes/make_photo_stills.py + record.sh stills) right, four rows per sheet.

  python3 scripts/video/compare_sheet.py views.json <photos dir> <stills dir> <out prefix>
  -> <out prefix>_1.jpg, _2.jpg, ...

Look for colour casts, exposure, texture scale and missing parts row by row; fix one thing per round.
Needs ffmpeg.
"""
import json
import os
import subprocess
import sys
import tempfile

views_path, photos, stills, out = sys.argv[1:5]
views = json.load(open(views_path))
shots = sorted(f for f in os.listdir(stills) if f.startswith("still_") and f.endswith(".png"))
if len(shots) != len(views):
    print("warning: %d views, %d stills" % (len(views), len(shots)))
tmp = tempfile.mkdtemp()
rows = []
for i, (v, s) in enumerate(zip(views, shots)):
    row = os.path.join(tmp, "row_%02d.png" % i)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(photos, v["photo"]), "-i", os.path.join(stills, s),
                    "-filter_complex", "[0]scale=-2:450,crop=min(iw\\,800):450[a];[a]pad=800:450:(ow-iw)/2:0[a2];"
                    "[1]scale=800:450[b];[a2][b]hstack", row], check=True)
    rows.append(row)
for k in range(0, len(rows), 4):
    part = rows[k:k + 4]
    dst = "%s_%d.jpg" % (out, k // 4 + 1)
    inputs = sum((["-i", p] for p in part), [])
    flt = "vstack=%d,scale=1400:-2" % len(part) if len(part) > 1 else "scale=1400:-2"
    subprocess.run(["ffmpeg", "-v", "error", "-y"] + inputs + ["-filter_complex", flt, dst], check=True)
    print(dst)
