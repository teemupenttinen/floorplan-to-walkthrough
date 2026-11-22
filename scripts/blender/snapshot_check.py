"""
Check that a rebuild changed only what it should: snapshot every object's name, polygon count and world bounds,
rebuild, snapshot again, compare.

  blender -b model.blend --python snapshot_check.py -- save before.json
  (rebuild)
  blender -b model.blend --python snapshot_check.py -- diff before.json [--tol 0.01]

Why bounds: names and polygon counts alone miss an object that moved (a bed that moved 10 m kept both).
Several people or agent sessions editing shared build helpers is the usual cause of surprise changes: a rebuild
applies every unbuilt edit, not only yours.
"""

import json
import sys

import bpy
from mathutils import Vector

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def snapshot():
    dg = bpy.context.evaluated_depsgraph_get()
    out = {}
    for ob in bpy.data.objects:
        rec = {"type": ob.type, "hidden": bool(ob.hide_render)}
        if ob.type == "MESH":
            ev = ob.evaluated_get(dg)
            pts = [ob.matrix_world @ Vector(c) for c in ev.bound_box]
            rec["polys"] = len(ev.data.polygons)
            rec["lo"] = [round(min(p[i] for p in pts), 4) for i in range(3)]
            rec["hi"] = [round(max(p[i] for p in pts), 4) for i in range(3)]
        else:
            rec["loc"] = [round(v, 4) for v in ob.matrix_world.translation]
        out[ob.name] = rec
    return out


def diff(a, b, tol):
    added, removed = sorted(set(b) - set(a)), sorted(set(a) - set(b))
    changed = []
    for name in sorted(set(a) & set(b)):
        x, y = a[name], b[name]
        why = []
        if x.get("polys") != y.get("polys"):
            why.append("polys %s -> %s" % (x.get("polys"), y.get("polys")))
        for k in ("lo", "hi", "loc"):
            if k in x and k in y and max(abs(p - q) for p, q in zip(x[k], y[k])) > tol:
                why.append("%s %s -> %s" % (k, x[k], y[k]))
        if x["hidden"] != y["hidden"]:
            why.append("hidden %s -> %s" % (x["hidden"], y["hidden"]))
        if why:
            changed.append((name, why))
    for n in added:
        print("ADDED   ", n)
    for n in removed:
        print("REMOVED ", n)
    for n, why in changed:
        print("CHANGED ", n, "; ".join(why))
    print("SUMMARY: %d added, %d removed, %d changed, %d same" % (len(added), len(removed), len(changed),
                                                                 len(set(a) & set(b)) - len(changed)))


if ARGS[:1] == ["save"]:
    json.dump(snapshot(), open(ARGS[1], "w"), indent=0)
    print("saved", ARGS[1])
elif ARGS[:1] == ["diff"]:
    tol = float(ARGS[ARGS.index("--tol") + 1]) if "--tol" in ARGS else 0.01
    diff(json.load(open(ARGS[1])), snapshot(), tol)
else:
    print(__doc__)
