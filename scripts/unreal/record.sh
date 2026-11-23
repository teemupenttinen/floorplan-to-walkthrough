#!/bin/zsh
# Record a camera route (route.txt) from the Unreal walkthrough into numbered PNG frames, off-screen.
#
#   scripts/unreal/record.sh walk   <route.txt> <out dir>     a walk: 24 fps, quality High
#   scripts/unreal/record.sh fly    <route.txt> <out dir>     fly-ins: 24 fps, Cinematic, 2 engine frames per saved frame
#   scripts/unreal/record.sh stills <route.txt> <out dir>     one picture per "still" line of the route
#
# Environment:
#   UE_ROOT   engine folder (default: the macOS Epic launcher location below)
#   PROJECT   absolute path of the .uproject (required)
#   MAP       level (default /Game/Maps/Walkthrough)
#   HOUR DAY EV WHITE FOV FPS SUB QUALITY WARM   recorder settings (see docs/00-interfaces.md)
# Golden hour example: DAY=250 HOUR=18.5 EV=-0.6 WHITE=7300 FOV=90 record.sh fly route_fly.txt fly_frames
#
# Windows: run "$UE_ROOT/Engine/Binaries/Win64/UnrealEditor.exe" with the same arguments (PowerShell).
# Linux:   "$UE_ROOT/Engine/Binaries/Linux/UnrealEditor".
set -e
MODE=${1:?mode: walk, fly or stills}
ROUTE=${2:?route.txt}
OUT=${3:?output folder}
: ${PROJECT:?set PROJECT to the absolute path of your .uproject}
UE_ROOT=${UE_ROOT:-"/Users/Shared/Epic Games/UE_5.8"}
UE="$UE_ROOT/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor"
[ -x "$UE" ] || UE="$UE_ROOT/Engine/Binaries/Linux/UnrealEditor"
MAP=${MAP:-/Game/Maps/Walkthrough}
ROUTE=$(cd "$(dirname "$ROUTE")" && pwd)/$(basename "$ROUTE")
mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)

case $MODE in
  walk)   Q=${QUALITY:-2}; S=${SUB:-1} ;;
  fly)    Q=${QUALITY:-3}; S=${SUB:-2} ;;
  stills) Q=${QUALITY:-3}; S=${SUB:-1} ;;
  *) echo "unknown mode $MODE"; exit 1 ;;
esac
FLAGS=(-WalkOut="$OUT" -WalkRoute="$ROUTE" -WalkFps=${FPS:-24} -WalkFov=${FOV:-84} -WalkSub=$S -WalkQuality=$Q
       -WalkWarm=${WARM:-20} -WalkEv=${EV:-0} -WalkWhite=${WHITE:-6500})
[ -n "$HOUR" ] && FLAGS+=(-WalkHour=$HOUR)
[ -n "$DAY" ] && FLAGS+=(-WalkDay=$DAY)

# find, not a glob: zsh aborts a script (set -e) on a glob with no match ("no matches found")
find "$OUT" -maxdepth 1 \( -name "frame_*.png" -o -name "still_*.png" \) -delete
LOG="$OUT/record.log"
# 1600 x 900: a 1920 x 1080 window does not fit a laptop screen and the frames come out at another size.
# -RenderOffscreen: no window on the screen, the GPU renders anyway.
"$UE" "$PROJECT" "$MAP" -game -windowed -ResX=1600 -ResY=900 -nosplash -RenderOffscreen "${FLAGS[@]}" > "$LOG" 2>&1 &
# The launcher process can return at once and leave the game running in the background, so wait for any
# process with this route on its command line. Do not start a second run meanwhile.
sleep 5
while pgrep -f "WalkRoute=$ROUTE" > /dev/null; do sleep 5; done
N=$(ls "$OUT" | grep -c -E '^(frame|still)_' || true)
echo "$MODE: $N pictures in $OUT"
# The game log: on a Mac the game writes ~/Library/Logs/<Project>/<Project>.log, not stdout or Saved/Logs.
GAME_LOG="$HOME/Library/Logs/$(basename "$PROJECT" .uproject)/$(basename "$PROJECT" .uproject).log"
[ -f "$GAME_LOG" ] || GAME_LOG="$(dirname "$PROJECT")/Saved/Logs/$(basename "$PROJECT" .uproject).log"
cat "$GAME_LOG" >> "$LOG" 2>/dev/null || true
grep -E "Walk: (done|stills done)" "$LOG" > /dev/null || echo "WARNING: the run did not finish; see $LOG"
grep -q "SpawnActor failed because of collision" "$LOG" && echo "WARNING: the player did not spawn: move the player start out of geometry"
grep -E "LogWalk: Error|Sampler type .* should be|Failed to compile Material" "$LOG" | sort -u | head -5
exit 0
