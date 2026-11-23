# 3. Building the model in Blender

## Always headless, always from scripts

```sh
blender -b --factory-startup --python-exit-code 1 --python build_template.py -- out/model.blend
```

- `-b` runs without the UI. Never build in a session that someone has open: a long script freezes it, and another
  person or agent session may be using it.
- `--factory-startup` keeps the user's add-ons and preferences out of the build.
- `--python-exit-code 1` makes a script error fail the command. Without it, a later `--python-expr "save"` still saves
  a broken file.
- To chain scripts: `--python a.py --python b.py --python-expr "import bpy; bpy.ops.wm.save_mainfile()"`. Order
  matters. A script that deletes a collection also deletes what another script put in it, so run them in the order of
  their dependencies.

To look at or change something in the open session, use the Blender MCP add-on socket
(`scripts/blender/blender_socket.py`). It is fine for small things: one render, or selecting an object.

## Files in this kit

| File | What it does |
|---|---|
| `mesh_builder.py` | `MB` collects boxes and prisms and builds one object with a slot per material key. `wall()` cuts openings by building pieces around them, with no booleans. `slab()`, `stair()` and `polygon_area()`. |
| `materials.py` | `mat_flat`, `mat_tex` (world box-projected scans), `mat_uv`, `mat_glass` and `mat_emit`, plus `srgb()` to convert colours. These are the node layouts the exporters can read back. |
| `build_template.py` | A home from data tables: ROOMS, WALLS, WINDOWS and DOORS. It builds floors, ceilings, walls, windows, door leaves with hinge data, room lights, the sun, the spots and `labels.json`. |
| `export_manifest.py` | Exports to Unreal: FBX files plus `manifest.json` (see chapter 4). `--config` for a project's collections and glass names. |
| `plan_overlay.py` | Plan section at 1 m blended over the plan image: the first geometry check (chapter 2). |
| `snapshot_check.py` | Compares the object names, the polygon counts and the world bounds before and after a rebuild. |
| `blender_socket.py` | Runs Python in the open Blender session. |

## Build script structure

```python
SOURCES = "..."; ASSUMPTIONS = "..."          # 1. what is known and what is guessed
PX(), CEIL, DOOR_H ...                        # 2. scale and constants
ROOMS, WALLS, WINDOWS, DOORS, FINISHES        # 3. the tables
def materials(): ...                          # 4. material keys -> materials
def build_walls(c, M): ...                    # 5. one function per part, reading the tables
def build(): clear_scene(); ...; save()       # 6. everything from nothing, every time
```

A build always starts from an empty scene and makes everything. There is no state to drift from the scripts.

## Rebuild safely

```sh
blender -b model.blend --python snapshot_check.py -- save before.json
blender -b --factory-startup --python-exit-code 1 --python build.py -- model.blend
blender -b model.blend --python snapshot_check.py -- diff before.json
```

The diff lists every object that appeared, disappeared, moved or changed its polygon count. Read it before you
export. Names and counts alone missed a bed that had moved 10 m. Keep a dated backup of the `.blend` before a large
change, such as adding a whole neighbourhood.

## Cycles stills (checks and references)

- Use the AgX view transform, and a 5600 K white balance for interiors if the reference renders are neutral.
- Light portals in the window panes take most of the noise out of rooms lit only by daylight.
- Use 128 samples plus the denoiser for checks, and 16 samples for clay walks (a white material on everything) that
  you use as motion references.
- For each listing photo, make a camera that matches it, and put the photo and the render side by side.

## Typical generators worth writing once

- **Kitchen run:** carcasses, fronts and gaps from a list of module widths, plus the worktop with a real sink hole
  (a loft around the bowl, and the carcass split around it).
- **Wardrobes and shelves:** from module lists.
- **Stairs:** from risers and going (2 × rise + going between 0.60 and 0.66 m).
- **Trees:** your own L-system branches with leaf cards on a leaf-atlas texture. Use collection instances, so the
  exporters write each tree once plus transforms.
- **Cars, street furniture, signs:** lofted cross-sections, and texture sheets drawn with Pillow.
- **Grass:** Poly Haven clumps scattered with geometry nodes. The Unreal export keeps a share of them (for example
  8 %) as instanced LOD meshes.
- **People for scale:** the Human Base Meshes with the arms lowered from the A-pose, and clothes as material zones.

## Neighbourhoods from open data (optional)

1. Fetch OSM buildings, streets and trees for a box around the site (Overpass), plus the elevation model and the
   orthophoto from the national mirror.
2. Process them outside Blender, in a venv run with `python -I`, into one JSON file (footprints in model metres,
   storeys, roof type, colours) and a terrain height grid.
3. Build them in Blender as one object per 120 m cell. That cuts thousands of draw calls to a few dozen.
4. Keep the hand-built block level and fade the real terrain in from 60 m to 120 m, so the block you modelled from
   plans does not tilt.
5. Generate what is unknown (roof shapes, colours, windows) with the OSM id as the random seed. A rebuild then
   gives the same town.
