#!/usr/bin/env bash
# Run every retained manual/movement/sample story plus the new drawing stories.
set -euo pipefail
B="${1:?Blender path required}"; OUT="${2:?Evidence path required}"
mkdir -p "$OUT"; OUT="$(cd "$OUT" && pwd)"
bash tools/verify_manual_associations.sh "$B" "$OUT/regression"
export BLENDER_USER_CONFIG="$OUT/regression/config" LIBGL_ALWAYS_SOFTWARE=1
export ALUDIY_EVIDENCE_DIR="$OUT/drawing"
mkdir -p "$ALUDIY_EVIDENCE_DIR"
timeout -k 5s 150s xvfb-run -a -s '-screen 0 1800x1100x24' "$B" --gpu-backend opengl -t 2 -p 0 0 1680 1000 --python tools/blender_gui_drawing_snap_test.py > "$OUT/drawing-gui.log" 2>&1
python - "$ALUDIY_EVIDENCE_DIR/report.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]));assert r['status']=='passed',r
print('DRAWING_CHECKS',len(r['checks']))
PY
if grep -E 'Traceback|Python script error|AluDIY endpoint overlay:' "$OUT/drawing-gui.log"; then exit 1; fi
timeout -k 5s 40s "$B" -t 2 -b "$ALUDIY_EVIDENCE_DIR/drawing-demo.blend" --python-exit-code 1 --python-expr 'import sys,json,os;from pathlib import Path;sys.path.insert(0,str(Path("extension").resolve()));import aludiy_designer as a;a.register();import bpy;from aludiy_designer import runtime;assert runtime.get_project(bpy.context.scene).to_dict()==json.load(open(Path(os.environ["ALUDIY_EVIDENCE_DIR"])/"expected.aludiy.json"));print("DRAWING_FRESH_PROCESS_REOPEN_OK",flush=True);a.unregister()' > "$OUT/drawing-reopen.log" 2>&1
printf 'UNIFIED_DRAWING_RUNTIME_OK\n'
