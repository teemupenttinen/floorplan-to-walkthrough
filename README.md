# 3D walkthrough guide: from floor plan to Unreal, browser and photoreal video

This guide shows how to turn a floor plan and a few photos into:

- a **Blender model built from scripts**, with sourced facts kept apart from assumptions;
- a **realistic Unreal Engine walkthrough**, with Lumen, a C++ player, doors, lamps and the sun for any day and hour;
- **recorded videos**: smooth walks, real-estate room clips and drone fly-ins, recorded frame by frame;
- a **browser walkthrough** in three.js, with baked light maps, real materials, collision and the Unreal look;
- a **"choose your floor" sales page**, where drone fly-ins hand over to the walk without a cut;
- a **photoreal kit**: prompts and references for image and video models, so the footage looks real without losing
  the real layout.

Everything here is generic. Adapt the data tables and the configuration blocks to your own home or building.

## Start here

| If you want to… | Read |
|---|---|
| See the whole pipeline and the loop after a change | [docs/01-pipeline-overview.md](docs/01-pipeline-overview.md) |
| Know the shared file formats (manifest, route, clips, labels) | [docs/00-interfaces.md](docs/00-interfaces.md) |
| Turn plans and photos into numbers you can trust | [docs/02-sources-and-modeling.md](docs/02-sources-and-modeling.md) |
| Build the model in Blender | [docs/03-blender-build.md](docs/03-blender-build.md) |
| Get it into Unreal with good light | [docs/04-unreal.md](docs/04-unreal.md) |
| Record walks, room clips and fly-ins | [docs/05-routes-and-recording.md](docs/05-routes-and-recording.md) |
| Make the browser version | [docs/06-web-walkthrough.md](docs/06-web-walkthrough.md) |
| Make the floor picker with fly-ins | [docs/07-floor-picker.md](docs/07-floor-picker.md) |
| Make photoreal stills and videos with AI | [docs/08-ai-photoreal.md](docs/08-ai-photoreal.md) |
| Drive a coding agent through all of it (the prompts) | [docs/09-agent-prompts.md](docs/09-agent-prompts.md) |
| Avoid the known traps | [docs/10-lessons-learned.md](docs/10-lessons-learned.md) |

## Scripts

```text
scripts/
  blender/   mesh_builder.py  materials.py  build_template.py  export_manifest.py  snapshot_check.py  blender_socket.py
  unreal/    Python/import_manifest.py  Python/update_running_editor.py  remote_run.py  record.sh  build_and_import.sh
             Source/Walkthrough/ (C++: character, recorder, doors, sun, scatter, scripting helper)
             Config/DefaultEngine.snippet.ini  Walkthrough.uproject.template
  routes/    route_lib.py  make_walk_route.py  make_flyins.py
  video/     encode.sh  make_frames.sh  make_fly_clips.sh  chain_tools.sh  make_control.sh
  web/       bake_lightmaps.py  serve.py  viewer/index.html  floorpicker/index.html  floorpicker/build_picker_data.py
  ai/        make_kit.py  KIT_README.md  templates/*.txt  comfy_client.py  h3_job_example.py
templates/   CLAUDE.md (project instructions for a coding agent)
```

## Quick start (with the template home)

```sh
K=$PWD/scripts
# 1. Build the template home and export it for Unreal
blender -b --factory-startup --python-exit-code 1 --python $K/blender/build_template.py -- work/model.blend
blender -b work/model.blend --python-exit-code 1 --python $K/blender/export_manifest.py -- --out work/export

# 2. Unreal: create a C++ project from scripts/unreal (see docs/04), then with the editor closed:
WALK_EXPORT=$PWD/work/export UnrealEditor-Cmd <abs>/Walkthrough.uproject -run=pythonscript \
  -script=<abs>/Content/Python/import_manifest.py

# 3. A route, checked against the model, then recorded
python3 $K/routes/make_walk_route.py
blender -b work/model.blend --python $K/routes/make_walk_route.py -- --check
PROJECT=<abs>/Walkthrough.uproject $K/unreal/record.sh walk $K/routes/route.txt work/frames
$K/video/encode.sh work/frames work/video 10

# 4. Browser version
blender -b work/model.blend --python-exit-code 1 --python $K/web/bake_lightmaps.py
python3 $K/web/serve.py <web output dir> 8768
```

## Tools

| Tool | Used for |
|---|---|
| Blender 4.2+ (tested with 5.x) | The model, Cycles stills, light-map bakes, route checks |
| Unreal Engine 5.4+ (tested with 5.8, macOS) | The real-time walkthrough and the recordings. The C++ in this kit has not been compiled as is: expect small fixes per engine version. |
| ffmpeg | Encoding, frame sequences, edge control videos, SSIM checks |
| basisu, gltfpack (optional) | KTX2 textures and meshopt-compressed GLB files for the browser |
| Chrome + puppeteer-core (optional) | Headless checks of the web pages |
| ComfyUI on a rented GPU (optional) | Open-model photoreal video with ControlNet |
| Image and video model hosts | Photoreal stills and clips, run by a person from the kit |

## Principles

1. **Scripts, not hand edits.** A model rebuilds from nothing in seconds. Every tool downstream reads what the
   scripts write.
2. **Facts and guesses apart.** Every number is either sourced or listed as an assumption.
3. **One curve for every camera.** The recorder, the page and the checks evaluate the same Hermite curve. A pose on
   the page is the pose in the video.
4. **Check without looking.** Ray-cast the routes, diff the snapshots, check the bounds and read the logs. Render only
   when nothing else can find a fault.
5. **Real geometry, AI only for the look.** AI models restyle what was rendered. They are not trusted with layout.
6. **People run the paid steps.** The kit prepares everything; a person generates and reviews.

## Licences of assets mentioned

ambientCG and Poly Haven assets are CC0. OpenStreetMap data is ODbL; credit OpenStreetMap contributors. National
open data is often CC BY 4.0, so check each dataset. Check the terms of street-level imagery before you use it.
