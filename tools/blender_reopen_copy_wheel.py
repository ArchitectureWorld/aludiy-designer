"""Check independent copy identities in a fresh Blender process after saving."""
import os, sys, json
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'extension'))
import aludiy_designer as addon
addon.register()
from aludiy_designer import runtime
from aludiy_designer.vendor.aludiy_core.movement import duplicate_members,preview_move
folder=Path(os.environ['ALUDIY_EVIDENCE_DIR'])
p=runtime.get_project(bpy.context.scene)
expected=json.loads((folder/'expected.aludiy.json').read_text())
assert p.to_dict()==expected
copy=duplicate_members(p,p.members)
assert not set(copy.member_map.values()).intersection(p.members)
assert not set(copy.node_map.values()).intersection(p.nodes)
q=preview_move(copy.project,(100,200,300),member_ids=copy.member_map.values()).project
assert all(q.nodes[n].position_mm==node.position_mm for n,node in p.nodes.items())
assert runtime.get_project(bpy.context.scene).to_dict()==expected
assert 'duplicate' in bpy.ops.aludiy.move_engineering.get_rna_type().properties
print('COPY_WHEEL_REOPEN_OK',runtime.EXTENSION_VERSION)
addon.unregister()
