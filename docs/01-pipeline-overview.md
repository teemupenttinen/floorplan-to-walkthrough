# 1. Pipeline overview

This chapter covers the whole route from a floor plan to a walkthrough, a sales page and photoreal footage.

## The idea in one paragraph

Build the home **from scripts** in Blender, with sourced facts kept apart from assumptions. Export it to **Unreal
Engine**, which gives real-time Lumen light and a walkable C++ player. Record **camera routes** frame by frame with a
fixed time step, so walks, room clips and drone fly-ins come out smooth. Bake a light-mapped copy for a **three.js**
walkthrough in the browser. Hand the recorded footage to **image and video models** as a kit, so stills and clips
become photoreal without losing the real layout. Every step can be run again. A change to the plan means a rebuild
and a re-export, not hand edits in three tools.

## Map

```text
 sources (plans, photos, material sheets, open map data)
        │  docs/02
        ▼
 Blender build scripts ──────────────► model.blend ──► Cycles stills (camera-matched to photos)
 (data tables, mesh_builder, materials)     │
        docs/03                             ├── export_manifest.py ──► export/ (FBX + manifest.json)
                                            │         │  docs/04
                                            │         ▼
                                            │   Unreal: import_manifest.py → level, C++ player,
                                            │   doors, lamps, sun ─► play / screenshots / path-traced stills
                                            │         │
                                            │         ▼  routes (route_lib.py)  docs/05
                                            │   recorder ─► frames/*.png ─► mp4, parts, WebP sequences
                                            │         │                          │
                                            │         ▼  docs/08                 ▼  docs/07
                                            │   AI kit (stills + videos)   floor picker / fly-in page
                                            │
                                            └── bake_lightmaps.py ──► web/ (GLB + light maps) ─► three.js viewer  docs/06
```

## Folder layout of a project

```text
project/
  sources/            plans, photos, material sheets (private), with a SOURCES.md listing what each one gives
  textures/           CC0 scans (ambientCG, Poly Haven) and generated tiles
  build_*.py          Blender build scripts (data tables at the top)
  model.blend         output of the build (never hand-edited)
  export/             Unreal export (meshes/, tex/, manifest.json)
  unreal/<Project>/   Unreal project (Content/Python, Source/<Module>)
  walk/               routes, recordings, encodes
  web/                browser walkthrough (GLB, light maps, viewer)
  site/               floor picker / sales page
  kit/                photoreal kit for image and video models
```

## The loop after a change

| Change | Run |
|---|---|
| A wall, a window or a room size | Build script → `export_manifest.py` → close the editor → `import_manifest.py` (commandlet) |
| A material colour | The same. With the editor open: `update_running_editor.py` through `remote_run.py`. |
| Player keys, doors, lighting logic | Build the C++ module (`Build.sh <Module>Editor ...`), with the editor closed. |
| A camera path | `make_walk_route.py` → `--check` in Blender → `record.sh` |
| The browser version | `bake_lightmaps.py -- --reuse` (it bakes only what changed) |
| The sales page | Record the walk and the fly-ins again, then `make_frames.sh`, `make_fly_clips.sh` and `build_picker_data.py` |

## Time and hardware (measured on a 14-core laptop with 48 GB, Apple GPU)

| Step | Time |
|---|---|
| Build a home from scripts | 3–30 s |
| Export to Unreal | 3–90 s, depending on the surroundings |
| Unreal import (commandlet) | 15–90 s |
| C++ build | about 25 s |
| Record a 140 s walk at 1600 × 900, quality High | about 25 min (about 5 fps of real time) |
| Cinematic quality, 2 engine frames per saved frame | about 1 saved frame per second |
| Path-traced still, 256 spp + denoise | 1–3 min |
| Light map bake for the browser, full | 35–80 min, then incremental with `--reuse` |
| AI video, 10 s segment on a 48 GB cloud GPU | about 9 min |

## What goes where

- **Unreal** is the source of truth for the look. Match the browser and the AI stills to Unreal, not the other way round.
- **Blender** is the source of truth for the geometry and the materials. Never fix geometry in Unreal: the next import overwrites it.
- **Routes** are the source of truth for every camera. The page, the recorder and the checks all evaluate the same curve.
