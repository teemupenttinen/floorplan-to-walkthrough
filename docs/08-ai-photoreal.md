# 8. Photoreal stills and videos with AI models

Real-time renders are accurate but look like CGI. Image and video models look real but invent things. The method here
keeps the **geometry, the camera and the furniture from the render**, and takes **only the photographic qualities**
from the model. Everything is prepared as a kit (`scripts/ai/make_kit.py`), so a person can run the paid tools by hand
and review each result.

## Which tool for which job (as of late 2026)

| Job | Tool type | Examples | Notes |
|---|---|---|---|
| Photoreal still from a render | Image edit with several references | Nano Banana Pro, Qwen-Image-Edit (+ a "real" LoRA), GPT Image | The best realism came from Nano Banana Pro at 2K, 16:9. Qwen-Image-Edit with ControlNet (Canny of the render) holds the framing well, but its light stays flat. |
| Room clip, 5–10 s | Start + end frame video | Kling 3/4, Seedance 2.x, Veo, MiniMax H3 | Both frames fix the move. Short clips work well. |
| Fly-in that must follow the plan | Video-to-video restyle, or ControlNet video | Runway Aleph, Luma Modify, Wan VACE, MiniMax H3 + Fun ControlNet (self-hosted) | Start + end models **invent the interior on the way**. Restyle the recorded motion instead. |
| Walk through several rooms | Reference-to-video with a motion reference | Seedance 2.x Reference (clay video + material crops) | Split it into 5 s parts, one floor each, chained on last frames. |
| Upscale | Video upscaler | Built into most hosts | 4K makes the files 20+ MB. Serve them only to large screens. |

Costs add up fast. A typical sales kit is about 40 stills and 20 videos. At late-2026 prices that is about 800 credits
for the stills and 100–270 per video. Budget before you start, and ask before every paid run.

## The anatomy of a still prompt

Every still prompt has the same parts, in this order. The templates are in `scripts/ai/templates/`.

1. **Task:** "Re-photograph @render as a real interior photograph."
2. **Framing lock:** "Keep the camera, the framing and the room size exactly: the image edges cut through the same objects
   as in @render (*the left edge cuts the bookshelf, the window fills the centre-right, the right edge cuts the door
   frame*); do not zoom out, do not widen, add nothing and remove nothing."
3. **Subject:** what the view shows, in plain words, with each large object and where it is.
4. **Furniture source:** "the furniture exactly as in @render". If the references show other furniture, also say "it
   is not the furniture of the reference images: keep ours".
5. **Materials,** named and described against the usual failures, for example "white-waxed spruce, very pale warm
   ivory with faint grain, **not yellow**", "light grey polished concrete", "black window frames".
6. **Look reference:** "Take from @look only its photographic qualities (real light falloff, soft shadows, real
   material texture, slight lens vignetting, fine grain)."
7. **Light:** time of day, the direction of the sun, and the white balance, for example "golden hour, low warm sun from
   the left, the rest of the room in soft bounce light, neutral whites in the shade".
8. **Genre and negatives:** "Real estate photography with a wide rectilinear lens, verticals straight,
   indistinguishable from reality, not CGI. No people, no text."
9. **For the end still of a shot:** "Match the materials, colours and light of @start exactly." Attach your checked
   start still as `@start`.

### Exterior drone stills

Add a hard description of the facade, and attach the developer's or a photographed exterior as `@exterior`, for
example: "all outer walls are clad in <colour> <material> (<width, finish>), and the roof is <material and shape> as
in @exterior". Without it, a model made a dark facade pale on the first try. Say which parts differ, for example
"only the inside of the balcony recesses is pale wood".

### Lifestyle stills (people)

Add a **scale line** with real sizes: "ceiling 2.7 m, doors 2.1 m, worktop 90 cm; adults 1.70–1.85 m, a 3-year-old
95 cm, a 1-year-old 75 cm". Then describe one simple action per person. Models zoom out when they add people, so
the framing lock matters even more. Hosts moderate some scenes, such as children in a parents' bed, so phrase family
scenes neutrally.

## Reference handling

- **Order and tags:** attach the render first (`@render`, image 1), then the look reference (`@look`, image 2), then
  the material references (`@dev`). If the tool has no tags, write "image 1", "image 2" and say what each one is.
  Tools that count images and videos separately call them `@Image3` and `@Video1`. Describe each reference in the
  prompt too, so the model can match them by content.
- **Use close-up crops, not whole rooms.** With whole-room reference images, a video model jumped to their exact
  views and copied their furniture. Crops of materials and objects (a floor patch, a tap, a door pull) give the look
  without a view to jump to.
- **The look reference** is one real photograph with good light: for example, a well-lit hall photo from a real home.
  It gives the look only. Say so in every prompt.
- **Never use the render video as a style reference.** The result copies the CGI look. Use it only as a motion
  reference (`@motion`), or as the source of a ControlNet edge video.

## Checking every result

Check every result against `@render` before it goes anywhere:

| Check | How |
|---|---|
| Framing | Do the image edges cut the same objects? If the result shows more of the room, it zoomed out: run it again. |
| Scale | People and objects against the 2.1 m doors and the ceiling height |
| Windows and doors | Are they the same number in the same places? A bathroom with no window got one twice. |
| Materials | The colour against the references; tiles must not turn into wood |
| Small hardware | Image models drew pulls and handles 1.5–2.5 times too big, even when the prompt asked for the exact size. Measure the part in the render, then retouch the result by hand (fill, then draw the shape at the render's size). |
| Text and signs | No invented text |

Keep the checked results in a `best/` folder, one per view, and keep the rejected ones with a note on why.

## Videos

### Start + end frames (room clips)

```text
A slow, steady real estate gimbal move from the first frame to the last frame, exactly as in @motion (eases in and
out, no shake, no zoom). The room, the furniture and the light do not change. About 8 seconds. Photoreal, golden
hour, no people, no text.
```

Give the model your two checked stills as the first and the last frame. Attach `motion.mp4` where the tool accepts a
motion reference.

### Fly-ins: keep the real path

Start + end models flew to the right balcony, but on the way they cross-faded at the door or invented a kitchen
island for a moment. To keep the plan:

1. **Video-to-video restyle** of `motion.mp4`, with the photoreal start still as the style reference
   (`templates/video_restyle.txt`).
2. **Self-hosted ControlNet video** (`scripts/ai/h3_job_example.py`): an edge video from the Unreal normal and
   base-colour passes (`make_control.sh`) drives the structure. The photoreal start and end stills anchor frame 0 and
   the last frame. Developer images give the materials. In tests it followed the Unreal path exactly; the remaining
   faults were colour drift in the middle of the clip.

### Long walks

- Split them into 5–10 s parts. Each part starts on the **last frame of the good previous part**
  (`chain_tools.sh last`). Join the parts and drop the repeated first frames (`chain_tools.sh join`).
- Give each part only the references of its own rooms.
- A white **clay render** of the route (Cycles, 16 samples, every material white) is a clean motion reference. It
  carries no CGI materials for the model to copy.

## A self-hosted GPU (optional)

A rented 48 GB GPU running ComfyUI is free of per-generation credits, and it runs the open models with ControlNet.
`scripts/ai/comfy_client.py` uploads the inputs, queues an API-format graph, waits and downloads the outputs. Its
docstring has the SSH tunnel recipe and the pitfalls: HTTP proxies that block uploads or user agents, a container
disk that loses everything on restart, and a GPU stuck after a crash.

## Kit layout (what make_kit.py writes)

```text
kit/
  README.md            the workflow and the fixes table (from scripts/ai/KIT_README.md)
  PROMPTS.md           every prompt, shot by shot
  overview.jpg         the start and end frame of every shot
  references/          the look reference, exterior and developer images
  shots/<id>/          start.png end.png motion.mp4 refs.txt still_start.txt still_end.txt video.txt
```

The kit lets someone else, a designer or a later session, make the photoreal set without knowing Unreal. It also
keeps paid generation in a person's hands.
