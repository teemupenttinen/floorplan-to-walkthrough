#!/usr/bin/env bash
# Cut the recorded fly-ins into the floor picker's videos, using the frame ranges in clips.json:
#   <site>/fly/fly<id>.mp4    forward
#   <site>/fly/back<id>.mp4   the same frames reversed (the way out)
#   <site>/fly/tower.webp     the start view (first frame of the first flight, or a path-traced still)
# Usage: make_fly_clips.sh <fly frames dir> <clips.json> <site dir> [start view png]
set -euo pipefail
SRC=$1; CLIPS=$2; SITE=$3; TOWER=${4:-}
rm -rf "$SITE/fly" && mkdir -p "$SITE/fly"
python3 -c "
import json, sys; c = json.load(open(sys.argv[1]))
for x in c['clips']: print(x['id'], x['f0'], x['f1'])" "$CLIPS" | while read -r id f0 f1; do
  cnt=$((f1 - f0 + 1))
  for dir in fly back; do
    vf="scale=1600:-2"; [ $dir = back ] && vf="reverse,$vf"
    # -nostdin: inside a 'while read' loop ffmpeg would otherwise eat the loop's input.
    ffmpeg -nostdin -y -loglevel error -framerate 24 -start_number "$f0" -i "$SRC/frame_%05d.png" -frames:v $cnt \
      -vf "$vf" -c:v libx264 -preset slow -crf 19 -pix_fmt yuv420p -movflags +faststart -an "$SITE/fly/$dir$id.mp4"
  done
  if [ ! -f "$SITE/fly/tower.webp" ]; then
    [ -n "$TOWER" ] || TOWER="$SRC/$(printf 'frame_%05d.png' "$f0")"
    ffmpeg -nostdin -y -loglevel error -i "$TOWER" -c:v libwebp -quality 86 "$SITE/fly/tower.webp"
  fi
  echo "flight $id: $cnt frames"
done
