#!/usr/bin/env bash
set -euo pipefail
B="${1:?Blender executable}"; OUT="${2:?Evidence directory}"
mkdir -p "$OUT"; OUT="$(cd "$OUT" && pwd)"
bash tools/verify_section_ui.sh "$B" "$OUT/retained"
export LIBGL_ALWAYS_SOFTWARE=1 BLENDER_USER_CONFIG="$OUT/retained/retained/workspace/config"
for SCALE in 1 1.5; do
  export ALUDIY_TEST_UI_SCALE="$SCALE" ALUDIY_EVIDENCE_DIR="$OUT/console-$SCALE"
  mkdir -p "$ALUDIY_EVIDENCE_DIR"
  timeout -k 5s 160s xvfb-run -a -s '-screen 0 1800x1100x24' "$B" --gpu-backend opengl -t 2 -p 0 0 1680 1000 --python tools/blender_gui_console_joint_test.py > "$OUT/console-$SCALE.log" 2>&1
  python - "$ALUDIY_EVIDENCE_DIR/report.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]));assert r['status']=='passed',r
print('CONSOLE_JOINT_CHECKS',r['ui_scale'],len(r['checks']))
PY
  if grep -E 'Traceback|Python script error|AluDIY section inspector:|AluDIY direction overlay warning:' "$OUT/console-$SCALE.log"; then exit 1; fi
  for CASE in released console-joints; do
    export ALUDIY_REOPEN_CASE="$CASE"
    timeout -k 5s 40s "$B" -b "$ALUDIY_EVIDENCE_DIR/$CASE.blend" -t 2 --python-exit-code 1 --python tools/blender_reopen_console_joints.py > "$OUT/console-$SCALE-$CASE-reopen.log" 2>&1
    grep CONSOLE_JOINT_REOPEN_OK "$OUT/console-$SCALE-$CASE-reopen.log"
  done
done
printf 'CONSOLE_JOINT_RUNTIME_OK\n'
