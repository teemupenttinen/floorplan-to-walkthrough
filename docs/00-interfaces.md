# Shared formats

Every script in this kit talks to the others through a few plain files. If you change one of these formats,
change every reader and writer listed under it.

## Coordinates

- **Model space:** metres, z up, right-handed (Blender). Pick one origin and keep it in every script and file. A good
  origin is an inner wall corner on the ground floor, with the finished floor at z = 0.
- **Unreal:** centimetres, left-handed. A model point (x, y, z) becomes Unreal (100 x, -100 y, 100 z).
  A turn of θ radians about z in Blender becomes Unreal yaw `-degrees(θ)`.
- **three.js / glTF:** metres, y up. A model point (x, y, z) becomes three.js (x, z, -y). The Blender glTF exporter does
  this conversion when "+Y up" is on.

## `manifest.json` (Blender → Unreal)

Written by `scripts/blender/export_manifest.py`. Read by `scripts/unreal/Python/import_manifest.py`. The web bake
(`scripts/web/bake_lightmaps.py`) reuses `describe()` and `box_uvs()` from the exporter.

```jsonc
{
  "units": "metres, z up; Unreal = (100 x, -100 y, 100 z)",
  "materials": {
    "<blender material name>": {
      "kind": "tex | uv | flat | glass | leaf_tex",
      // tex:  tiling image maps on box-projected UVs (UV 0 is in texture tiles; "size" is the tile size in metres)
      // uv:   image maps on the mesh's own UVs (downloaded assets)
      // flat: one colour
      // glass: thin window glass ("tint")
      // leaf_tex: masked two-sided foliage ("color_tex", "mask_tex")
      "color": [r, g, b],            // linear, for flat
      "color_tex": "file.jpg",       // file names in export/tex/
      "rough": 0.5, "rough_tex": "file.jpg",
      "metal": 0.0,
      "normal_tex": "file.jpg", "normal": 1.0,   // OpenGL normal maps (green up)
      "size": [sx, sy, sz],          // tex only: tile size in metres
      "saturation": 1.0, "value": 1.0,           // optional Hue/Saturation step
      "tint": [r, g, b], "tint_mix": 0.0,         // optional colour mix
      "emit": [r, g, b],             // emission colour x strength
      "masked": true                 // alpha cut-out
    }
  },
  "meshes": [ { "file": "SM_name", "name": "source object", "group": "f1", "materials": ["..."], "tris": 1234,
                "tags": ["optional actor tags"] } ],
  "doors":  [ { "file": "SM_door_name", "name": "...", "materials": ["..."], "hinge": [x, y, z],
                "open_yaw": 0.0, "closed_yaw": 90.0 } ],      // Unreal yaw degrees; the mesh origin is the hinge
  "protos": { "<proto name>": { "file": "SM_proto", "materials": ["..."] } },
  "instances": [ { "proto": "<proto name>", "loc": [x, y, z], "yaw": 0.0, "scale": [1, 1, 1] } ],   // yaw in model degrees (CCW)
  "lights": [ { "kind": "rect | spot | point", "name": "Living room", "loc": [x, y, z],
                "size": [sx, sy], "radius": 0.1, "lumens": 1500 } ],
  "sun": { "to_sun": [x, y, z], "lux": 75000 },
  "player_start": { "loc": [x, y, z], "yaw": 0.0 },          // model metres, eye on the floor; yaw in model degrees
  "spots": [ { "name": "Hall", "loc": [x, y, z], "yaw": 0.0 } ]  // teleport points for keys 1..9
}
```

Mesh files are `export/meshes/<file>.fbx`, textures `export/tex/<name>`. FBX files carry the `SM_` prefix, because the
FBX import names materials after their slots.

## `route.txt` (camera paths → Unreal recorder)

Written by `scripts/routes/route_lib.py`. Read by `UWalkRecorderComponent` in the Unreal C++ module, by the
floor picker page (through `build_picker_data.py`) and by the Blender ray-cast check. All positions in model metres.

```text
# comment
key   <t s> <eye x y z> <look-at x y z>          camera key; the path is a cubic Hermite curve through the keys
door  <t s> <x y z> <radius m> open|close         every door whose hinge is within radius (xy) and 1.5 m (z); t < 0 = before warm-up
still <t s> <path-trace s> [hour [ev white]]      stills mode: one picture per line instead of a video
lamps <t s> <x y z> <level 0..1>                  only the room light nearest to x y z on, at level
```

Curve rule, the same in C++, Python and JavaScript: cubic Hermite through the keys, tangent at key j =
(P[j+1] - P[j-1]) / (t[j+1] - t[j-1]), except zero at the first and last key and wherever two neighbouring keys are equal.
Two equal keys therefore make the camera stop and start with zero speed (ease in and out).

## `clips.json` (fly-ins)

Written by `scripts/routes/make_flyins.py`. Read by `scripts/video/make_fly_clips.sh` and `build_picker_data.py`.

```json
{ "fps": 24, "tower": [[ex, ey, ez], [lx, ly, lz]],
  "clips": [ { "id": "1", "f0": 72, "f1": 242, "walk_t": 3.0, "settle_from": 0 } ] }
```

`f0..f1` are frame numbers in the recorded fly route. `walk_t` is the walk time the flight ends on, so the page can hand
over to the walk frames without a cut.

## `labels.json` (room names, sizes, anchors)

Written by your build or by hand. Read by the floor picker and the viewer's size overlay.

```json
{ "rooms": [ { "name": "Living room", "floor": 1, "at": [x, y, z], "size": "4.2 × 5.1 m · 21.4 m²" } ] }
```

## Recorder command line (Unreal)

```text
-WalkOut=<dir>  -WalkRoute=<route.txt>  [-WalkFps=24] [-WalkFov=84] [-WalkWarm=20] [-WalkSub=1]
[-WalkHour=15] [-WalkDay=172] [-WalkEv=0] [-WalkWhite=6500] [-WalkQuality=3]
```

Frames are saved as `<dir>/frame_00000.png`; stills as `<dir>/still_<t*100>.png`.
