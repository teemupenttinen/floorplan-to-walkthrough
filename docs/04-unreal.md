# 4. Unreal Engine walkthrough

The Blender model becomes a real-time Unreal level with Lumen lighting, a first-person walker, opening
doors, a real sun for any day and hour, lamps, path-traced stills and a camera recorder for videos.
Everything is built by script. You never place an actor by hand, so a model change is one command away.

> The C++ and Python here are cleaned-up, generic versions of code that ran in a real project on UE 5.x.
> They were compiled and run as they are on UE 5.8 with Xcode 27 (macOS, Apple silicon) in one test project.
> Expect small API differences on other engine versions.

## Why C++ plus Python

| Part | Language | Why |
|---|---|---|
| Scene build: textures, materials, meshes, level, lights | Python (editor scripting) | Runs headless as a commandlet. Re-runs from zero after every model change. |
| Gameplay: walker, doors, sun, recorder | C++ | Blueprint graphs cannot be written or edited from a script. C++ can be written, diffed and reviewed by an agent. |
| Spawning actors from Python | C++ helper `UWalkScripting::SpawnInWorld` | The editor scripting subsystems refuse to spawn actors inside a commandlet. |

Input actions and key mappings are also created in C++ code, so the project has no `.uasset` files that only
the editor can author.

## Files

| Path | What it does |
|---|---|
| `scripts/unreal/Walkthrough.uproject.template` | Project file with the needed plugins. Rename it to `Walkthrough.uproject`. |
| `scripts/unreal/Config/DefaultEngine.snippet.ini` | Renderer settings (Lumen HW ray tracing, VSM, TSR, path tracing), remote execution, game mode. |
| `scripts/unreal/Config/DefaultInput.snippet.ini` | Enhanced Input classes. They must be in `DefaultInput.ini`: in `DefaultEngine.ini` they are ignored and no key works. |
| `scripts/unreal/Source/` | The C++ module `Walkthrough` and its two target files. |
| `scripts/unreal/Python/import_manifest.py` | Builds everything from `export/manifest.json`. Copy it to `Content/Python/`. |
| `scripts/unreal/Python/update_running_editor.py` | Re-imports textures, materials and meshes into an open editor. |
| `scripts/unreal/remote_run.py` | Runs a Python file inside the open editor. |
| `scripts/unreal/build_and_import.sh` | The export → import → (compile) loop. |
| `scripts/unreal/record.sh` | Records a route into PNG frames, off-screen. |

## Project setup (once)

1. Create a blank C++ project named `Walkthrough` in the Epic launcher, or make the folder by hand:
   ```text
   Walkthrough/
     Walkthrough.uproject          <- Walkthrough.uproject.template
     Config/DefaultEngine.ini      <- merge DefaultEngine.snippet.ini
     Config/DefaultInput.ini       <- merge DefaultInput.snippet.ini
     Source/Walkthrough.Target.cs, WalkthroughEditor.Target.cs, Walkthrough/*   <- scripts/unreal/Source
     Content/Python/import_manifest.py, update_running_editor.py
   ```
   The module is called `Walkthrough`. If you rename it, rename the C++ module, the `/Script/Walkthrough.*`
   class paths in the Python script and the ini, and the `WALKTHROUGH_API` macro.
2. Compile once:
   ```sh
   "$UE_ROOT/Engine/Build/BatchFiles/Mac/Build.sh" WalkthroughEditor Mac Development -project=/abs/Walkthrough.uproject
   ```
   On a Mac, every new Xcode version needs its own Metal toolchain: `xcodebuild -downloadComponent MetalToolchain`.
3. Set the site on the sun controller. Open `WalkSun.h` and set the default `Latitude`, `Longitude`,
   `UtcOffset` and `ModelNorthDeg`, or set them on the "Sun controller" actor after the first import.
   City-level coordinates are enough. `ModelNorthDeg` is the direction of true north in your model, in
   degrees counter-clockwise from model +x. A map outline of the building gives it.

## The loop after every model change

```sh
BLEND=model.blend PROJECT=/abs/Walkthrough/Walkthrough.uproject scripts/unreal/build_and_import.sh
```

| Step | Command | Time (a 3-storey home with its block) |
|---|---|---|
| 1. Export | `blender -b model.blend --python-exit-code 1 --python scripts/blender/export_manifest.py` | seconds to 2 min |
| 2. Import | `UnrealEditor-Cmd Walkthrough.uproject -run=pythonscript -script=<abs>/Content/Python/import_manifest.py` | 15-90 s |
| 3. C++ (only after C++ changes) | `Build.sh WalkthroughEditor Mac Development -project=<abs>` | about 30 s |

- **Close the editor** before step 2. The editor holds the assets, and the commandlet cannot overwrite them.
- **Editor open?** Use `python3 scripts/unreal/remote_run.py <abs>/Content/Python/update_running_editor.py`.
  It re-imports textures, material parameters and meshes into the open level. New or deleted objects,
  doors, lights and instances still need the full import.
- `LEVEL_ONLY=1` rebuilds only the level from assets an earlier import made (fast, for level tweaks).
- Always pass `--python-exit-code 1` to Blender. Without it, a script error still "succeeds" and you import
  half an export.
- Project settings for the export (collection names, glass names, which groups are not bevelled) go into a config
  file: `export_manifest.py -- --out export --config export_config.py` (docs/00-interfaces.md). Put sofas, cushions,
  lamps and plants in a "Decor" collection: the bevel step marks every crease sharp and would make them faceted.

Run the game:

```sh
"$UE_ROOT/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor" /abs/Walkthrough.uproject \
    /Game/Maps/Walkthrough -game -windowed -ResX=1600 -ResY=900
```

Keys: W A S D walk, mouse looks, Shift runs, E opens the door you look at, 1-9 jump to spots, F field of
view (75° / 90°), L lamps, T and [ ] change the hour, P quality, R path trace (R again saves the still).

## How the import builds the scene

### Materials

Blender materials are not portable, so the exporter describes each one in the manifest and the import
rebuilds it from a few master materials. One material instance per Blender material.

| Manifest kind | Master | Notes |
|---|---|---|
| `tex` | `M_Textured` | Tiling image maps. The exporter writes box-projected UVs in texture tiles, so the mapping matches Cycles' Box projection. Saturation, Value, Tint and TintMix reproduce a Hue/Saturation and Mix step. |
| `uv` | `M_Textured` | Image maps on the asset's own UVs (downloaded furniture, plants). |
| `flat` | `M_Flat` | One colour, roughness, metallic, emission. |
| `glass` | `M_Glass` | Thin window glass, translucent, black base colour. |
| `leaf_tex` | `M_LeafTex` | Masked two-sided foliage with a photo atlas. |

- Procedural Blender textures (noise, wave) do not survive. Bake them to tileable images first, or use
  scanned textures from the start. Use power-of-two sizes, because other sizes get no mip maps.
- Normal maps from free scan libraries are OpenGL style. The import flips green for Unreal.
- Optional weathering: put a grey streak mask named `leak_mask.png` into the export. `M_Textured` then gets a
  `Weather` parameter (rain streaks on walls, blotches on floors, a slow variation that hides tile repeats).
  The `WEATHER` table sets it by material name.

### Meshes, doors, instances

- One FBX per object, named `SM_<name>`. **Nanite is turned off** on every mesh. Room-scale meshes are small,
  and the Nanite fallback mesh (used in some `-game` runs and on some GPUs) breaks thin parts: lamp wires,
  taps, handles, window reveals.
- Collision is **complex as simple**: the player collides with the real triangles. No collision modelling.
- **Doors** are `AWalkDoor` actors standing on the hinge. The exporter moves each leaf so its origin is the
  hinge and exports it fully open. The manifest gives `open_yaw` and `closed_yaw`. E toggles the door you
  look at; route `door` lines open and close doors during recordings.
- **Instances** (trees, grass clumps, parked cars) go to one `AWalkScatter` per prototype (a hierarchical
  instanced mesh). Grass: cull at 30-45 m and no shadows. Trees: cull at 450-600 m with shadows. Far trees
  can use a lighter copy of the prototype (fewer leaf cards, each larger).

### Lighting and exposure

| Setting | Value | Why |
|---|---|---|
| Sun | Directional light, 75 000 lux, atmosphere sun, 5600 K, source angle 0.54° | Physical units. The sky atmosphere and auto exposure then behave like a camera. |
| Sky | SkyAtmosphere + SkyLight (real-time capture) + VolumetricCloud | The sky light follows the sun when the hour changes. |
| Fog | ExponentialHeightFog, density 0.002, start 15 m | Distance haze outside, none inside the rooms. |
| Auto exposure | Histogram, low 10 %, **high 65 %**, bias +1.3, min brightness 4 | Meters the room and ignores the bright window third of the picture. The minimum keeps night rooms dark. |
| Local exposure | Highlight contrast 0.18, shadow 0.85, blurred luminance blend 0.6 | Compresses the bright window view and lifts dark corners, so room and view both read. |
| Default exposure | -1 EV (`AWalkSun::DefaultExposure`) | Closer to real-estate photographs of bright rooms. |
| Outdoor exposure | −1 EV more outdoors (`AWalkSun::OutdoorExposure`) | The interior metering ignores the brightest 35 % (windows); outside that is the sky, so facades metered alone blow out. Outdoors = a ray straight up from the camera hits nothing within 30 m; eased over 1 s. |
| Lumen quality | final gather, scene detail, lighting, reflections all 2 | Cleaner indirect light in small rooms. |
| Look | vignette 0.25, bloom 0.4, motion blur 0.2, saturation 1.1, Lumen diffuse colour boost 1.2 | Leave out saturation and colour boost if a green lawn tints white walls olive. |

Lamps:

- The import makes one soft rect light per room (from Blender's room lights), spots under downlights and
  point lights in small globe lamps. All are 3000 K, in lumens, hidden at start, tagged `CeilingLight` plus
  the room name.
- `AWalkSun::SetLamps` switches them and sets `MPC_Lights.LightsOn`, which makes lamp shades glow.
- Keep the attenuation radius short (about 4 m). Many overlapping lights overflow a cell of the forward
  light grid, which shows as bright or dark rectangles on walls. The ini also raises
  `r.Forward.MaxCulledLightsPerCell` to 64.
- `SetOnlyRoomAt` lights one room only (for a windowless bathroom in a daytime recording).

### The sun for any day and hour

`AWalkSun` uses the NOAA solar position equations with your latitude, longitude and time zone. `-WalkDay` and
`-WalkHour` (and T / [ ] in the game) set it.

**Golden-hour recipe for sales footage.** Pick the date and hour by ray-casting the sun onto the facade you
want lit (in Blender or in your head with a sun path tool). A low early-autumn evening sun that falls
almost straight onto the main facade worked well in one project; a midsummer evening sun was blocked by
neighbours. The settings that read as warm but not orange:

```sh
DAY=250 HOUR=18.5 EV=-0.6 WHITE=7300 FOV=90 scripts/unreal/record.sh fly route_fly.txt frames_fly
```

`WHITE` above 6500 reads warmer. Test grades as stills first (route `still` lines with `hour ev white`).

**Overcast recipe** (most Nordic listing photos are overcast: soft light, white sky, neutral whites). Set it on the
spawned actors in a project import wrapper (exec `import_manifest.py` with `NO_MAIN = True`, adjust, call `main()`):

| Setting | Value |
|---|---|
| Sun (`AWalkSun::SunLux` and the light) | 4000 lux, source angle 30°, `atmosphere_sun_disk_color_scale` black (no disc) |
| SkyAtmosphere | Mie scattering scale 0.02 (5× default), Mie absorption 0.0005, Rayleigh scattering scale 0.012, multi-scattering 2 |
| Clouds | hidden |
| Sky light | intensity 3 |
| Post | white balance 6000 K (`WHITE=6000` when recording), saturation 0.9, no Lumen diffuse colour boost |

## Recording frames

`UWalkRecorderComponent` (on `AWalkCharacter`) plays a route file and saves every frame as a PNG, without UI.
See `docs/05-routes-and-recording.md` for writing routes. The recorder:

- runs game time in fixed steps of `1/(fps × sub)`, so motion is smooth however slow a frame renders;
- waits `-WalkWarm` seconds first (shaders compile, Lumen and the exposure settle);
- disables movement and collision (fly-ins pass through glass), turns motion blur off;
- with `still` lines, saves one picture per line, optionally path traced for N real seconds;
- quits when done and logs `Walk: done`.

```sh
PROJECT=/abs/Walkthrough.uproject scripts/unreal/record.sh walk   route.txt  out/walk
PROJECT=/abs/Walkthrough.uproject scripts/unreal/record.sh fly    route_fly.txt out/fly      # Cinematic, sub 2
PROJECT=/abs/Walkthrough.uproject scripts/unreal/record.sh stills route_stills.txt out/stills
```

Real time is about 5 frames per second at High and slower at Cinematic with sub 2 (about 1 saved frame per
second). A 2-minute walk takes 10-25 minutes.

## Path-traced stills

- `r.PathTracing=True` in the ini, and the **NNEDenoiser** plugin. The OIDN denoiser plugin is Windows only.
- In the game, R starts the path tracer at 256 samples with the denoiser. Stand still; moving restarts it.
  R again saves `Saved/Stills/Still_<time>.png`. 1-3 minutes at 1600 × 900 on a recent laptop GPU.
- In a route, `still <t> <seconds>` path traces for that many real seconds.
- Translucent tricks that read the scene colour (frosted glass done in screen space) do not work in the path
  tracer. Give such materials a `PathTracingQualitySwitch` fallback.

## Quality presets

| Preset | Resolution | Hardware ray tracing | Use |
|---|---|---|---|
| 0 Fast | 60 % | off | Weak GPUs |
| 1 Balanced | 80 % | on | Walking around |
| 2 High | 100 % | on | Checking, walk recordings |
| 3 Cinematic | 200 % | on | Fly-in and sales recordings only |

**The quality trap.** If someone once picked "Fast" and it was saved, mirrors look blocky and shadows jagged,
and it looks like a content problem. It is not. `AWalkCharacter` applies presets for the session only and
never saves them. Judge reflections and shadows with `-WalkQuality=2` or `3`.

## Gotchas

| Symptom | Cause and fix |
|---|---|
| Thin parts broken, holes in window frames | Nanite fallback mesh. Turn Nanite off per mesh (the import does). |
| A milky veil over every window view | Light base colour on translucent glass. Use a black base colour; reflections come from specular. |
| Blotches on emissive screens or lamp shades | Emissive surfaces in Lumen. Light screens with their own rect light (picture as source texture) and keep them out of Lumen. |
| Slivers crossing the room, NaN bounds | A Blender bevel threw vertices 1e20 m away. The exporter's `safe_bevel()` checks each object against its own bounds and falls back to a thinner or no bevel. The import logs a bounds check. |
| The game crawls at 2 fps, no shots taken | The player did not spawn: `SpawnActor failed because of collision` in the log, and a fallback camera runs. Move the player start (or spot) into open floor. It looks like a GPU problem but is not. |
| Night shot still shows daylight | Lumen needs 10-20 s after a big change of hour. Hold 8 s or more before saving, or take the shot three times. |
| Nothing from `print()` in the import log | Commandlet `print()` does not reach the log. Use `unreal.log_warning`. |
| Distant textures shimmer | Non-power-of-two textures get no mips. Resize to 512, 1024, 2048… |
| Paper, leaves, curtains look like cardboard | Use the Two Sided Foliage shading model: Lumen adds the light from behind (subsurface colour). |
| C++ build fails after an Xcode update | Download the Metal toolchain again: `xcodebuild -downloadComponent MetalToolchain`. |
| Import fails with "Insufficient Storage" | The derived data cache filled the disk. Keep 30+ GB free; recorded PNG frames are large too (6 GB for a 2-minute walk). |
| `record.sh` returns at once | The launcher exits early and the game keeps running in the background. Wait for the process (the script does). Never start two runs. |
| Frames come out 1500 × 1125 instead of 1920 × 1080 | The window did not fit the screen. Record at 1600 × 900, or use `-RenderOffscreen` with a size that fits. |
| A window opens over your work during recordings | Add `-RenderOffscreen` (record.sh does). |
| `FParse::Value` cuts a value at a comma | Pass `bShouldStopOnSeparator = false` for values with commas (paths, shot lists). |
| A material instance keeps its old look after a re-import | `save_loaded_asset(mi)` skips an instance whose only change is a new parent. Save with `only_if_is_dirty=False`. |
| Grass draws grey | The material needs "Used with Instanced Static Meshes". |
| Remote execution finds no editor (Mac) | Bind the multicast to 0.0.0.0, not 127.0.0.1. |
| White walls turn olive | Green bounce light from a lawn plus a saturation boost. Remove `color_saturation` and `lumen_diffuse_color_boost` from the post settings. |
| Sky shows a blue band at the horizon | The ground ends and the atmosphere draws the bare planet. Add a dark ring of distant "hills" just inside the far clip, or extend the ground. |
| Every textured surface is a grey checker | The master material failed to compile; the game log says why (`Sampler type is Masks, should be Color` was a roughness sampler holding a colour texture; fixed in `import_manifest.py`). Search the game log for `Failed to compile Material`. |
| No key works; the log says "Set the Enhanced Input component class" | The input settings are in `DefaultEngine.ini`. Move them to `DefaultInput.ini`. |
| C++ fails with `-Wunreachable-code-loop-increment` | Newer clang (Xcode 27) rejects `for (TActorIterator<T> It(...); It; ++It) { ...; break; }`. Use `if (TActorIterator<T> It(GetWorld()); It)`. |
| Where is the game log? | On a Mac `~/Library/Logs/<Project>/<Project>.log`, not `Saved/Logs` (record.sh appends it to its own log). |
| Interior and exterior grade differently | Textures graded against the photos for the browser read too yellow under Unreal's tone map. Check textures in Unreal stills, not only in the browser. |

## Checking without looking

Screenshot runs open windows and use the GPU. Prefer checks by script:

- the import log (`[walkthrough]` lines, the bounds check, missing material slots);
- the game log for `SpawnActor failed`;
- a ray-cast of every route in Blender before recording (`docs/05-routes-and-recording.md`).

Render a still only when a script cannot find a suspected fault, and say what was not checked by eye.

## The photo-matching loop

The one check by eye that pays for itself: one still per reference photo, the photo and the still side by side.

```sh
python3 scripts/routes/make_photo_stills.py views.json route_photos.txt      # views: photo, eye, look-at, lamps
PROJECT=<abs>/Walkthrough.uproject QUALITY=2 FOV=90 WARM=15 scripts/unreal/record.sh stills route_photos.txt stills
python3 scripts/video/compare_sheet.py views.json <photos dir> stills compare/round1
```

With the export and import in the same script, a round takes about 60 s (8 views, UE 5.8, M4 Pro). Fix one thing per
round, in this order: missing materials (checker), exposure, colour cast, texture scale, missing parts. Turn the room
light on (`"lamps": true`) for photos taken with the lights on.
