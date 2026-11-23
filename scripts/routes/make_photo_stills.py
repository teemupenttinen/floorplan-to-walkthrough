"""
A stills route with one view per reference photo, for the photo-matching check (docs/04-unreal.md):

  python3 scripts/routes/make_photo_stills.py views.json route_photos.txt
  PROJECT=... QUALITY=2 FOV=90 scripts/unreal/record.sh stills route_photos.txt stills/
  python3 scripts/video/compare_sheet.py views.json <photos dir> stills/ compare/round1

views.json: a list, in the order the stills are taken:
  [{"photo": "16_kitchen.jpg", "eye": [7.4, 6.4, 1.45], "look": [2.5, 2.2, 1.0]},
   {"photo": "26_bath.jpg", "eye": [7.0, 8.75, 1.5], "look": [9.1, 8.0, 1.4], "lamps": true}, ...]
eye / look in model metres. "lamps": true turns on the room light nearest the look-at point (windowless rooms or
photos taken with the lights on). Frame each view like the photo: same side of the room, same height, about the
same field of view (90 deg for real-estate photos).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from route_lib import Route

views = json.load(open(sys.argv[1]))
r = Route()
for v in views:
    r.step(0.5 if r.keys else 0.0, tuple(v["eye"]), tuple(v["look"]))
    r.hold(0.5)
    if v.get("lamps"):
        r.lamps_only(tuple(v["look"]), 1.0)
    r.still()
    r.step(0.1, tuple(v["eye"]), tuple(v["look"]))
r.write(sys.argv[2])
