#!/usr/bin/env bash
# Encode recorded frames (frame_00000.png ...) into
#   <out>/walkthrough.mp4        the whole walk, H.264, 24 fps, CRF 16
#   <out>/parts/part_NN.mp4      N-second parts for AI video tools (most take 5-10 s clips)
#   <out>/parts/part_NN_first.jpg   the first frame of each part (for image-guided tools)
# Usage: encode.sh <frames dir> <out dir> [part seconds, default 10] [fps, default 24]
set -euo pipefail
SRC=$1; OUT=$2; PART=${3:-10}; FPS=${4:-24}
mkdir -p "$OUT"
ffmpeg -nostdin -y -loglevel error -framerate "$FPS" -i "$SRC/frame_%05d.png" -c:v libx264 -preset slow -crf 16 \
  -pix_fmt yuv420p -movflags +faststart "$OUT/walkthrough.mp4"
rm -rf "$OUT/parts" && mkdir "$OUT/parts"
N=$(ls "$SRC" | grep -c '^frame_')
PER=$((PART * FPS)); i=0; start=0
while [ $start -lt "$N" ]; do
  name=$(printf "part_%02d" $i)
  ffmpeg -nostdin -y -loglevel error -framerate "$FPS" -start_number $start -i "$SRC/frame_%05d.png" -frames:v $PER \
    -c:v libx264 -preset slow -crf 16 -pix_fmt yuv420p -movflags +faststart "$OUT/parts/$name.mp4"
  ffmpeg -nostdin -y -loglevel error -i "$SRC/$(printf 'frame_%05d.png' $start)" -q:v 2 "$OUT/parts/${name}_first.jpg"
  i=$((i + 1)); start=$((start + PER))
done
echo "walkthrough.mp4 ($N frames) and $i parts of $PART s in $OUT"
