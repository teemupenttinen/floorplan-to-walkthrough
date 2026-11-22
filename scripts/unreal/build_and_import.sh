#!/bin/zsh
# The model -> Unreal loop.
#   1. Blender exports meshes, textures and manifest.json (scripts/blender/export_manifest.py), headless.
#   2. The Unreal commandlet imports them and rebuilds the level (Content/Python/import_manifest.py).
#      The editor must be CLOSED: it holds the assets.
#   3. Optional: compile the C++ module (only after C++ changes).
#
#   BLEND=model.blend PROJECT=/abs/Walkthrough.uproject scripts/unreal/build_and_import.sh [--cpp] [--level-only]
#
# Environment: BLENDER (Blender binary), UE_ROOT (engine folder), WALK_EXPORT (export folder, default
# <project folder>/../export), PLATFORM (Mac, Win64, Linux).
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
: ${BLEND:?set BLEND to the .blend file}
: ${PROJECT:?set PROJECT to the absolute path of the .uproject}
BLENDER=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}
UE_ROOT=${UE_ROOT:-"/Users/Shared/Epic Games/UE_5.5"}
PLATFORM=${PLATFORM:-Mac}
PROJ_DIR=$(dirname "$PROJECT")
MODULE=$(basename "$PROJECT" .uproject)
export WALK_EXPORT=${WALK_EXPORT:-$(cd "$PROJ_DIR/.." && pwd)/export}
mkdir -p "$PROJ_DIR/Saved/Logs"

if [[ " $* " == *" --cpp "* ]]; then
  echo "== C++ build"
  # Mac: the Metal toolchain is a separate download for every Xcode version:
  #   xcodebuild -downloadComponent MetalToolchain
  "$UE_ROOT/Engine/Build/BatchFiles/Mac/Build.sh" ${MODULE}Editor $PLATFORM Development -project="$PROJECT"
fi

if [[ " $* " != *" --level-only "* ]]; then
  echo "== Blender export -> $WALK_EXPORT"
  # --python-exit-code 1: a Python error fails the step instead of leaving half an export.
  "$BLENDER" -b "$BLEND" --python-exit-code 1 --python "$HERE/../blender/export_manifest.py" -- --out "$WALK_EXPORT"
else
  export LEVEL_ONLY=1
fi

echo "== Unreal import (editor must be closed)"
if pgrep -f "UnrealEditor.*$(basename "$PROJECT")" > /dev/null; then
  echo "The editor seems to be open with this project. Close it, or use remote_run.py with update_running_editor.py."
  exit 1
fi
UE_CMD="$UE_ROOT/Engine/Binaries/Mac/UnrealEditor-Cmd"
[ -x "$UE_CMD" ] || UE_CMD="$UE_ROOT/Engine/Binaries/Linux/UnrealEditor-Cmd"
"$UE_CMD" "$PROJECT" -run=pythonscript -script="$PROJ_DIR/Content/Python/import_manifest.py" -unattended -nosplash \
  > "$PROJ_DIR/Saved/Logs/import.log" 2>&1 || true
grep "\[walkthrough\]" "$PROJ_DIR/Saved/Logs/import.log" | tail -20
grep -q "\[walkthrough\] done" "$PROJ_DIR/Saved/Logs/import.log" || { echo "import did not finish: see Saved/Logs/import.log"; exit 1; }
