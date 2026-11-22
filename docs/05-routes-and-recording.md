# 5. Camera routes and recording

Every camera move (the walkthrough video, room clips, drone fly-ins) is a route file of keys. A recorder in Unreal
plays it back with a fixed time step and saves every frame. The format is in `docs/00-interfaces.md`.

## Why record frame by frame

A screen recording drops frames and stutters whenever the GPU is busy. The recorder runs the game with a fixed time
step of 1/fps (or 1/(fps × sub)), poses the camera exactly on the curve for that time, and saves the frame. However
slow a frame is to render, the motion in the video stays perfectly smooth. The same route gives the same frames
every time.

## Writing a route

```python
from route_lib import Route
r = Route(eye_height=1.5)
r.door("close", (5.35, 5.0, 0.0), 0.5, t=-1)         # start state, before the warm-up
r.step(0.0, r.at(6.6, 5.5), (5.2, 5.5, 1.4))          # t = 0: eye, look-at
r.hold(1.0)
r.door("open", (5.35, 5.0, 0.0), 0.5)                 # opens at t = 1.0
r.step(2.5, r.at(5.8, 5.5), (3.0, 5.6, 1.4))          # 2.5 s later
r.write("route.txt")
```

See `scripts/routes/make_walk_route.py` (a walk) and `scripts/routes/make_flyins.py` (fly-ins plus `clips.json`).

### Rules for walks that look filmed

| Rule | Value |
|---|---|
| Eye height | 1.45–1.6 m for a walk; 1.2–1.45 m for real-estate room clips |
| Walking speed | 0.6–0.8 m/s. `speeds()` warns above 1.2 m/s. |
| Turning | at most ~30–45°/s |
| Look-at | 3–6 m ahead, a little below the eye |
| Field of view | 84° horizontal for a walk, 90° for real-estate stills and room clips |
| Holds | 1–2 s at each room's best view. Two equal keys give an ease-out and an ease-in. |
| Small rooms | Open the door, step into the doorway, look in, step back and close it. A door that swings into a narrow hall blocks the walk. |
| Stairs | Keys at each landing; compute the eye height from the stair (`on_stair()`). |

### Room clips (real-estate style)

- 7–8 s each, eased in and out, a slow gimbal move: a short push-in, a slide of 0.5–1 m, or a pan of 20–30°.
- Start and end on framings you would use as stills. People can then pick framings in the game (for example with a
  "save this view" key that writes the camera pose) and you build the clips around them.
- For a windowless room, use a `lamps` line, so that only that room's light is on.

### Fly-ins

- Every flight starts from **one shared high view**. The page shows that view as its start image.
- Each flight ends **exactly on a pose of the walk** (read from the walk route at `walk_t`). The page then continues on
  the walk frames without a cut.
- Settle for 3 s at the start view before each flight, so the exposure and Lumen recover from the jump. Hold for
  1.5 s at the end.
- Snap the keys to whole frames, so that no frame falls inside the jump back.
- Fly in through **open** glass (a balcony door or a big window). Keep 0.5–0.7 m from pendants, railings and frames.

### Checking a route (always, before recording)

```sh
blender -b model.blend --python make_walk_route.py -- --check
```

This lists everything the eye passes through, or comes within 18 cm of (25 cm for flights). Hits on doors that the
route opens are expected, because the leaves are closed in the `.blend`. For a drone start view, `view_blocked()`
casts rays to points in front of the facade and names the hedge or roof that hides it.

## Recording in Unreal

```sh
scripts/unreal/record.sh walk  route.txt  out/frames          # see the script for modes and env overrides
```

Under the hood:

```text
UnrealEditor <project>.uproject /Game/Maps/<Map> -game -windowed -ResX=1600 -ResY=900 -RenderOffscreen
  -WalkOut=<dir> -WalkRoute=<route.txt> -WalkFps=24 -WalkFov=84 -WalkWarm=20 -WalkSub=2 -WalkQuality=3
  -WalkHour=18.5 -WalkDay=250 -WalkEv=-0.6 -WalkWhite=7300
```

- **Warm-up** (`-WalkWarm=20`): 20 s of game time at the first pose before frame 0. Shaders, Lumen and the auto
  exposure settle.
- **Sub-steps** (`-WalkSub=2`): two engine frames per saved frame. TSR and Lumen gather more history, so there is less
  noise and ghosting. Cinematic quality with sub 2 gives about 1 saved frame per second.
- **Resolution:** 1600 × 900. On a laptop screen, a 1920 × 1080 window does not fit and silently came out 1500 × 1125.
  Upscale later, or use a render target that does not depend on the window.
- **Off-screen:** `-RenderOffscreen` opens no window. The launcher returns at once and runs the game in the
  background, so wait for the process (`pgrep` on the route path) and do not start a second run.
- **Golden hour:** choose the day and the hour by ray-casting the sun onto the facade you film. Near midsummer the
  evening sun can be blocked or behind the building. In one project an early-September evening sun lit the facade
  almost head-on. Use EV −0.6 and a 7300 K white balance for a warm look that does not go orange.
- **Stills mode:** `still` lines in the route give one picture per line. Use 0 seconds for Lumen, or N seconds of path
  tracing. Each still waits 4 s of game time first (8 s after an hour change) for the doors, Lumen and the exposure.

## After recording

```sh
scripts/video/encode.sh  frames/ out/ 10            # walkthrough.mp4 + 10 s parts + first frames
scripts/video/make_frames.sh frames/ site/           # 12 fps WebP hi/lo sequences for the page
scripts/video/make_fly_clips.sh fly_frames/ clips.json site/
scripts/video/chain_tools.sh ssim fly_last.png walk_frame.png   # hand-over check, should be > 0.95
```

PNG frames are large: about 6 GB for a 140 s walk at 1600 × 900. Keep the encoded videos and delete the frame folders
once the page and the kit are built. Write down which route made which video, so you can record it again.

## Passes for AI control videos

Record the same route again with buffer visualisation, and keep each pass in its own folder:

```text
-ExecCmds="r.BufferVisualizationTarget WorldNormal,viewmode VisualizeBuffer"
-ExecCmds="r.BufferVisualizationTarget BaseColor,viewmode VisualizeBuffer"
```

Then `scripts/video/make_control.sh normal/ base/ control.mp4` makes an edge video without any lighting (chapter 8).
