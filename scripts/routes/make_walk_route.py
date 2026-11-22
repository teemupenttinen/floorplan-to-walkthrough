"""
Example walk route for the template house (scripts/blender/build_template.py). Copy it per project.

  python3 make_walk_route.py                                  -> route.txt next to this file
  blender -b model.blend --python make_walk_route.py -- --check   also ray-cast the path against the model

Write the walk as steps: (seconds since the previous step, eye, look-at). Model metres.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from route_lib import Route, check_in_blender, speeds  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def build():
    r = Route(eye_height=1.5, floor_height=3.0)
    # Start state of the doors (t < 0: applied before the warm-up).
    r.door("close", (5.35, 5.0, 0.0), 0.5, t=-1)        # entrance
    r.door("open", (3.05, 6.0, 0.0), 0.5, t=-1)         # kitchen
    # Outside the entrance, looking at the door; it opens; walk in.
    r.step(0.0, r.at(6.6, 5.5), (5.2, 5.5, 1.4))
    r.hold(1.0)
    r.door("open", (5.35, 5.0, 0.0), 0.5)
    r.step(2.5, r.at(5.8, 5.5), (3.0, 5.6, 1.4))
    r.step(2.5, r.at(4.6, 5.6), (2.0, 5.8, 1.3))       # hall, looking into the kitchen
    r.hold(1.5)
    r.step(3.0, r.at(4.4, 4.6), (2.6, 1.0, 1.3))        # turn toward the living room door
    r.door("open", (4.0, 4.15, 0.0), 0.5)
    r.step(2.5, r.at(4.4, 3.6), (2.0, 0.5, 1.2))
    r.step(3.0, r.at(3.8, 2.4), (1.0, 0.2, 1.3))       # living room, window wall
    r.hold(1.5)
    r.step(3.5, r.at(3.4, 2.0), (0.4, 3.5, 1.3))       # pan to the back wall
    r.hold(1.0)
    return r


if __name__ == "__main__":
    r = build()
    r.write(os.path.join(HERE, "route.txt"))
    fast = [(t, v, w) for t, v, w in speeds(r.keys) if v > 1.2 or w > 45]
    if fast:
        print("WARNING: %d frames faster than 1.2 m/s or 45 deg/s, first at t %.2f" % (len(fast), fast[0][0]))
    if "--check" in sys.argv:
        check_in_blender(r.keys)
