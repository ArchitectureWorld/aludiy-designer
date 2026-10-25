import sys,json,os
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'extension'))
import aludiy_designer as addon
addon.register()
from aludiy_designer import runtime,joint_editor
from aludiy_designer.vendor.aludiy_core.joint_editor import joint_choices
out=Path(os.environ['ALUDIY_EVIDENCE_DIR'])
p=runtime.get_project(bpy.context.scene)
assert p.to_dict()==json.loads((out/'expected.aludiy.json').read_text())
assert len(p.joints)==2 and not p.associations
assert all(o.valid for o in joint_choices(p,runtime.get_catalog(),member_ids=p.members))
assert joint_editor._ACTIVE is None and joint_editor._HANDLE is None
print('JOINT_EDITOR_REOPEN_OK')
addon.unregister()
