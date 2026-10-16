"""Check confirmed snap connectivity in a fresh Blender process."""
from pathlib import Path
import os,sys,json
import bpy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'extension'))
import aludiy_designer as addon
from aludiy_designer import runtime,scene_adapter
from aludiy_designer.vendor.aludiy_core.movement import preview_move
folder=Path(os.environ['ALUDIY_EVIDENCE_DIR'])
addon.register()
try:
    expected=json.loads((folder/'expected.aludiy.json').read_text())
    p=runtime.get_project(bpy.context.scene)
    assert p.to_dict()==expected
    assert p.members['M-003'].end_node_id=='N-001' and 'N-007' not in p.nodes
    propagated=preview_move(p,(0,0,100),node_ids=['N-001'])
    assert set(propagated.affected_member_ids)=={'M-001','M-002','M-003'}
    scene_adapter.rebuild_scene(bpy.context.scene,p,runtime.get_catalog())
    assert runtime.get_project(bpy.context.scene).to_dict()==expected
    print('ALUDIY_SNAP_REOPEN_OK: saved_project,shared_node,propagation,rebuilt_caches')
finally: addon.unregister()
