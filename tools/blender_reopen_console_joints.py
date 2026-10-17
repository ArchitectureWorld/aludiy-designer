"""Fresh-process checks of released slot endpoints and valid processing rules."""
import sys,os,json
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'extension'))
import aludiy_designer as addon
addon.register()
from aludiy_designer import runtime
from aludiy_designer.vendor.aludiy_core.movement import preview_move
from aludiy_designer.vendor.aludiy_core.joints import solve_cutbacks
p=runtime.get_project(bpy.context.scene)
folder=Path(os.environ['ALUDIY_EVIDENCE_DIR']);case=os.environ['ALUDIY_REOPEN_CASE']
expected=folder/('released.aludiy.json' if case=='released' else 'expected.aludiy.json')
assert p.to_dict()==json.loads(expected.read_text())
if case=='released':
 assert len(p.associations)==1
 q=preview_move(p,(50,0,0),endpoint=('M-002','START')).project
 assert q.nodes['N-003'].position_mm[0]==p.nodes['N-003'].position_mm[0]+50
else:
 assert len(p.joints)==2 and p.schema_version=='0.4.0'
 assert solve_cutbacks(p,runtime.get_catalog(),strict=True).lengths['M-002'].cut_length_mm==480
print('CONSOLE_JOINT_REOPEN_OK',case)
addon.unregister()
