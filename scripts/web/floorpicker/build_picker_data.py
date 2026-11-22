"""
Write data.json for the floor picker page (index.html in this folder).

  python3 build_picker_data.py \
      --route ../routes/walk/route.txt        the route the walk frames were recorded with (key lines)
      --fly-route ../routes/fly/route.txt     the fly-in route (key lines), optional: paths for a live three.js variant
      --clips ../routes/fly/clips.json        fly-in clip ranges (scripts/routes/make_flyins.py)
      --labels labels.json                    room names, anchors and sizes
      --frames frames/lo                      the page's walk frames (make_frames.sh), counted

What the page needs:
  - the walk camera keys, so it can rebuild the camera of any walk time with the same Hermite curve as the
    recorder and pin room hotspots onto the frames
  - the rooms: anchor point (model metres) and area text from labels.json
  - the tower (start view) camera and the floor bands as 3D boxes or polygons, projected by the page
  - frame count, page frame rate, frame size and horizontal field of view of the recording

Edit ROOMS and BANDS below. Every walk time the page uses (FLOORS in index.html, walk_t in clips.json) must be
a time of the walk route.
"""

import argparse
import json
import os

FPS = 12                         # page frame rate (make_frames.sh keeps every 2nd frame of a 24 fps walk)
WIDTH, HEIGHT = 1600, 900        # recorded frame size
HFOV = 84.0                      # horizontal field of view of the walk recording (degrees)
FLY_HFOV = None                  # of the fly-in recording, if different (the start view uses it)

# Page room key -> (room name in labels.json, floor in labels.json). The page shows these as pills and hotspots.
ROOMS = {
    "living": ("Living room", 0),
    "kitchen": ("Kitchen", 0),
    "bedroom": ("Bedroom", 1),
    "study": ("Study", 1),
}

# Floor bands on the start view, in model metres. "box": [x0, y0, z0, x1, y1, z1] (the page draws the outline of
# its projection) or "poly": [[x, y, z], ...] (drawn as given). The id matches the floor number in index.html.
BANDS = [
    {"id": "1", "label": "1", "box": [0.0, 0.0, 0.0, 5.2, 7.0, 3.0]},
    {"id": "2", "label": "2", "box": [0.0, 0.0, 3.0, 5.2, 7.0, 6.0]},
]


def route_keys(path):
    keys = []
    for line in open(path):
        f = line.split()
        if len(f) == 8 and f[0] == "key":
            v = [float(x) for x in f[1:]]
            keys.append([round(v[0], 4), [round(x, 4) for x in v[1:4]], [round(x, 4) for x in v[4:7]]])
    keys.sort(key=lambda k: k[0])
    return keys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--route", required=True)
    ap.add_argument("--clips")
    ap.add_argument("--fly-route")
    ap.add_argument("--labels")
    ap.add_argument("--frames", default=os.path.join("frames", "lo"))
    ap.add_argument("--out", default="data.json")       # run it in the page folder
    a = ap.parse_args()

    keys = route_keys(a.route)
    if len(keys) < 2:
        raise SystemExit("no key lines in " + a.route)
    frames = len([f for f in os.listdir(a.frames) if f.endswith(".webp")]) if os.path.isdir(a.frames) else 0

    rooms = {}
    if a.labels and os.path.exists(a.labels):
        labels = json.load(open(a.labels))["rooms"]
        for key, (name, floor) in ROOMS.items():
            r = next((r for r in labels if r["name"] == name and r.get("floor") == floor), None)
            if r is None:
                print("WARNING: room %r (floor %s) not in labels.json" % (name, floor))
                continue
            area = r.get("size", "").split("·")[-1].strip() if "·" in r.get("size", "") else ""
            rooms[key] = {"at": [round(v, 3) for v in r["at"]], "area": area, "label": name}

    data = {"fps": FPS, "frames": frames, "width": WIDTH, "height": HEIGHT, "hfov": HFOV,
            "keys": keys, "rooms": rooms, "bands": BANDS}

    if a.clips and os.path.exists(a.clips):
        fly = json.load(open(a.clips))
        fps = fly["fps"]
        fkeys = route_keys(a.fly_route) if a.fly_route and os.path.exists(a.fly_route) else []
        walk_times = {k[0] for k in keys}
        clips = {}
        for c in fly["clips"]:
            cid = str(c.get("id", c.get("floor")))
            if not any(abs(c["walk_t"] - t) < 1e-3 for t in walk_times):
                print("WARNING: clip %s ends on walk t %.2f, which is not a key time of the walk route" % (cid, c["walk_t"]))
            entry = {"walk_t": c["walk_t"], "frames": c["f1"] - c["f0"] + 1}
            if fkeys:
                t0, t1 = c["f0"] / fps, c["f1"] / fps
                entry["path"] = [[round(t - t0, 4), e, l] for t, e, l in fkeys if t0 - 1e-3 <= t <= t1 + 1e-3]
            clips[cid] = entry
        data["fly"] = {"tower": fly["tower"], "clips": clips, "hfov": FLY_HFOV or HFOV}

    end = keys[-1][0]
    if frames and abs((frames - 1) / FPS - end) > 0.1:
        print("WARNING: %d frames at %d fps = %.2f s, but the route ends at %.2f s (wrong route, fps or frame step?)"
              % (frames, FPS, (frames - 1) / FPS, end))
    json.dump(data, open(a.out, "w"), separators=(",", ":"))
    print("wrote %s: %d keys, %d rooms, %d frames (%.1f s), %d fly clips"
          % (a.out, len(keys), len(rooms), frames, max(0, frames - 1) / FPS, len(data.get("fly", {}).get("clips", {}))))


if __name__ == "__main__":
    main()
