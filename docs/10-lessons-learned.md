# 10. Lessons learned

Each entry is a symptom, its cause and the fix. Most of them cost hours the first time.

## Blender

| Symptom | Cause | Fix |
|---|---|---|
| A broken `.blend` was saved after a script error | `--python-expr save` ran anyway | Add `--python-exit-code 1` |
| Black patches in Cycles | Two boxes share a coplanar face | Stop one box 1 mm short, or split it |
| Colours too light and washed out | sRGB values typed into linear colour fields | Convert with `srgb()` |
| A 2:1 wood image squashed six times on the floor | `smart_project(correct_aspect=True)` on a non-square image | Use `correct_aspect=False` for material UVs, then rebake |
| Bevel throws vertices 1e20 m away, at random | A bevel modifier on mixed box meshes | `safe_bevel()`: check the bounds, fall back to 1 mm, then to no bevel. Use 2 mm or less near 12 mm parts. |
| Unbevelled creases shade soft after a bevel | Smooth shading without sharp edges | Mark every crease sharp first, and use harden normals |
| The rebuild moved something nobody touched | Another session's edits to a shared helper | Snapshot and diff every rebuild |
| A scratch script broke Pillow | A scratch file named like a standard module (`inspect.py`) | Never name scripts after standard modules. Run scripts that read downloads with `python -I`. |
| zsh `rm -f a* b*` deleted nothing | An unmatched glob aborts the whole command | Use `setopt null_glob`, or delete per pattern |
| A zsh script stops at a cleanup line (`no matches found`) | The same glob trap under `set -e`, e.g. `rm -f "$OUT"/frame_*.png` before the first run | `find "$OUT" -name 'frame_*.png' -delete` |
| Smooth furniture exported faceted | The export bevel marks every crease over 1° sharp | A "Decor" collection that is not bevelled |
| Template room lights in the daytime light map | Light objects render in the Cycles bake | The bake hides them with `LAMPS_OFF` |

## Unreal

| Symptom | Cause | Fix |
|---|---|---|
| Thin parts broken, window holes closed | The Nanite fallback mesh | Turn Nanite off for small architectural meshes |
| A milky veil over the window views | Translucent glass with a light base colour | Use a black base colour; reflections come from the specular |
| Blotches on emissive screens | Emissive surfaces in Lumen | Keep them out of Lumen, and give them their own rect light that uses the picture as its source texture |
| Blocky reflections, jagged shadows | The saved quality preset was "Fast" (60 %, no hardware RT) | Judge with an explicit quality flag, for example `-WalkQuality=2` |
| Bright or dark rectangles on walls with all lamps on | Too many overlapping lights in a light-grid cell | Shorter attenuation radii (about 4 m), and `r.Forward.MaxCulledLightsPerCell=64` |
| The game ran at 2 fps and took no shots | The player spawn failed because of collision, so a fallback camera ran | Search the log for "SpawnActor failed", and move the start |
| White walls look olive | Saturation and diffuse colour boost on green lawn bounce | Remove the boost from the post-process |
| A blue band at the horizon | The ground ends and the planet's sky atmosphere shows | Add a dark distant ring (a hazy ridge), only for Unreal |
| A day/night switch looks stale | Lumen needs 10–20 s to converge | Take the same shot three times, or wait 8 s in stills mode |
| `print()` missing from the commandlet log | stdout is not logged | Use `unreal.log_warning` |
| A material instance didn't update | `save_loaded_asset` skips an instance whose only change is a new parent | Pass `only_if_is_dirty=False` |
| Values with commas cut short | `FParse::Value` stops at separators | Pass `bShouldStopOnSeparator=false` |
| Light leaks through paper or thin panels | Lumen's surface cache does not pass light through | Use Two Sided Foliage shading, and add rect lights behind the panel driven by a light meter |
| Remote execution finds no editor on macOS | macOS doesn't deliver multicast to a socket bound to 127.0.0.1 | Bind to 0.0.0.0 |
| The DDC fails with "Insufficient Storage 507" | The disk is nearly full | Keep 30+ GB free. Delete PNG frame folders after encoding. |
| The C++ build fails after an Xcode update | The Metal toolchain is a separate download per Xcode version | `xcodebuild -downloadComponent MetalToolchain` |
| Textures without mips | The size is not a power of two | Use 512, 1024, 2048 |
| HISM instances grey | The material lacks the instanced-meshes usage flag | Set `used_with_instanced_static_meshes` |
| Every textured surface is a grey checker | The master material failed to compile (a Masks sampler holding a colour texture) | Fixed in `import_manifest.py`; read the game log for `Failed to compile Material` |
| No key works in the game | Input settings in `DefaultEngine.ini` | Move them to `DefaultInput.ini` |
| Facades blow out, interiors are right | Interior-tuned auto exposure outdoors | `AWalkSun::OutdoorExposure` (−1 EV when nothing is overhead) |
| Textures graded for the browser look yellow in Unreal | Different tone maps | Check the grade in Unreal stills (photo-matching loop) |

## Recording and video

| Symptom | Cause | Fix |
|---|---|---|
| Frames 1500 × 1125 instead of 1920 × 1080 | The window did not fit the screen | Record at 1600 × 900, or use off-screen rendering at a fixed size |
| Two recordings fought each other | The launcher returns at once, and the game runs on | Wait for the process before starting another |
| A black flash in a flight | The camera passed through a mesh for one frame | Ray-cast the route |
| Fly-in to walk hand-over jumps | The flight's last key was typed, not read from the walk route | Read the walk pose from the route at `walk_t`, and check with SSIM (> 0.95) |
| ffmpeg in a `while read` loop ate the loop's input | ffmpeg reads stdin | `-nostdin` |
| Still files overwrote each other | Names by time only, across test runs | Separate the output folders per run |

## Browser

| Symptom | Cause | Fix |
|---|---|---|
| Old model after a re-export | Browser cache | Serve with `Cache-Control: no-cache`, and fetch with `cache: 'no-cache'` |
| A light map baked black | A collapsed UV pack (thousands of tiny islands) or broken UVs, not missing light | Check the UV density, grow the atlas, use 2 px margins, and skip dense decor |
| Blocks in smooth light gradients | RDO compression on the light maps | UASTC without RDO for light maps |
| Untextured parts lost their UVs | gltfpack drops unused UVs | Use `-kv`, plus `-noq` for box UVs that span many tiles |
| A shadow from a hidden furniture set | The hidden set was visible in the bake | Hide every object of the other set during the bake |
| Soft image on a Retina screen | Pixel ratio 1 | Use up to 2×, and sharpen after TAA |
| Halos at window edges | Local exposure on a wide blur | Mostly per-pixel luminance, with only a third of the blurred value |
| A headless screenshot is black or stuck on "Loading" | Chrome `--screenshot` with WebGPU or WebGL | Drive Chrome over CDP (puppeteer-core) and wait for `window.__ready` |
| A hosted page cannot load models | The host's CSP blocks `fetch()` of `data:` and `blob:` | Embed the glTF buffers, decode base64 yourself, and use `<img>` for textures |
| Tiling textures 2-3× too large | Box UVs in tiles plus the Mapping scale exported as `KHR_texture_transform` | The bake resets the Mapping scale before the export |
| Normal maps never show | The bake set their strength to 0 and the GLB went out in the same session | The bake restores it before the export |
| Wood, sauna and white walls look pastel and grey | AgX tone mapping | `LOOK = {"tone": "neutral", "ev": 0}` in the bake config |
| Images "are JPEGs" but tools fail on them | Listing sites (e.g. a common Finnish one) serve WebP under `.jpg` | Convert with ffmpeg first |
| Every wall is white, the photos are not | One paint assumed for the whole home | Measure each wall against the ceiling in the same photo (chapter 2) |

## AI stills and videos

| Symptom | Cause | Fix |
|---|---|---|
| Rooms look bigger than they are | The model zoomed out, worst when it adds people | Name what each image edge cuts through |
| A window appeared in a bathroom | A general prompt | "This room has no window: do not add any window" |
| A dark facade came out pale | The model's prior for the building type | Describe the facade hard, and attach a real exterior image |
| Handles and pulls 1.5–2.5 times too big | The model's prior for small hardware | Retouch by hand, measured against the render |
| Wood turned yellow | Warm renders plus the model's prior | "very pale, almost white, not yellow" |
| A video copied a reference's room and furniture | Whole-room reference images | Use close-up material crops as references |
| A fly-in invented an interior | A start + end frame model | Restyle `motion.mp4`, or use a ControlNet edge video |
| The video looks like CGI | The render clip was used as a style reference | Use the render only for motion or edges |
| Black artifacts in a ControlNet video | Canny edges of sun patches in the lit render | Edges from the normal and base-colour passes |
