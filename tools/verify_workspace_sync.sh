#!/usr/bin/env bash
# Verify the repaired lifecycle itself, not a manually prepared ALU DIY workspace.
set -euo pipefail
B="${1:?Blender executable required}"; OUT="${2:?Evidence path required}"
mkdir -p "$OUT"; OUT="$(cd "$OUT" && pwd)"
export BLENDER_USER_CONFIG="$OUT/config" LIBGL_ALWAYS_SOFTWARE=1
mkdir -p "$BLENDER_USER_CONFIG"
"$B" -t 2 -b --factory-startup --python-expr 'import bpy;bpy.context.preferences.view.show_splash=False;bpy.context.preferences.view.smooth_view=0;bpy.ops.wm.save_userpref()' > "$OUT/prefs.log" 2>&1
for projection in PERSP ORTHO; do
  export ALUDIY_EVIDENCE_DIR="$OUT/$projection" ALUDIY_INITIAL_PROJECTION="$projection"
  mkdir -p "$ALUDIY_EVIDENCE_DIR"
  timeout -k 5s 90s xvfb-run -a -s '-screen 0 1800x1100x24' "$B" --gpu-backend opengl -t 2 -p 0 0 1680 1000 --python tools/blender_gui_workspace_test.py > "$OUT/$projection.log" 2>&1
  python - "$ALUDIY_EVIDENCE_DIR/report.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]));assert r['status']=='passed',r
print('WORKSPACE_CHECKS',len(r['checks']),sys.argv[1])
PY
  for file in workspace-sync workspace-legacy; do
    timeout -k 5s 40s xvfb-run -a -s '-screen 0 1800x1100x24' "$B" --gpu-backend opengl -t 2 -p 0 0 1680 1000 "$ALUDIY_EVIDENCE_DIR/$file.blend" --python tools/blender_workspace_reopen_test.py > "$OUT/$projection-$file-reopen.log" 2>&1
    grep WORKSPACE_FRESH_GUI_REOPEN_OK "$OUT/$projection-$file-reopen.log"
  done
done
if grep -E 'Traceback|Python script error|AluDIY workspace setup warning:|AluDIY view synchronization warning:' "$OUT"/*.log; then exit 1; fi
printf 'WORKSPACE_SYNC_RUNTIME_OK\n'
