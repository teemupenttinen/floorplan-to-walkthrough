# Floor picker with drone fly-ins

A sales-style page in the manner of high-end residential sites: the building from a drone, floors highlighted as
you hover, a click flies the camera into that floor, and the visitor continues room by room. It uses only footage
recorded from your own engine model, so the layout is exact (AI video invents rooms on the way; see the AI doc).

Files: `scripts/web/floorpicker/index.html`, `scripts/web/floorpicker/build_picker_data.py`,
`scripts/routes/make_flyins.py` (flights), `scripts/video/make_fly_clips.sh` and `make_frames.sh` (cutting),
`scripts/web/serve.py` (local server).

## The idea that makes it seamless

1. **One shared start view.** Every flight starts at the same drone pose (the "tower"). Its first settled frame is the
   page's still image, so the click into a video shows no jump.
2. **Every flight ends exactly on a pose of the recorded walk.** The fly route's last key *is* a key of the walk route
   (same eye and look-at). So when the fly video ends, the page swaps to the walk frame at that time and nobody sees
   the cut. Check it: the last fly frame and that walk frame should have an SSIM of about 0.96 or more.
3. **The walk is a frame sequence, not a video.** The page draws WebP frames on a canvas and can move forward or
   backward to any room stop with easing. Room hotspots are projected with the same camera curve the recorder used.
4. **Back is the same clip reversed.** Walk back to the entry pose, play `backN.mp4`, end on the tower view.

## Designing flights

- `SETTLE` (about 3 s) at the start view before each flight, with two equal keys, so the engine's auto exposure has
  settled and the camera leaves with zero speed. `HOLD` (about 1.5 s) at the end for the same reason.
- Snap every key time to whole frames (`round(t × fps) / fps`), so no frame falls inside the jump back to the start
  view between flights.
- Record all flights in one route: start view, flight 1, jump back one frame later, settle, flight 2, and so on.
  `clips.json` keeps each flight's frame range `f0..f1` and the walk time it ends on.
- Fly in through openings that are really open: an open balcony door, glass you remove, a window. Keep 0.5–0.7 m
  clear of pendants and railings; the camera has no collision.
- **Ray-cast the paths in Blender before recording**: anything the camera passes through, and anything closer than
  0.25 m. Also cast rays from the start view to points on the facade to see what hides it (hedges, outbuildings).
  The fly script's `--check` does both. Hits at doors you open during the flight are expected.
- Match the walk's settings: same field of view, resolution, time of day, exposure and white balance. A golden-hour
  version needs the walk recorded at golden hour too.

## Recording and cutting

```sh
python3 scripts/routes/make_flyins.py                       # route.txt + clips.json
blender -b model.blend --python scripts/routes/make_flyins.py -- --check
scripts/unreal/record.sh fly                                # frames, off-screen
scripts/video/make_fly_clips.sh <fly frames> [tower.png]    # fly/flyN.mp4, fly/backN.mp4, fly/tower.webp
scripts/video/make_frames.sh <walk frames> 2                # frames/hi (1600 px), frames/lo (800 px), 12 fps WebP
python3 scripts/web/floorpicker/build_picker_data.py --route <walk route.txt> --fly-route <fly route.txt> \
        --clips <clips.json> --labels labels.json            # run in the page folder -> data.json
python3 scripts/web/serve.py <page folder> 8770
```

- Clips: H.264, `-crf 19`, `yuv420p`, `+faststart`, no audio; `backN.mp4` uses the `reverse` filter on the same frames.
- Walk frames at 12 fps (every second frame of a 24 fps recording) are enough with cross-fading; the 800 px tier
  loads first so the whole walk can be scrubbed, the 1600 px tier loads around the playhead.
- Put `ffmpeg -nostdin` in shell loops that read from a pipe, or ffmpeg eats the loop's input.

Verify the handoff (last fly frame against the walk frame it should match):

```sh
ffmpeg -i fly_last.png -i walk_frame.png -lavfi "[0][1]scale2ref[a][b];[a][b]ssim" -f null -
```

## `data.json`

Written by `build_picker_data.py`: `fps`, `frames`, `width`, `height`, `hfov`, `keys` (walk route), `rooms` (key → `at`,
`area`, `label` from `labels.json`), `bands` and `fly` (`tower`, per-clip `walk_t`, `frames`, and the flight's keys
for a live 3D variant). The script warns when the frame count × fps does not match the route length (the usual cause:
frames recorded with an older route).

**Floor bands** are 3D boxes (or polygons) in model metres. The page projects them with the tower camera and draws
the convex outline, so they stay correct when you re-record the start view; never trace them by hand.

## Page states

`house` (start view, bands, panel) → `flying` (fly clip) → `floor` (walk frames, caption, room pills, hotspots) →
`flying` (walk to entry, reversed clip) → `end` (title, "Start again").

Configuration at the top of `index.html`: `FLOORS` (rooms and their walk times, two text lines per language),
`NAMES` and `TEXT` per language. Query checks: `?hover=2`, `?floor=2&room=bedroom`, `?debug`, `?lang=de`.

Hotspots: rooms of the floor projected from the current walk pose, nearest first, no overlaps, at most three, and only
those in front of the camera and away from the screen edges. They are not occlusion-tested, so choose room anchors
that are visible from the stops.

## AI-restyled flights

To show a photoreal flight, restyle the recorded clip (video-to-video with the start still as style reference, or
start/end-frame generation) and put it in `fly/ai/flyN.mp4`. Open the page with `?ai` (all floors) or `?ai=2`. Its last
frame will not match the walk pose exactly, so the page holds the video's last frame and only switches to the walk
frames on the next move. Offer a high-resolution version only to large screens (`screen.width × devicePixelRatio`),
and fall back to streaming when the full download fails (large files dropped in some browsers).

## Live 3D variant

The same flights can run live in the three.js viewer: `data.json` carries each flight's keys, and the viewer evaluates
the same Hermite curve per frame. It needs no video, but it looks like the browser bake, not the engine; it worked best
as a test page.
