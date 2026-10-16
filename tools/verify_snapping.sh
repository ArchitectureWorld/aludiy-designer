#!/usr/bin/env bash
# Run in the repository root, in an isolated Blender configuration.
set -euo pipefail
B="${1:?Path to the Blender executable required}"
OUT="${2:?Evidence output directory required}"
mkdir -p "$OUT"
export BLENDER_USER_CONFIG="$OUT/config"
export LIBGL_ALWAYS_SOFTWARE=1
mkdir -p "$BLENDER_USER_CONFIG"
"$B" --version > "$OUT/blender-version.txt"
for name in blender_smoke_test blender_movement_test blender_snap_test; do
  "$B" -b --factory-startup --python-exit-code 1 --python "tools/$name.py" > "$OUT/$name.log" 2>&1
done
"$B" -b --factory-startup --python-expr 'import bpy; bpy.context.preferences.view.show_splash=False; bpy.ops.wm.save_userpref()' > "$OUT/preferences.log" 2>&1
for pair in snap:blender_gui_snap_test move:blender_gui_move_test sample:blender_sample_safety_test; do
  name="${pair%%:*}"; script="${pair#*:}"
  export ALUDIY_EVIDENCE_DIR="$OUT/$name"
  timeout 150s xvfb-run -a -s '-screen 0 1800x1100x24' "$B" --gpu-backend opengl -t 2 -p 0 0 1680 1000 --python "tools/$script.py" > "$OUT/$name-gui.log" 2>&1
  python - "$OUT/$name/report.json" <<'PY'
import json, sys
p=sys.argv[1]; r=json.load(open(p)); assert r['status']=='passed', r
print(p, 'GUI checks:', len(r['checks']))
PY
  if grep -E 'Traceback|Python script error|AluDIY endpoint overlay:' "$OUT/$name-gui.log"; then exit 1; fi
done
export ALUDIY_EVIDENCE_DIR="$OUT/snap"
"$B" -b "$OUT/snap/endpoint-demo.blend" --python-exit-code 1 --python tools/blender_reopen_snap_test.py > "$OUT/snap-reopen.log" 2>&1
export ALUDIY_EVIDENCE_DIR="$OUT/move"
"$B" -b "$OUT/move/endpoint-demo.blend" --python-exit-code 1 --python tools/blender_reopen_move_test.py > "$OUT/move-reopen.log" 2>&1
export ALUDIY_EVIDENCE_DIR="$OUT/sample"
"$B" -b "$OUT/sample/sample-safety.blend" --python-exit-code 1 --python-expr 'import sys,json,os; from pathlib import Path; sys.path.insert(0,str(Path("extension").resolve())); import aludiy_designer as a; a.register(); import bpy; from aludiy_designer import runtime; assert runtime.get_project(bpy.context.scene).to_dict()==json.load(open(Path(os.environ["ALUDIY_EVIDENCE_DIR"])/"expected.aludiy.json")); print("SAMPLE_REOPEN_OK"); a.unregister()' > "$OUT/sample-reopen.log" 2>&1
printf 'SNAP_AND_EXISTING_REGRESSIONS_OK\n'
