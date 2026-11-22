#!/usr/bin/env bash
# Turn recorded walk frames into the scroll / floor-picker page's WebP sequences:
#   <site>/frames/hi/NNNN.webp  1600 px, drawn when loaded
#   <site>/frames/lo/NNNN.webp   800 px, loaded first so the whole walk can be scrubbed at once
# Usage: make_frames.sh <frames dir> <site dir> [step, default 2]
#   step 2 turns a 24 fps recording into 12 fps on the page (half the downloads, still smooth with cross-fades).
set -euo pipefail
SRC=$1; SITE=$2; STEP=${3:-2}
rm -rf "$SITE/frames" && mkdir -p "$SITE/frames/hi" "$SITE/frames/lo"
enc() {  # width quality tier
  ffmpeg -nostdin -y -loglevel error -framerate 24 -i "$SRC/frame_%05d.png" \
    -vf "select=not(mod(n\,$STEP)),scale=$1:-2:flags=lanczos" -fps_mode passthrough \
    -c:v libwebp -quality "$2" -compression_level 4 -start_number 0 "$SITE/frames/$3/%04d.webp"
}
enc 1600 80 hi &
enc 800 62 lo &
wait
echo "hi: $(ls "$SITE/frames/hi" | wc -l | tr -d ' ') frames, $(du -sh "$SITE/frames/hi" | cut -f1); lo: $(du -sh "$SITE/frames/lo" | cut -f1)"
