"""
Build a photoreal "kit" from recorded Unreal footage: per shot the start and end frames, the camera motion clip,
the reference list and ready-to-paste prompts, plus an overview sheet. A person (or a script) then runs the image
and video models with it; nothing here calls a paid API.

  python3 make_kit.py shots.json out/kit

shots.json:
{
  "style": {                                  // shared prompt parts (see templates/*.txt)
    "materials": "walls white-painted plaster, light oak floor, black window frames, white matt joinery",
    "exterior": "red brick walls with light mortar, white window frames, a grey tiled roof",
    "light": "golden hour, low warm sunlight through the windows, the rest of the room in soft bounce light",
    "light_short": "golden hour",
    "scale": "ceiling 2.6 m, doors 2.1 m, worktop 90 cm; adults 1.70-1.85 m"
  },
  "references": {"@look": "references/look_reference.jpg", "@exterior": "references/exterior/facade.jpg"},
  "shots": [
    {"id": "room_living", "kind": "room", "frames": "../recordings/rooms", "f0": 0, "f1": 182,
     "subject": "the living room seen from the hall: sofa, rug, the large window", "edges":
     "the left edge cuts the bookshelf, the right edge cuts the window frame",
     "refs": ["references/developer/living.jpg"]},
    {"id": "fly_kitchen", "kind": "fly", "frames": "../recordings/fly", "f0": 72, "f1": 278,
     "subject": "a high drone view over the courtyard of the building", "end_subject": "inside the kitchen",
     "path": "it glides down toward the facade and flies in through the open balcony door into the kitchen",
     "refs": []}
  ]
}

Kinds: "room" (interior: start and end still use still_interior), "fly" (start still uses still_exterior, end
still uses still_interior unless "end_kind": "exterior"). Frame ranges are in the recorded frame folders
(frame_00000.png ...). Paths are relative to shots.json.
"""

import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(HERE, "templates")
FPS = 24


class Blank(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def tpl(name, values):
    text = open(os.path.join(TEMPLATES, name + ".txt")).read().strip()
    return text.format_map(Blank(values)).replace("  ", " ")


def frame(src_dir, n, dst):
    src = os.path.join(src_dir, "frame_%05d.png" % n)
    if not os.path.exists(src):
        raise FileNotFoundError(src)
    shutil.copy2(src, dst)


def motion_clip(src_dir, f0, f1, dst, width=1344):
    """The camera move of the shot, small: a reference for video models (not a style reference)."""
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-framerate", str(FPS), "-start_number", str(f0),
                    "-i", os.path.join(src_dir, "frame_%05d.png"), "-frames:v", str(f1 - f0 + 1),
                    "-vf", "scale=%d:-2" % width, "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", dst], check=True)


def overview(kit, shots):
    """Start and end frame of every shot, two shots per row."""
    lst = []
    for s in shots:
        lst += [os.path.join(kit, "shots", s["id"], "start.png"), os.path.join(kit, "shots", s["id"], "end.png")]
    if not lst:
        return
    inputs = []
    for p in lst:
        inputs += ["-i", p]
    n = len(lst)
    cols = 4
    rows = (n + cols - 1) // cols
    filt = "".join("[%d:v]scale=480:-2[s%d];" % (i, i) for i in range(n))
    layout = "|".join("%d_%d" % ((i % cols) * 480, (i // cols) * 270) for i in range(n))
    filt += "".join("[s%d]" % i for i in range(n)) + "xstack=inputs=%d:layout=%s:fill=black" % (n, layout)
    if n == 1:
        filt = "[0:v]scale=480:-2"
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error"] + inputs +
                   ["-filter_complex", filt, "-frames:v", "1", "-q:v", "3", os.path.join(kit, "overview.jpg")], check=True)


def main():
    spec_path = os.path.abspath(sys.argv[1])
    kit = os.path.abspath(sys.argv[2])
    base = os.path.dirname(spec_path)
    spec = json.load(open(spec_path))
    style = spec.get("style", {})
    os.makedirs(os.path.join(kit, "shots"), exist_ok=True)
    md = ["# Prompts per shot", "",
          "Attach as named in the prompt: `@render` = start.png or end.png of the shot, `@dev` = the reference images "
          "in refs.txt, `@look` = the look reference, `@start` / `@end` = your checked photoreal stills, "
          "`@motion` = motion.mp4. If a tool has no tags, write \"image 1\", \"image 2\" and list what each one is.", ""]
    for tag, rel in spec.get("references", {}).items():
        src = os.path.join(base, rel)
        if os.path.exists(src):
            os.makedirs(os.path.join(kit, "references"), exist_ok=True)
            shutil.copy2(src, os.path.join(kit, "references", os.path.basename(src)))
    for s in spec["shots"]:
        d = os.path.join(kit, "shots", s["id"])
        os.makedirs(d, exist_ok=True)
        src = os.path.join(base, s["frames"])
        frame(src, s["f0"], os.path.join(d, "start.png"))
        frame(src, s["f1"], os.path.join(d, "end.png"))
        motion_clip(src, s["f0"], s["f1"], os.path.join(d, "motion.mp4"))
        seconds = round((s["f1"] - s["f0"] + 1) / FPS, 1)
        v = dict(style, **s, seconds=seconds, extra=s.get("extra", ""))
        if s["kind"] == "fly":
            start = tpl("still_exterior", v)
            end_v = dict(v, subject=s.get("end_subject", s["subject"]))
            end = tpl("still_exterior" if s.get("end_kind") == "exterior" else "still_interior", end_v)
            video = tpl("video_flyin", v)
        else:
            start = tpl("still_interior", v)
            end = tpl("still_interior", v)
            video = tpl("video_room", v)
        end += tpl("still_end_suffix", v)
        refs = [os.path.join(base, r) for r in s.get("refs", [])]
        open(os.path.join(d, "refs.txt"), "w").write("\n".join(refs) + "\n")
        for name, text in (("still_start", start), ("still_end", end), ("video", video)):
            open(os.path.join(d, name + ".txt"), "w").write(text + "\n")
        md += ["## %s (%s, %.1f s)" % (s["id"], s["kind"], seconds), "",
               "References: " + (", ".join("`%s`" % os.path.relpath(r, base) for r in refs) or "none"), "",
               "**Start still** (`@render` = start.png):", "", "```text", start, "```", "",
               "**End still** (`@render` = end.png, plus your photoreal start still as `@start`):", "", "```text", end, "```", "",
               "**Video** (first frame = your start still, last frame = your end still, camera path = motion.mp4):", "",
               "```text", video, "```", ""]
        missing = sorted({k for k in ("subject", "edges", "materials", "light", "path") if "{" + k + "}" in start + end + video})
        if missing:
            print("WARNING: %s: fill in %s" % (s["id"], ", ".join(missing)))
    open(os.path.join(kit, "PROMPTS.md"), "w").write("\n".join(md))
    overview(kit, spec["shots"])
    shutil.copy2(os.path.join(HERE, "KIT_README.md"), os.path.join(kit, "README.md"))
    print("kit: %d shots -> %s" % (len(spec["shots"]), kit))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main()
