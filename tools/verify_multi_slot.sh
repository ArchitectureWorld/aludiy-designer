#!/usr/bin/env bash
# Separate suite: avoid double-counting retained checks.
set -euo pipefail
B="${1:?Blender executable}"; OUT="${2:?Evidence directory}"
mkdir -p "$OUT"; OUT="$(cd "$OUT" && pwd)"
export LIBGL_ALWAYS_SOFTWARE=1 BLENDER_USER_CONFIG="$OUT/config"
mkdir -p "$BLENDER_USER_CONFIG"
"$B" -b -t 2 --factory-startup --python-expr 'import bpy;bpy.context.preferences.view.show_splash=False;bpy.context.preferences.view.smooth_view=0;bpy.ops.wm.save_userpref()' > "$OUT/prefs.log" 2>&1
for SCALE in 1 1.5; do
  export ALUDIY_TEST_UI_SCALE="$SCALE" ALUDIY_EVIDENCE_DIR="$OUT/multi-$SCALE"
  timeout -k 5s 180s xvfb-run -a -s '-screen 0 1800x1100x24' "$B" --gpu-backend opengl -t 2 -p 0 0 1680 1000 --python tools/blender_gui_multi_slot_test.py > "$OUT/multi-$SCALE.log" 2>&1
  python - "$ALUDIY_EVIDENCE_DIR/report.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]));assert r['status']=='passed',r
print('MULTI_SLOT_CHECKS',r['ui_scale'],len(r['checks']))
PY
  if grep -E 'Traceback|Python script error|AluDIY action wheel:|AluDIY section inspector:|AluDIY direction overlay warning:' "$OUT/multi-$SCALE.log"; then exit 1; fi
  timeout -k 5s 45s "$B" -b "$ALUDIY_EVIDENCE_DIR/multi-slot.blend" -t 2 --python-exit-code 1 --python tools/blender_reopen_multi_slot.py > "$OUT/multi-$SCALE-reopen.log" 2>&1
  grep MULTI_SLOT_REOPEN_OK "$OUT/multi-$SCALE-reopen.log"
done
printf 'MULTI_SLOT_RUNTIME_OK\n'
