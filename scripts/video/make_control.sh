#!/usr/bin/env bash
# Control video for ControlNet-guided AI video (Canny/edge mode), from Unreal buffer passes instead of the lit render.
# Edges of the world-normal pass (geometry) + edges of the blurred base-colour pass (material borders): no lighting,
# so sun patches and shadows give no edges (Canny of the lit render gave black artifacts where the sun fell).
# The base colour is blurred first so wood knots and tile noise give no dots.
# Record the passes with the same route: add -ExecCmds="r.BufferVisualizationTarget WorldNormal,viewmode VisualizeBuffer"
# (and BaseColor) to the recorder run.
# Usage: make_control.sh <normal frames dir> <basecolor frames dir> <out.mp4> [W H]
set -euo pipefail
N=$1; B=$2; OUT=$3; W=${4:-1344}; H=${5:-768}
ffmpeg -nostdin -v error -y -framerate 24 -i "$N/frame_%05d.png" -framerate 24 -i "$B/frame_%05d.png" -filter_complex \
 "[0:v]scale=$W:$H:flags=lanczos,edgedetect=low=0.05:high=0.12:mode=wires,format=gray[n];[1:v]scale=$W:$H:flags=lanczos,gblur=sigma=1.5,edgedetect=low=0.1:high=0.25:mode=wires,format=gray[b];[n][b]blend=all_mode=lighten,lut=y='if(gt(val,40),255,0)',format=yuv420p" \
 -c:v libx264 -crf 18 -preset slow "$OUT"
echo "wrote $OUT"
