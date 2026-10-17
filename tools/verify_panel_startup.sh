#!/usr/bin/env bash
# Native Panel.draw must run before any test initializes an AluDIY project.
set -euo pipefail
B="${1:?Blender executable}"; OUT="${2:?Evidence directory}"
mkdir -p "$OUT"; OUT="$(cd "$OUT" && pwd)"
export LIBGL_ALWAYS_SOFTWARE=1 BLENDER_USER_CONFIG="$OUT/config"
mkdir -p "$BLENDER_USER_CONFIG"
"$B" -b -t 2 --factory-startup --python-expr 'import bpy;bpy.context.preferences.view.show_splash=False;bpy.context.preferences.view.smooth_view=0;bpy.ops.wm.save_userpref()' > "$OUT/prefs.log" 2>&1
for SCALE in 1 1.5; do
  export ALUDIY_TEST_UI_SCALE="$SCALE" ALUDIY_EVIDENCE_DIR="$OUT/cold-$SCALE"
  timeout -k 5s 70s xvfb-run -a -s '-screen 0 1440x1000x24' "$B" --gpu-backend opengl -t 2 -p 0 0 1320 900 --python tools/blender_gui_panel_startup_test.py > "$OUT/cold-$SCALE.log" 2>&1
  export ALUDIY_EVIDENCE_DIR="$OUT/reopen-$SCALE"
  timeout -k 5s 70s xvfb-run -a -s '-screen 0 1440x1000x24' "$B" --gpu-backend opengl -t 2 -p 0 0 1320 900 "$OUT/cold-$SCALE/empty-panel.blend" --python tools/blender_gui_panel_startup_test.py > "$OUT/reopen-$SCALE.log" 2>&1
  for CASE in cold reopen; do
    python - "$OUT/$CASE-$SCALE/report.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]));assert r['status']=='passed',r
print('NATIVE_PANEL_CHECKS',r['ui_scale'],len(r['checks']),sys.argv[1])
PY
  done
done
if grep -E 'Traceback|Writing to ID|Python script error' "$OUT"/*.log; then exit 1; fi
printf 'PANEL_STARTUP_RUNTIME_OK\n'
