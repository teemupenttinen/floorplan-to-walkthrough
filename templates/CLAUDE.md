# Project instructions (template for a coding agent)

Copy this file to the root of a new project as `CLAUDE.md` (or your agent's equivalent), then fill in the `<...>` parts.

## What this project is

A 3D model of <the home> built from scripts in Blender, with an Unreal Engine walkthrough, recorded videos, a
browser walkthrough (three.js) and a photoreal kit. The sources are in `sources/`, and each one is listed in
`sources/SOURCES.md`.

## Rules

- Build and export headless (`blender -b --factory-startup --python-exit-code 1 ...`). Never build in the open Blender
  session. Use the MCP socket only for small looks in the open session.
- Keep the SOURCES and ASSUMPTIONS lists in every build script current. Never change a sourced number to make
  something fit. Ask me.
- Change the data tables, not the geometry code, when the plan changes.
- Before each rebuild, snapshot the object names, polygon counts and world bounds, and diff them afterwards
  (`scripts/blender/snapshot_check.py`). Report anything that changed outside the request.
- Do not run test renders or Unreal screenshot runs unless I ask, or unless no other check can find a suspected
  fault. Say what you did not check by eye.
- Never call paid image or video generation without asking. State the cost before and after.
- Close the Unreal editor before a commandlet import or a C++ build. With the editor open, use `remote_run.py`.
- Before you change a shared helper's signature, search every project that uses it.
- Do not publish private sources (owner photos, street-level photos, personal documents).

## Commands

| Step | Command |
|---|---|
| Build | `blender -b --factory-startup --python-exit-code 1 --python build.py -- model.blend` |
| Export to Unreal | `blender -b model.blend --python-exit-code 1 --python scripts/blender/export_manifest.py -- --out export` |
| Import | `UnrealEditor-Cmd <abs>/<Project>.uproject -run=pythonscript -script=<abs>/Content/Python/import_manifest.py` |
| C++ build | `<UE>/Engine/Build/BatchFiles/Mac/Build.sh <Module>Editor Mac Development -project=<abs>/<Project>.uproject` |
| Play | `UnrealEditor <abs>/<Project>.uproject /Game/Maps/<Map> -game -windowed -ResX=1600 -ResY=900` |
| Record | `PROJECT=<abs>/<Project>.uproject scripts/unreal/record.sh walk walk/route.txt walk/frames` |
| Browser | `python3 scripts/web/serve.py web 8768` |

## Facts and defaults

- Coordinates: metres, origin <...>, +x <...>, north is <deg> from +x. Unreal = (100x, −100y, 100z).
- Ceiling <...> m, floor-to-floor <...> m.
- Start state: every door closed, lamps off, <day and hour>, exposure −1 EV.
- Ports: browser walkthrough <...>, sales page <...>, headless Chrome <...>.
