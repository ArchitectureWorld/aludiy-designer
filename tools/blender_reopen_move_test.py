"""Verify saved GUI movement state in a fresh Blender process."""
from pathlib import Path
import json, os, sys
import bpy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'extension'))
import aludiy_designer as addon
from aludiy_designer import runtime,scene_adapter
folder=Path(os.environ['ALUDIY_EVIDENCE_DIR'])
addon.register()
try:
    expected=json.loads((folder/'expected.aludiy.json').read_text())
    p=runtime.get_project(bpy.context.scene)
    assert p.to_dict()==expected
    scene_adapter.rebuild_scene(bpy.context.scene,p,runtime.get_catalog())
    p2=runtime.get_project(bpy.context.scene)
    assert p2.to_dict()==expected
    assert len(p2.nodes)==5 and p2.nodes['N-001'].position_mm==(0,0,800)
    new=p2.members['M-003'].end_node_id
    assert new!='N-001' and p2.nodes[new].position_mm==(0,0,900)
    print('ALUDIY_MOVE_REOPEN_OK: exact saved project, detached topology, rebuilt caches')
finally:
    addon.unregister()
