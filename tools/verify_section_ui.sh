#!/usr/bin/env bash
set -euo pipefail
B="${1:?Blender executable required}"; OUT="${2:?Evidence directory required}"
mkdir -p "$OUT";OUT="$(cd "$OUT" && pwd)"
bash tools/verify_slot_attachment.sh "$B" "$OUT/retained"
export BLENDER_USER_CONFIG="$OUT/retained/workspace/config" LIBGL_ALWAYS_SOFTWARE=1
for SCALE in 1 1.5; do
    export ALUDIY_TEST_UI_SCALE="$SCALE" ALUDIY_EVIDENCE_DIR="$OUT/section-$SCALE"
    mkdir -p "$ALUDIY_EVIDENCE_DIR"
    timeout -k 5s 120s xvfb-run -a -s '-screen 0 1800x1100x24' "$B" --gpu-backend opengl -t 2 -p 0 0 1680 1000 --python tools/blender_gui_section_ui_test.py > "$OUT/section-$SCALE.log" 2>&1
    python - "$ALUDIY_EVIDENCE_DIR/report.json" <<'PY'
import sys,json
r=json.load(open(sys.argv[1]));assert r['status']=='passed',r
print('SECTION_UI_CHECKS',r['ui_scale'],len(r['checks']))
PY
    if grep -E 'Traceback|Python script error|AluDIY section inspector:|AluDIY endpoint overlay:|AluDIY direction overlay warning:' "$OUT/section-$SCALE.log"; then exit 1; fi
    timeout -k 5s 40s "$B" -t 2 -b "$ALUDIY_EVIDENCE_DIR/section-ui.blend" --python-exit-code 1 --python-expr 'import sys,os,json;from pathlib import Path;sys.path.insert(0,str(Path("extension").resolve()));import aludiy_designer as a;a.register();import bpy;from aludiy_designer import runtime;assert runtime.get_project(bpy.context.scene).to_dict()==json.load(open(Path(os.environ["ALUDIY_EVIDENCE_DIR"])/"expected.aludiy.json"));assert runtime.settings(bpy.context.scene).show_selection_lengths;print("SECTION_UI_FRESH_PROCESS_REOPEN_OK");a.unregister()' > "$OUT/section-$SCALE-reopen.log" 2>&1
    grep SECTION_UI_FRESH_PROCESS_REOPEN_OK "$OUT/section-$SCALE-reopen.log"
done
printf 'SECTION_UI_RUNTIME_OK\n'
