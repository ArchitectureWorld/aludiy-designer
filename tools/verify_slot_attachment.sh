#!/usr/bin/env bash
set -euo pipefail
B="${1:?Blender executable required}";OUT="${2:?Evidence directory required}"
mkdir -p "$OUT";OUT="$(cd "$OUT" && pwd)"
bash tools/verify_profile_orientation.sh "$B" "$OUT/retained"
bash tools/verify_workspace_sync.sh "$B" "$OUT/workspace"
export BLENDER_USER_CONFIG="$OUT/workspace/config" LIBGL_ALWAYS_SOFTWARE=1 ALUDIY_EVIDENCE_DIR="$OUT/slot"
mkdir -p "$ALUDIY_EVIDENCE_DIR"
timeout -k 5s 120s xvfb-run -a -s '-screen 0 1800x1100x24' "$B" --gpu-backend opengl -t 2 -p 0 0 1680 1000 --python tools/blender_gui_slot_test.py > "$OUT/slot-gui.log" 2>&1
python - "$ALUDIY_EVIDENCE_DIR/report.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]));assert r['status']=='passed',r
print('SLOT_GUI_CHECKS',len(r['checks']))
PY
if grep -E 'Traceback|Python script error|AluDIY slot target overlay:|AluDIY section inspector:' "$OUT/slot-gui.log"; then exit 1; fi
timeout -k 5s 40s "$B" -t 2 -b "$ALUDIY_EVIDENCE_DIR/slot-attachment.blend" --python-exit-code 1 --python-expr 'import sys,os,json;from pathlib import Path;sys.path.insert(0,str(Path("extension").resolve()));import aludiy_designer as a;a.register();import bpy;from aludiy_designer import runtime;assert runtime.get_project(bpy.context.scene).to_dict()==json.load(open(Path(os.environ["ALUDIY_EVIDENCE_DIR"])/"expected.aludiy.json"));print("SLOT_FRESH_PROCESS_REOPEN_OK");a.unregister()' > "$OUT/slot-reopen.log" 2>&1
grep SLOT_FRESH_PROCESS_REOPEN_OK "$OUT/slot-reopen.log"
printf 'SLOT_ATTACHMENT_RUNTIME_OK\n'
