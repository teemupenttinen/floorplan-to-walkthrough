"""
Drone fly-ins for a "choose your floor" page: one route for the Unreal recorder with N flights that all start
from the same high view (the "tower" view) and each end exactly on a pose of the recorded walk, so the page can
continue along the walk frames without a cut. Also writes clips.json (frame ranges per flight).

  python3 make_flyins.py                                    -> fly_route.txt, clips.json
  blender -b model.blend --python make_flyins.py -- --check ray-cast flights and the start view

Design rules (learned the hard way):
- SETTLE seconds at the start view before each flight: auto exposure and Lumen need time after the jump back.
- Equal keys at both ends: the camera leaves and arrives with zero speed (the page cuts there).
- Keys snapped to whole frames, so no frame falls inside the jump back to the start view.
- Fly in through OPEN glass (balcony door, big window) and keep 0.5-0.7 m from pendants, railings and frames.
  Ray-cast every flight; a camera inside a mesh for one frame shows as a black flash.
- Check the start view: rays to points just in front of the facade show which hedge or roof hides it.
- The flight's last pose must equal the walk pose at walk_t: read it from the walk route, do not retype it.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from route_lib import Route, check_in_blender, read_route, hermite, view_blocked  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FPS = 24
WALK_ROUTE = os.path.join(HERE, "route.txt")             # the walk that the flights hand over to
TOWER = ((14.0, -12.0, 9.0), (2.6, 3.5, 1.5))            # start view: eye, look-at (model metres)
SETTLE, HOLD, LAST_LEG = 3.0, 1.5, 1.8                   # seconds

# Flights: (id, walk time it ends on, [(seconds since previous key, eye, look-at), ...])
FLIGHTS = [
    ("1", 2.5, [
        (2.2, (9.0, -4.0, 5.0), (5.2, 5.0, 1.8)),
        (1.6, (7.6, 3.0, 2.2), (5.2, 5.5, 1.5)),
    ]),
    ("2", 13.5, [
        (2.6, (4.0, -6.0, 3.5), (3.0, 1.0, 1.5)),
        (1.5, (3.0, -1.2, 1.6), (2.6, 2.5, 1.4)),     # through the open window glass
    ]),
]
DOOR_STATE = []      # extra 'door' lines (the walk's start state) if the flights must match it


def build():
    walk = read_route(WALK_ROUTE)
    r = Route()
    clips = []
    E0, L0 = TOWER
    for fid, walk_t, steps in FLIGHTS:
        start = r.t
        r.keys.append((r.t, E0, L0))
        r.step(SETTLE, E0, L0)                          # equal keys: wait, then leave with zero speed
        r.snap(FPS)
        fly0 = r.t
        for dt, e, l in steps:
            r.step(dt, e, l)
        we, wl = hermite(walk, walk_t, 1), hermite(walk, walk_t, 2)
        r.step(LAST_LEG, we, wl)
        r.hold(HOLD)
        r.snap(FPS)
        clips.append({"id": fid, "walk_t": walk_t, "f0": int(round(fly0 * FPS)), "f1": int(round(r.t * FPS)),
                      "settle_from": int(round(start * FPS))})
        r.t += 1.0 / FPS                                # one frame later: back at the start view
    return r, clips


if __name__ == "__main__":
    r, clips = build()
    path = os.path.join(HERE, "fly_route.txt")
    lines = r.lines() + DOOR_STATE
    open(path, "w").write("\n".join(lines) + "\n")
    json.dump({"fps": FPS, "tower": TOWER, "clips": clips}, open(os.path.join(HERE, "clips.json"), "w"), indent=1)
    print("wrote fly_route.txt (%.1f s) and clips.json (%d flights)" % (r.keys[-1][0], len(clips)))
    if "--check" in sys.argv:
        for c in clips:
            print("FLIGHT", c["id"])
            check_in_blender(r.keys, FPS, clearance=0.25, frames=(c["f0"], c["f1"]))
        # Facade sample points just outside the unit (edit for your building): x along the facade, z up.
        pts = [(x / 10, -0.6, z / 10) for x in range(0, 53, 5) for z in range(2, 30, 4)]
        view_blocked(TOWER[0], pts)
