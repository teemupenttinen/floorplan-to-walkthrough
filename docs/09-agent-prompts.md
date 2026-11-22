# 9. Prompt guide: driving a coding agent through the pipeline

This pipeline was built with a coding agent (Claude Code) that writes and runs the Blender, Unreal and web scripts.
This chapter lists the prompts and working habits that worked. Paste the prompts as they are, and fill in the
`<...>` parts.

## Set the ground rules first

Put a project instructions file (`CLAUDE.md` or similar) in the project root. A starting point is in
`templates/CLAUDE.md`. These are the rules that mattered most:

- **Sources versus assumptions:** "Keep a SOURCES and an ASSUMPTIONS list in every build script. Never change a sourced
  number to make something fit; ask me."
- **Headless only:** "Build and export with `blender -b`, never in my open Blender session."
- **No unrequested renders:** "Don't run test renders or Unreal screenshot runs unless I ask, or unless no other check
  can find a suspected fault. Say what you did not check by eye." Renders open windows, use the GPU and take minutes.
  Ray casts, bounds checks and log reads find most faults without them.
- **Paid tools:** "Never call paid generation APIs without asking. When you do, tell me the cost before and after."
- **Check every rebuild:** "Snapshot the names, polygon counts and bounds before a rebuild, and diff them afterwards.
  Report anything that changed outside what you meant to change."
- **Shared helpers:** "Before you change a shared helper's signature, search every project that execs it."

## Stage prompts

### 1. Start a model

```text
Build a 3D model of <the home> in Blender from scripts, in a new folder <folder>/ with its own .blend.
Sources are in <folder>/sources: <plan file> (scale: <scale bar / dimension>), <photos>, <material sheet>.
Coordinates in metres, origin at <inner corner>, floor at z = 0. Put ROOMS, WALLS, WINDOWS and DOORS in data tables at
the top. Write SOURCES and ASSUMPTIONS lists. Use CC0 textures from ambientCG / Poly Haven.
Build it headless, then render one overview from above and the views that match photos <n, m> so we can compare.
```

If you don't know the scale:

```text
The plan has no dimensions. Get the scale from the room areas written on the plan, check it against two rooms,
and tell me the px/m you used.
```

### 2. Correct it from photos

```text
Here are photos of the real rooms (<files>). Solve each camera from the wall, window and door corners, make
matching render views, and move the big furniture to where it is in the photos, without clutter.
Compare every position in two photos before you trust it. Put the photo and render pairs side by side in one sheet.
```

```text
The <room> is wrong: <what you see>, for example "the sofa is on the wall with the street window on the right when you
face it". Change the table, rebuild, and show me the same view again.
```

### 3. Materials and fidelity

```text
Match the finishes to <material sheet / product page>. Convert colours from sRGB to linear. For <product>, take
the sizes from the product page; where it gives none, read them from the photo against a known size and mark them as
assumptions.
```

```text
The <wood> repeats on a visible <60 cm> grid. Build a bigger tile from random strips of the scan, with knots on
only about a third of the boards.
```

### 4. Unreal

```text
Make an Unreal Engine <version> walkthrough of this model with realistic graphics (Lumen, hardware ray tracing).
Put the gameplay in C++ (first-person player, doors that open with E, keys 1-9 for spots, L for lamps,
O for a lighting panel with sun hour and exposure) and the scene setup in a Python import script that reads a
manifest exported from Blender. No Blueprints. Use the coordinate rule Blender (x, y, z) m = Unreal (100x, -100y, 100z) cm.
Build, import, and tell me the commands to run it. Don't take screenshots.
```

```text
The rooms are too dark / the window views burn out. Tune the post-process: histogram auto exposure that ignores the
brightest 35 %, local exposure for the window views, and a default of -1 EV. Say what you changed and why.
```

```text
<Something> looks wrong in Unreal: <blocky reflections / jagged shadows / white walls look olive>. Before changing
content, check the saved quality preset, the light grid and the bounce colour settings, and tell me the cause you found.
```

### 5. Recording

```text
Record a walkthrough video through all rooms in Unreal, frame by frame with a fixed time step, 24 fps, 1600x900,
84° FOV, quality High. Write the route as keys in a Python script, ray-cast it against the model in Blender before
recording, and open doors only where the walk passes them. Encode an mp4 and 10 s parts.
```

```text
Record it again at golden hour: pick a day and hour when the low sun falls on the <courtyard> facade (ray-cast it),
EV -0.6, white balance about 7300 K. Test stills of the start and end poses first.
```

### 6. Fly-ins and the sales page

```text
Make a "choose your floor" page like <reference>: one high drone view of the building; hovering a floor highlights its
band (project it from the model outline, don't trace it); clicking flies in (a recorded Unreal fly-in) and hands over
without a cut to the recorded walk frames on that floor; room pills and projected hotspots move along the walk;
"back" plays the flight reversed. Each flight must end exactly on a walk pose. Check the flights by ray casting and the
hand-over by SSIM. Serve it locally.
```

### 7. Browser version

```text
Make a browser walkthrough of the same model with three.js: baked light maps from Cycles (one atlas per floor,
denoised), the real tiling materials, room reflection probes, capsule collision with a BVH, and the Unreal look
(exposure, saturation, white, vignette). Default state as in Unreal. Headless-test it with Chrome over CDP, not with
screenshots I have to look at.
```

### 8. Photoreal kit

```text
Prepare a photoreal kit from the Unreal footage for me to run myself (no paid API calls): per shot the start and end
frames, motion.mp4, the references, and prompts that lock the framing (name what each image edge cuts through),
name the materials against their typical failures, and take only the photographic look from the look reference.
Add an overview sheet and a README with the workflow and the checks.
```

## Feedback that works

- **Name the place:** "the north wall of the small bedroom", "the wall with the window on your right". Avoid "left"
  unless you say which way you are facing.
- **Give numbers:** "move the bed 20 cm toward the window", "the door opens 70°".
- **Say what to keep:** "keep the sofa; change only the rug".
- **Show it:** paste a photo or a screenshot, and say what in it is right.
- **Say what stays fixed:** "Only update Unreal, not the browser version." "The second unit always has the
  developer's furniture."
- **Make defaults explicit:** "Every door starts closed." "The game starts with layout 0." Agents do not guess these.

## Things to ask the agent to remember

At the end of a session, ask it to save what was learned to its memory or notes. For example: the commands that
rebuild everything, the ports of the local servers, a cause that took long to find ("the slow game was a failed
player spawn, not the meshes"), and your standing preferences ("no extra renders", "ask before paid tools"). A later
session then starts where this one stopped.

## Parallel sessions

Several agent sessions can work on one project, for example one on Unreal and one on the web viewer. Rules:

- Give each session its own output folder and its own Unreal project, or at least its own map.
- Shared build helpers are the danger: a rebuild runs every unbuilt edit, including another session's edits.
  Snapshot-diff every rebuild.
- Only one session should drive the open Blender or Unreal editor at a time.
