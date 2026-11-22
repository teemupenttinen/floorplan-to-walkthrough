"""
Template: build a home from data tables. Copy this file per project and change the TABLES, not the code.

Run headless (never in a Blender session someone has open):
  blender -b --factory-startup --python-exit-code 1 --python build_template.py -- out/model.blend

Without --python-exit-code 1 a script error still lets later steps save a broken file.

Coordinates: metres, z up, origin at an inner wall corner of the ground floor, finished floor at z = 0.
If you trace a plan image, keep plan pixels in the tables and convert with PX() (scale from a dimension line or
from the plan's scale bar; check it against two room areas). Write down in SOURCES which number came from where
and in ASSUMPTIONS what you guessed. The user can then correct an assumption without breaking a sourced fact.

What it makes:
- floors (one slab per room, room-specific floor material), ceilings, walls with openings cut in pieces
- windows (frame + glass) and doors (one object per leaf, with a "door" property for the exporters)
- an area light per room (0.6 x the room) for night views and the Unreal L key
- empties "Start" and "Spot <name>" (player start and teleport points)
- labels.json next to the .blend (room names, centres, sizes) for the viewers
"""

import json
import math
import os
import sys

import bpy
from mathutils import Vector

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))      # scripts/
exec(open(os.path.join(KIT, "blender", "mesh_builder.py")).read(), globals())
exec(open(os.path.join(KIT, "blender", "materials.py")).read(), globals())

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT_FILE = os.path.abspath(ARGS[0] if ARGS else "model.blend")
TEX_DIR = os.environ.get("TEX_DIR", os.path.join(os.path.dirname(OUT_FILE), "textures"))

# ---------------------------------------------------------------------------
# Sources and assumptions (keep these honest: they are what the user reviews)

SOURCES = """
- Floor plan 1:50 (plan.pdf): wall positions and openings.
- Materials sheet: floors, wall finish.
- Listing photos 1-8: window heights, kitchen layout (camera-matched views in render_views.py).
"""
ASSUMPTIONS = """
- Ceiling 2.60 m, exterior walls 0.30 m, partitions 0.10 m.
- Window sills 0.60 m, heads 2.20 m where no photo shows them.
"""

PLAN_PX_PER_M = 100.0           # example: the plan's 5 m scale bar is 500 px long
PLAN_ORIGIN = (800, 1200)       # plan pixel of the model origin (inner corner)


def PX(x_px, y_px):
    """Plan pixel -> model metres (image y runs down, model y up)."""
    return ((x_px - PLAN_ORIGIN[0]) / PLAN_PX_PER_M, (PLAN_ORIGIN[1] - y_px) / PLAN_PX_PER_M)


CEIL = 2.60
WALL_TOP = 2.95                  # exterior walls up to the roof structure
DOOR_H = 2.10
FLOOR_T = 0.03                   # floor finish thickness above z = 0

# ---------------------------------------------------------------------------
# Tables

# Rooms: name -> (outline (x, y) in metres, floor material key, floor index)
ROOMS = {
    "Living room": ([(0, 0), (5.2, 0), (5.2, 4.1), (0, 4.1)], "oak", 0),
    "Kitchen": ([(0, 4.2), (3.0, 4.2), (3.0, 7.0), (0, 7.0)], "oak", 0),
    "Hall": ([(3.1, 4.2), (5.2, 4.2), (5.2, 7.0), (3.1, 7.0)], "tile", 0),
}

# Walls: (axis, a0, a1, t0, t1, exterior). axis 'x': the wall runs along x from a0 to a1, between y = t0 and t1.
WALLS = [
    ("x", -0.30, 5.50, -0.30, 0.00, True),      # south
    ("x", -0.30, 5.50, 7.00, 7.30, True),       # north
    ("y", -0.30, 7.30, -0.30, 0.00, True),      # west
    ("y", -0.30, 7.30, 5.20, 5.50, True),       # east
    ("x", 0.00, 5.20, 4.10, 4.20, False),       # living / kitchen + hall
    ("y", 4.20, 7.00, 3.00, 3.10, False),       # kitchen / hall
]

# Windows: (axis, wall t0, a, b, sill, head)
WINDOWS = [
    ("x", -0.30, 0.8, 2.6, 0.60, 2.30),
    ("x", -0.30, 3.2, 4.6, 0.60, 2.30),
    ("y", -0.30, 5.0, 6.2, 0.90, 2.20),
]

# Doors: name -> (axis, wall t0, a, b, hinge end 'a'|'b', swing side +1 (toward t1) | -1, exterior)
DOORS = {
    "Entrance door": ("y", 5.20, 5.0, 6.0, "a", -1, True),
    "Kitchen door": ("y", 3.00, 5.2, 6.0, "b", 1, False),
    "Living door": ("x", 4.10, 4.0, 4.85, "a", -1, False),
}

SPOTS = {"Hall": ((4.2, 5.6, 0.0), 180.0), "Living room": ((2.6, 1.0, 0.0), 90.0), "Kitchen": ((1.5, 5.5, 0.0), 0.0)}
START = ((4.9, 5.5, 0.0), 180.0)      # player start: position on the floor, yaw in degrees (model, CCW from +x)


def materials():
    """Material keys used by the tables. Replace the flat colours with mat_tex() scans when you have them."""
    M = {
        "wall": mat_flat("Wall paint", "#EEEBE4", rough=0.85),
        "clad": mat_flat("Facade boards", "#3A3530", rough=0.8),
        "ceiling": mat_flat("Ceiling paint", "#F4F2EE", rough=0.9),
        "oak": mat_flat("Oak floor", "#B89068", rough=0.45),
        "tile": mat_flat("Hall tile", "#8E8A84", rough=0.4),
        "frame": mat_flat("Window frame", "#1C1C1C", rough=0.5),
        "door": mat_flat("Door white", "#F0EEEA", rough=0.5),
        "glass": mat_glass("Glass"),
        "trim": mat_flat("Trim white", "#F3F1EC", rough=0.5),
    }
    return M


# ---------------------------------------------------------------------------
# Builders

def openings_in(axis, t0, a0, a1):
    def near(p, q):
        return abs(p - q) < 1e-4
    out = []
    for w in WINDOWS:
        if w[0] == axis and near(w[1], t0) and a0 - 1e-4 <= w[2] and w[3] <= a1 + 1e-4:
            out.append(opening(w[2], w[3], w[4], w[5], "window"))
    for d in DOORS.values():
        if d[0] == axis and near(d[1], t0) and a0 - 1e-4 <= d[2] and d[3] <= a1 + 1e-4:
            out.append(opening(d[2], d[3], 0.0, DOOR_H, "door"))
    return out


def build_walls(c, M):
    mb = MB("Walls", c)
    for axis, a0, a1, t0, t1, ext in WALLS:
        ops = openings_in(axis, t0, a0, a1)
        if ext:
            # Which face is outside: the one away from the rooms' bounding box centre.
            cx = sum(p[0] for r in ROOMS.values() for p in r[0]) / sum(len(r[0]) for r in ROOMS.values())
            cy = sum(p[1] for r in ROOMS.values() for p in r[0]) / sum(len(r[0]) for r in ROOMS.values())
            centre_t = cy if axis == "x" else cx
            lo, hi = ("clad", "wall") if centre_t > t1 else ("wall", "clad")
            wall(mb, axis, a0, a1, t0, t1, -0.05, WALL_TOP, ops, face_lo=lo, face_hi=hi, end="clad", reveal="trim")
        else:
            wall(mb, axis, a0, a1, t0, t1, 0.0, CEIL, ops, face_lo="wall", face_hi="wall", end="wall", reveal="trim")
    mb.build(M)


def build_floors_ceilings(c, M):
    mb = MB("Floors", c)
    ceil = MB("Ceilings", c)
    for name, (pts, mat, floor) in ROOMS.items():
        slab(mb, pts, -0.05, 0.0, mat)
        slab(ceil, pts, CEIL, CEIL + 0.05, "ceiling")
    mb.build(M)
    ceil.build(M)


def build_windows(c, M):
    mb = MB("Windows", c)
    fw, depth = 0.06, 0.08
    for axis, t0, a, b, sill, head in WINDOWS:
        t1 = next(w[4] for w in WALLS if w[0] == axis and abs(w[3] - t0) < 1e-4)
        tm = (t0 + t1) / 2
        q0, q1 = tm - depth / 2, tm + depth / 2

        def B(a0, a1, z0, z1, m, s0=q0, s1=q1):
            if axis == "x":
                mb.box(a0, s0, z0, a1, s1, z1, m)
            else:
                mb.box(s0, a0, z0, s1, a1, z1, m)
        B(a, a + fw, sill, head, "frame")
        B(b - fw, b, sill, head, "frame")
        B(a + fw, b - fw, sill, sill + fw, "frame")
        B(a + fw, b - fw, head - fw, head, "frame")
        B(a + fw, b - fw, sill + fw, head - fw, "glass", tm - 0.003, tm + 0.003)
    mb.build(M)


def door_open_angle(axis, hinge, side):
    """Model angle (radians, CCW about z) that opens a leaf modelled closed. See export_manifest.py."""
    s = side * (1 if hinge == "a" else -1) * (1 if axis == "x" else -1)
    return math.radians(90.0) * s


def build_doors(c, M):
    """One object per leaf, modelled CLOSED in world space. The 'door' property tells the exporters where
    the hinge is and which way it opens; Unreal and the browser turn the leaf at run time."""
    for name, (axis, t0, a, b, hinge, side, ext) in DOORS.items():
        t1 = next(w[4] for w in WALLS if w[0] == axis and abs(w[3] - t0) < 1e-4)
        thick = 0.06 if ext else 0.04
        tm = (t0 + t1) / 2 if ext else (t0 + thick / 2 if side < 0 else t1 - thick / 2)
        mb = MB(name, c)
        g = 0.005                                     # gap to the frame, so nothing is coplanar
        if axis == "x":
            mb.box(a + g, tm - thick / 2, 0.01, b - g, tm + thick / 2, DOOR_H - g, "door")
            hx, hy = (a, tm) if hinge == "a" else (b, tm)
        else:
            mb.box(tm - thick / 2, a + g, 0.01, tm + thick / 2, b - g, DOOR_H - g, "door")
            hx, hy = (tm, a) if hinge == "a" else (tm, b)
        ob = mb.build(M)
        ob["door"] = json.dumps({"hinge": [hx, hy, 0.0], "open": door_open_angle(axis, hinge, side), "closed": 0.0})


def build_lights(c):
    """A soft area light per room, 0.6 x the room, just under the ceiling. Off in daylight renders; the
    exporters use them as the room lights (Unreal L key) and the viewers use their boxes as reflection probes."""
    for name, (pts, _, floor) in ROOMS.items():
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        L = bpy.data.lights.new("Light " + name, "AREA")
        L.shape = "RECTANGLE"
        L.size, L.size_y = 0.6 * (max(xs) - min(xs)), 0.6 * (max(ys) - min(ys))
        L.energy = 60.0 * polygon_area(pts)
        L.color = (1.0, 0.82, 0.62)                   # about 3000 K
        ob = bpy.data.objects.new("Light " + name, L)
        ob.location = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, CEIL - 0.02)
        ob["room"] = name
        c.objects.link(ob)


def build_sun(c, azimuth_deg=200.0, elevation_deg=35.0, strength=4.0):
    """Sun from a direction (azimuth clockwise from model +y = "plan north", if +y is north). For a real date and
    hour, compute azimuth/elevation with a solar position formula (the Unreal WalkSun uses NOAA)."""
    sun = bpy.data.lights.new("Sun", "SUN")
    sun.energy = strength
    sun.angle = math.radians(0.53)
    ob = bpy.data.objects.new("Sun", sun)
    az, el = math.radians(azimuth_deg), math.radians(elevation_deg)
    to_sun = (math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el))
    ob.rotation_euler = (-Vector(to_sun)).to_track_quat("-Z", "Y").to_euler()
    c.objects.link(ob)


def build_markers(c):
    def empty(name, loc, yaw):
        e = bpy.data.objects.new(name, None)
        e.location = loc
        e.rotation_euler = (0, 0, math.radians(yaw))
        e.empty_display_type = "ARROWS"
        c.objects.link(e)
    empty("Start", *START)
    for name, (loc, yaw) in SPOTS.items():
        empty("Spot " + name, loc, yaw)


def write_labels():
    rooms = []
    for name, (pts, _, floor) in ROOMS.items():
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        area = polygon_area(pts)
        rooms.append({"name": name, "floor": floor, "at": [(min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, 1.2],
                      "size": "%.1f × %.1f m · %.1f m²" % (max(xs) - min(xs), max(ys) - min(ys), area)})
    path = os.path.join(os.path.dirname(OUT_FILE), "labels.json")
    json.dump({"rooms": rooms}, open(path, "w"), indent=1, ensure_ascii=False)
    print("[build] wrote", path)


def clear_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)


def collection(name):
    c = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(c)
    return c


def build():
    clear_scene()
    M = materials()
    shell = collection("Shell")
    build_floors_ceilings(shell, M)
    build_walls(shell, M)
    build_windows(collection("Windows"), M)
    build_doors(collection("Doors"), M)
    build_lights(collection("Room lights"))
    build_sun(collection("Sun"))
    build_markers(collection("Markers"))
    write_labels()
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.view_settings.view_transform = "AgX"
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=OUT_FILE)
    print("[build] saved", OUT_FILE, "objects:", len(bpy.data.objects))


build()
