# Photoreal kit

This kit turns real-time renders into photoreal stills and videos. Use an image-edit model for the stills, and a
start-and-end-frame or video-to-video model for the videos.

## What is here

| Path | Contents |
|---|---|
| `overview.jpg` | The start and end frame of every shot. |
| `PROMPTS.md` | All prompts, shot by shot, ready to paste. |
| `shots/<id>/start.png`, `end.png` | The rendered frames. Use them as `@render`: they fix the layout, the camera and the furniture. |
| `shots/<id>/motion.mp4` | The camera move of the shot (`@motion`). |
| `shots/<id>/refs.txt` | The reference images to attach for this shot. |
| `shots/<id>/still_start.txt`, `still_end.txt`, `video.txt` | The prompts again, one per file, for scripts. |
| `references/` | The look reference and the exterior or developer images. |

## Workflow

1. **Shared stills first.** If several shots start on the same view (all fly-ins start on one drone view), make that
   photoreal still once and use it as the first frame of all of them.
2. **Stills, shot by shot.** Make the start still first. Then make the end still, and add your start still as `@start`,
   so the materials and the light match. Check every result against `@render`:
   - the same framing: image models tend to zoom out or widen;
   - the same furniture and the same number of windows and doors;
   - the materials' colours, for example pale wood that must not turn yellow.
3. **Videos.** There are two ways:
   - **Start and end frames only:** the model invents the path between the two frames. This works for short room
     moves, because both frames already fix the move.
   - **The exact path:** a video-to-video model restyles `motion.mp4`, with your start still as the style reference.
     This keeps the camera move and the layout. Use it for fly-ins, because start-and-end models invent the
     building on the way.
4. **Chaining.** If a clip must follow another clip without a cut, use the end still of the first clip as the first
   frame of the next one.

## When a result is wrong

| Problem | Fix |
|---|---|
| It zoomed out, and the room looks bigger. | Name what each image edge cuts through. The prompts already do this, so add detail. |
| It added a window, for example in a bathroom. | Say "This room has no window: do not add any window." |
| A material came out wrong, such as tiles turned into wood. | Add a close-up crop of the real material as an extra reference. |
| Small parts came out too big, such as handles and pulls. | Image models enlarge them, and asking for the right size seldom helps. Retouch them by hand, and measure the size in the render. |
| The result copied a reference's furniture or view. | Use close-up crops of materials as references, not whole-room images. |
| The video morphs or cuts between rooms. | Use shorter segments. Chain them on last frames, or restyle `motion.mp4` instead. |
