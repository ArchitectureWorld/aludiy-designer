#!/usr/bin/env bash
# Reproducible real-Blender verification in an isolated config and X11 display.
set -euo pipefail
B="${1:?Blender path required}"
OUT="${2:?Evidence path required}"
mkdir -p "$OUT"; OUT="$(cd "$OUT" && pwd)"
export BLENDER_USER_CONFIG="$OUT/config" LIBGL_ALWAYS_SOFTWARE=1
mkdir -p "$BLENDER_USER_CONFIG"
"$B" --version > "$OUT/blender-version.txt"
for name in blender_smoke_test blender_movement_test blender_snap_test; do
  timeout -k 5s 40s "$B" -t 2 -b --factory-startup --python-exit-code 1 --python "tools/$name.py" > "$OUT/$name.log" 2>&1
done
"$B" -t 2 -b --factory-startup --python-expr 'import bpy; bpy.context.preferences.view.show_splash=False; bpy.ops.wm.save_userpref()' > "$OUT/preferences.log" 2>&1
for pair in manual:blender_gui_manual_test move:blender_gui_move_test sample:blender_sample_safety_test; do
  name="${pair%%:*}"; script="${pair#*:}"
  export ALUDIY_EVIDENCE_DIR="$OUT/$name"
  timeout -k 5s 120s xvfb-run -a -s '-screen 0 1800x1100x24' "$B" --gpu-backend opengl -t 2 -p 0 0 1680 1000 --python "tools/$script.py" > "$OUT/$name-gui.log" 2>&1
  python - "$ALUDIY_EVIDENCE_DIR/report.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]));assert r['status']=='passed',r
print(sys.argv[1],len(r['checks']),'checks')
PY
  if grep -E 'Traceback|Python script error|AluDIY endpoint overlay:' "$OUT/$name-gui.log"; then exit 1; fi
  case "$name" in manual) file=manual-associations.blend;; move) file=endpoint-demo.blend;; sample) file=sample-safety.blend;; esac
  timeout -k 5s 40s "$B" -t 2 -b "$ALUDIY_EVIDENCE_DIR/$file" --python-exit-code 1 --python-expr 'import sys,json,os; from pathlib import Path;sys.path.insert(0,str(Path("extension").resolve()));import aludiy_designer as a;a.register();import bpy;from aludiy_designer import runtime;assert runtime.get_project(bpy.context.scene).to_dict()==json.load(open(Path(os.environ["ALUDIY_EVIDENCE_DIR"])/"expected.aludiy.json"));print("FRESH_PROCESS_REOPEN_OK",flush=True);a.unregister()' > "$OUT/$name-reopen.log" 2>&1
done
printf 'MANUAL_ASSOCIATIONS_RUNTIME_OK\n'
