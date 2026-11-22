"""
Mesh builder for architectural models: walls, slabs and joinery as boxes and extruded profiles, collected
into one Blender object per part with one material slot per material key.

Use it from a build script (it shares the script's globals):

    exec(open(os.path.join(KIT, "blender", "mesh_builder.py")).read(), globals())
    mb = MB("F1 walls", collection)
    mb.box(0, 0, 0, 4.0, 0.1, 2.7, "plaster")
    wall(mb, "x", 0.0, 4.0, 0.0, 0.1, 0.0, 2.7, [opening(1.0, 2.2, 0.6, 2.1, "window")], face_lo="plaster", face_hi="paint")
    mb.build(M)          # M: {material key: bpy material}

Why boxes: an apartment is mostly axis-aligned slabs. Boxes keep the geometry clean (no n-gons, no overlaps if you
cut the openings as below), they export well to FBX and glTF, and they unwrap well for light maps.

Rules that save time later:
- Do not let two boxes share a coplanar face (casing corners, frame corners). Coincident faces render black in
  Cycles and flicker in real time. Stop one box 1 mm short or split it.
- Cut wall openings by building the wall in pieces around them (wall() does this) instead of booleans.
- Keep one object per logical part (walls of a floor, doors, kitchen) so a change rebuilds one part and the
  exporters can tag, bevel or hide it by name.
"""

import math

import bmesh
import bpy


class MB:
    """Collects boxes and prisms, then builds one mesh object with a material slot per key."""

    def __init__(self, name, coll):
        self.name, self.coll = name, coll
        self.verts, self.faces, self.fmats = [], [], []

    def _add(self, verts, faces, mats):
        base = len(self.verts)
        self.verts.extend(verts)
        for f, m in zip(faces, mats):
            self.faces.append([i + base for i in f])
            self.fmats.append(m)

    def box(self, x0, y0, z0, x1, y1, z1, m):
        """Axis-aligned box. `m` is a material key, or a dict with keys -x +x -y +y -z +z (and 'all'),
        so one box can carry two finishes (plaster inside, cladding outside)."""
        x0, x1 = min(x0, x1), max(x0, x1)
        y0, y1 = min(y0, y1), max(y0, y1)
        z0, z1 = min(z0, z1), max(z0, z1)
        if x1 - x0 < 1e-5 or y1 - y0 < 1e-5 or z1 - z0 < 1e-5:
            return
        v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        f = {"-z": (0, 3, 2, 1), "+z": (4, 5, 6, 7), "-y": (0, 1, 5, 4),
             "+y": (2, 3, 7, 6), "-x": (3, 0, 4, 7), "+x": (1, 2, 6, 5)}
        if isinstance(m, str):
            m = {"all": m}
        keys = list(f)
        self._add(v, [f[k] for k in keys], [m.get(k, m.get("all")) for k in keys])

    def prism(self, pts, plane, c0, c1, m):
        """Extrude a 2D polygon. plane 'yz': pts are (y, z), extruded along x from c0 to c1; 'xz' and 'xy' alike.
        Use it for stair stringers, roof profiles, sloped ceilings, door casings with a profile."""
        def p3(p, c):
            a, b = p
            return {"yz": (c, a, b), "xz": (a, c, b), "xy": (a, b, c)}[plane]
        n = len(pts)
        v = [p3(p, c0) for p in pts] + [p3(p, c1) for p in pts]
        faces = [list(range(n))[::-1], list(range(n, 2 * n))]
        for i in range(n):
            j = (i + 1) % n
            faces.append([i, j, j + n, i + n])
        self._add(v, faces, [m] * len(faces))

    def quad(self, pts, m):
        """One face from 3 or more points (counter-clockwise seen from the front)."""
        self._add(list(pts), [list(range(len(pts)))], [m])

    def build(self, M, smooth=False):
        """Create the object in self.coll. M maps material keys to bpy materials. Normals are recalculated,
        because prisms from clockwise outlines face inward."""
        if not self.faces:
            return None
        me = bpy.data.meshes.new(self.name)
        me.from_pydata(self.verts, [], self.faces)
        keys = sorted({k for k in self.fmats if k is not None})
        for k in keys:
            me.materials.append(M[k])
        idx = {k: i for i, k in enumerate(keys)}
        for p, k in zip(me.polygons, self.fmats):
            p.material_index = idx.get(k, 0)
            p.use_smooth = smooth
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(self.name, me)
        self.coll.objects.link(ob)
        return ob


def opening(a, b, sill, head, kind="window"):
    """A hole in a wall: from a to b along the wall, from sill to head in height."""
    return {"a": a, "b": b, "sill": sill, "head": head, "kind": kind}


def _B(mb, axis, a0, a1, t0, t1, z0, z1, m):
    """Box in wall coordinates: 'a' along the wall, 't' across it."""
    if axis == "x":
        mb.box(a0, t0, z0, a1, t1, z1, m)
    else:
        mb.box(t0, a0, z0, t1, a1, z1, m)


def wall(mb, axis, a0, a1, t0, t1, z0, z1, openings=(), face_lo="wall", face_hi="wall", end="wall", reveal=None):
    """A straight wall along `axis` ('x' or 'y') from a0 to a1, between t0 and t1 across it, z0..z1 high.
    The wall is built in pieces around the openings, so there are no booleans and no hidden faces.
    face_lo / face_hi: material of the face at t0 / t1 (inside and outside); end: wall ends; reveal: the
    jambs, sill and head of the openings (None = like the faces)."""
    lo_key, hi_key = ("-y", "+y") if axis == "x" else ("-x", "+x")
    end_keys = ("-x", "+x") if axis == "x" else ("-y", "+y")
    rev = reveal or face_lo

    def mats(is_end_a=False, is_end_b=False, jamb_a=False, jamb_b=False, top=False, bottom=False):
        m = {lo_key: face_lo, hi_key: face_hi, "+z": end, "-z": end}
        m[end_keys[0]] = end if is_end_a else (rev if jamb_a else face_lo)
        m[end_keys[1]] = end if is_end_b else (rev if jamb_b else face_lo)
        if top:
            m["-z"] = rev           # the head of an opening (underside of the lintel)
        if bottom:
            m["+z"] = rev           # the sill
        return m

    ops = sorted((o for o in openings if o["b"] > a0 and o["a"] < a1), key=lambda o: o["a"])
    cur = a0
    for i, o in enumerate(ops):
        oa, ob = max(o["a"], a0), min(o["b"], a1)
        if oa > cur:
            _B(mb, axis, cur, oa, t0, t1, z0, z1, mats(is_end_a=(cur == a0), jamb_b=True, jamb_a=(cur != a0)))
        if o["sill"] > z0:
            _B(mb, axis, oa, ob, t0, t1, z0, o["sill"], mats(bottom=True))
        if o["head"] < z1:
            _B(mb, axis, oa, ob, t0, t1, o["head"], z1, mats(top=True))
        cur = ob
    if cur < a1:
        _B(mb, axis, cur, a1, t0, t1, z0, z1, mats(is_end_b=True, is_end_a=(cur == a0), jamb_a=(cur != a0)))


def polygon_area(pts):
    """Shoelace area of a 2D outline (m2), for labels.json."""
    return abs(sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                   for i in range(len(pts)))) / 2.0


def slab(mb, pts, z0, z1, m):
    """A floor or ceiling slab from a 2D outline (any simple polygon), z0..z1."""
    mb.prism([(x, y) for x, y in pts], "xy", z0, z1, m)


def stair(mb, x0, x1, y0, y1, z0, z1, risers, tread="tread", riser="riser", stringer=None, nosing=0.02,
          tread_t=0.04, open_risers=True):
    """A straight flight rising along +y from (y0, z0) to (y1, z1). Uses usual proportions:
    check that 2 x rise + going is between 0.60 and 0.66 m."""
    rise = (z1 - z0) / risers
    going = (y1 - y0) / (risers - 1) if risers > 1 else (y1 - y0)
    for i in range(risers - 1):
        ya, za = y0 + i * going, z0 + (i + 1) * rise
        mb.box(x0, ya - nosing, za - tread_t, x1, ya + going, za, tread)
        if not open_risers:
            mb.box(x0, ya - 0.02, za - rise, x1, ya, za - tread_t, riser)
    if stringer:
        t = 0.05
        for xs in (x0 - t, x1):
            mb.prism([(y0 - 0.1, z0), (y1, z1 - 0.15), (y1, z1 + 0.15), (y0 - 0.1, z0 + 0.3)], "yz", xs, xs + t, stringer)
    return rise, going
