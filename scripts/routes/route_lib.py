"""
Camera routes for recorded walkthroughs and drone fly-ins (format: docs/00-interfaces.md, route.txt).

A route is a list of keys (t, eye, look-at) in model metres plus events (doors, lamps, stills). The Unreal
recorder (UWalkRecorderComponent), the floor-picker page and the Blender check all evaluate the same cubic
Hermite curve, so a pose computed here is the pose in the video frame.

    from route_lib import Route
    r = Route(eye_height=1.6)
    r.step(0.0, r.at(2.6, -1.9, 0), (3.2, 4.0, 1.6))     # seconds since the previous key, eye, look-at
    r.door("open", (3.2, -0.1, 0.0), 0.5)                 # at the time of the key before it
    r.step(2.5, r.at(2.6, -1.4, 0), (3.2, 4.0, 1.5))
    r.hold(1.0)                                           # stand still (two equal keys = ease out and in)
    r.write("route.txt")

Check it in Blender (passes through walls, closer than 0.18 m to anything):
    blender -b model.blend --python make_walk_route.py -- --check

Rules of thumb for walks that look filmed, not gamey:
- Eye 1.45-1.6 m. Real-estate video sits lower (1.2-1.45 m) than a person's eye.
- 0.6-0.8 m/s walking; turns of at most ~30 degrees per second; look-at points 3-6 m ahead, slightly down.
- Look into small rooms (bathroom, WC) from the doorway instead of walking in: a door that swings into a narrow
  hall blocks the way. Open it, step into the doorway, look in, step back, close it.
- Pause 1-2 s at each room's best view: the page or editor can cut there.
- Stairs: put keys on each landing and compute the eye height from the stair (on_stair()).
"""

import math
import os
import sys


class Route:
    def __init__(self, eye_height=1.6, floor_height=3.0):
        self.eye = eye_height
        self.fh = floor_height
        self.keys = []          # (t, eye, look)
        self.doors = []         # (t, (x, y, z), radius, open)
        self.lamps = []         # (t, (x, y, z), level)
        self.stills = []        # (t, path_trace_s, hour, ev, white)
        self.t = 0.0

    # positions -----------------------------------------------------------
    def at(self, x, y, floor=0, eye=None):
        """Eye position on a floor (index), eye height above its floor."""
        return (x, y, floor * self.fh + (self.eye if eye is None else eye))

    def on_stair(self, x, y, floor, y0, y1, risers, eye=None):
        """Eye on a straight flight rising along +y from y0 (first riser) to y1 (last riser) on `floor`."""
        rise = self.fh / risers
        going = (y1 - y0) / (risers - 1)
        steps = min(risers, max(0.0, (y - y0) / going + 1))
        return (x, y, floor * self.fh + steps * rise + (self.eye if eye is None else eye))

    # building ------------------------------------------------------------
    def step(self, dt, eye, look):
        self.t += dt
        self.keys.append((self.t, tuple(eye), tuple(look)))

    def hold(self, seconds):
        """Stay on the last pose. The equal keys give zero speed at both ends of the hold."""
        t, e, l = self.keys[-1]
        self.step(seconds, e, l)

    def door(self, state, at, radius=0.5, t=None):
        """Open or close every door whose hinge is within `radius` (xy) of `at` (x, y, z: the hinge height or
        floor level; the recorder matches doors within 1.5 m in z). t=None: at the current time; t<0: before the
        warm-up (the start state)."""
        self.doors.append((self.t if t is None else t, tuple(at), radius, state == "open"))

    def lamps_only(self, at, level=1.0):
        """Only the room light nearest to `at` on (windowless rooms)."""
        self.lamps.append((self.t, tuple(at), level))

    def still(self, t=None, path_trace_s=0.0, hour=None, ev=None, white=None):
        """Stills mode: a picture at walk time t (Lumen, or path traced for path_trace_s seconds)."""
        self.stills.append((self.t if t is None else t, path_trace_s, hour, ev, white))

    def snap(self, fps):
        """Put every key on a whole frame, so no frame falls inside a jump."""
        self.keys = [(round(t * fps) / fps, e, l) for t, e, l in self.keys]
        self.t = self.keys[-1][0]

    # output --------------------------------------------------------------
    def lines(self):
        out = ["# camera route, written by route_lib.py (model metres)"]
        out += ["key %.4f %.3f %.3f %.3f %.3f %.3f %.3f" % ((t,) + e + l) for t, e, l in self.keys]
        out += ["door %.3f %.3f %.3f %.3f %.2f %s" % ((t,) + p + (r, "open" if o else "close")) for t, p, r, o in self.doors]
        out += ["lamps %.3f %.3f %.3f %.3f %.2f" % ((t,) + p + (lv,)) for t, p, lv in self.lamps]
        for t, pt, hour, ev, white in self.stills:
            s = "still %.3f %.1f" % (t, pt)
            if hour is not None:
                s += " %.2f" % hour
                if ev is not None and white is not None:
                    s += " %.2f %.0f" % (ev, white)
            out.append(s)
        return out

    def write(self, path):
        with open(path, "w") as f:
            f.write("\n".join(self.lines()) + "\n")
        print("wrote %s: %d keys, %.1f s" % (path, len(self.keys), self.keys[-1][0]))

    def pose(self, t):
        return hermite(self.keys, t, 1), hermite(self.keys, t, 2)


def read_route(path):
    """Keys of a route.txt as [(t, eye, look)]."""
    keys = []
    for line in open(path):
        f = line.split()
        if len(f) == 8 and f[0] == "key":
            v = [float(x) for x in f[1:]]
            keys.append((v[0], tuple(v[1:4]), tuple(v[4:7])))
    return keys


def hermite(keys, t, idx):
    """The curve of the recorder (idx 1: eye, 2: look-at). Tangent (P[j+1]-P[j-1])/(t[j+1]-t[j-1]); zero at the
    ends and at repeated keys."""
    n = len(keys)
    P = lambda i: keys[i][idx]
    if t <= keys[0][0]:
        return P(0)
    if t >= keys[-1][0]:
        return P(n - 1)
    i = 0
    while i < n - 2 and keys[i + 1][0] <= t:
        i += 1

    def same(a, b):
        return max(abs(x - y) for x, y in zip(a, b)) <= 1e-4

    def tan(j):
        if j in (0, n - 1) or same(P(j), P(j - 1)) or same(P(j + 1), P(j)):
            return (0.0, 0.0, 0.0)
        dt = keys[j + 1][0] - keys[j - 1][0]
        return tuple((a - b) / dt for a, b in zip(P(j + 1), P(j - 1)))
    h = keys[i + 1][0] - keys[i][0]
    s = (t - keys[i][0]) / h if h > 0 else 1.0
    s2, s3 = s * s, s * s * s
    m0, m1 = tan(i), tan(i + 1)
    return tuple(p0 * (2 * s3 - 3 * s2 + 1) + a * h * (s3 - 2 * s2 + s) + p1 * (-2 * s3 + 3 * s2) + b * h * (s3 - s2)
                 for p0, a, p1, b in zip(P(i), m0, P(i + 1), m1))


def speeds(keys, fps=24):
    """Max eye speed (m/s) and turn rate (deg/s) per segment: catch jerky spots before recording."""
    out = []
    prev = None
    for f in range(int(keys[-1][0] * fps) + 1):
        t = f / fps
        e, l = hermite(keys, t, 1), hermite(keys, t, 2)
        yaw = math.degrees(math.atan2(l[1] - e[1], l[0] - e[0]))
        if prev:
            v = math.dist(e, prev[0]) * fps
            w = abs((yaw - prev[1] + 180) % 360 - 180) * fps
            out.append((t, v, w))
        prev = (e, yaw)
    return out


def check_in_blender(keys, fps=24, clearance=0.18, frames=None):
    """Ray-cast the eye path against the evaluated scene: anything it passes through, and anything closer than
    `clearance` in the six axis directions. Hits at doors you open on the way are expected (the leaf is closed
    in the .blend)."""
    import bpy
    from mathutils import Vector
    sc = bpy.context.scene
    dg = bpy.context.evaluated_depsgraph_get()
    dirs = [Vector(d) for d in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))]
    f0, f1 = frames or (0, int(keys[-1][0] * fps))
    prev, hits = None, {}
    for f in range(f0, f1 + 1):
        p = Vector(hermite(keys, f / fps, 1))
        if prev is not None and (p - prev).length > 1e-4:
            hit, loc, _, _, ob, _ = sc.ray_cast(dg, prev, (p - prev).normalized(), distance=(p - prev).length)
            if hit:
                hits.setdefault(ob.name, []).append(("through", round(f / fps, 2)))
        for d in dirs:
            hit, loc, _, _, ob, _ = sc.ray_cast(dg, p, d, distance=clearance)
            if hit:
                hits.setdefault(ob.name, []).append(("near", round(f / fps, 2)))
                break
        prev = p
    for name, h in hits.items():
        print("ROUTE %-40s %4d frames, first %s, last %s" % (name, len(h), h[0], h[-1]))
    print("ROUTE problems: %d objects" % len(hits))
    return hits


def view_blocked(eye, targets):
    """Share of target points (e.g. points just in front of a facade) hidden from `eye` (Blender ray casts).
    Use it to pick a drone start view that shows the whole unit."""
    import bpy
    from mathutils import Vector
    sc = bpy.context.scene
    dg = bpy.context.evaluated_depsgraph_get()
    E = Vector(eye)
    by = {}
    for q in targets:
        d = Vector(q) - E
        hit, _, _, _, ob, _ = sc.ray_cast(dg, E, d.normalized(), distance=d.length - 0.05)
        if hit:
            by[ob.name] = by.get(ob.name, 0) + 1
    blocked = sum(by.values())
    print("VIEW from %s: %d of %d points blocked" % (tuple(eye), blocked, len(targets)))
    for name, n in sorted(by.items(), key=lambda kv: -kv[1])[:12]:
        print("VIEW   %-40s %d" % (name, n))
    return blocked / max(1, len(targets))


def in_blender():
    return "bpy" in sys.modules or os.path.basename(sys.executable).lower().startswith("blender")
