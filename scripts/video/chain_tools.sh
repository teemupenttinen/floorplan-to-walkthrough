#!/usr/bin/env bash
# Small ffmpeg helpers for chaining AI video segments and checking hand-overs.
#   chain_tools.sh last <clip.mp4> <out.jpg>                  last frame of a clip (start frame of the next part)
#   chain_tools.sh first <clip.mp4> <out.jpg>                 first frame
#   chain_tools.sh join <out.mp4> <part1.mp4> <part2.mp4> ...  join parts; drops the first frame of parts 2..n,
#                                                              because each part starts on the previous part's last frame
#   chain_tools.sh ssim <a.png> <b.png>                       similarity of two frames (1.0 = identical); a fly-in's
#                                                              last frame vs the walk frame it hands over to should be > 0.95
#   chain_tools.sh mp4 <frames dir> <out.mp4> [fps]           frames -> mp4
set -euo pipefail
cmd=$1; shift
case $cmd in
  last)  ffmpeg -nostdin -y -loglevel error -sseof -0.1 -i "$1" -update 1 -q:v 2 "$2" ;;
  first) ffmpeg -nostdin -y -loglevel error -i "$1" -frames:v 1 -q:v 2 "$2" ;;
  join)
    out=$1; shift; n=$#; inputs=(); filt=""; i=0
    for f in "$@"; do inputs+=(-i "$f"); done
    for f in "$@"; do
      if [ $i -eq 0 ]; then filt+="[0:v]setpts=PTS-STARTPTS[v0];"
      else filt+="[$i:v]trim=start_frame=1,setpts=PTS-STARTPTS[v$i];"; fi
      i=$((i + 1))
    done
    for ((k = 0; k < n; k++)); do filt+="[v$k]"; done
    filt+="concat=n=$n:v=1:a=0[out]"
    ffmpeg -nostdin -y -loglevel error "${inputs[@]}" -filter_complex "$filt" -map "[out]" \
      -c:v libx264 -crf 16 -pix_fmt yuv420p -movflags +faststart "$out" ;;
  ssim)  ffmpeg -nostdin -loglevel info -i "$1" -i "$2" -lavfi "[0:v]scale=800:-2[a];[1:v]scale=800:-2[b];[a][b]ssim" -f null - 2>&1 | grep -o 'All:[0-9.]*' ;;
  mp4)   ffmpeg -nostdin -y -loglevel error -framerate "${3:-24}" -i "$1/frame_%05d.png" -c:v libx264 -crf 16 -pix_fmt yuv420p -movflags +faststart "$2" ;;
  *) sed -n '2,12p' "$0"; exit 1 ;;
esac
