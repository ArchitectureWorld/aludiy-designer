"""Fresh-process verification of saved engineering data and rail UI state."""
import json
import os
import sys
from pathlib import Path
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'extension'))
import aludiy_designer as addon
addon.register()
from aludiy_designer import runtime, slot_tools
from aludiy_designer.vendor.aludiy_core.snapping import engineering_candidates

folder = Path(os.environ['ALUDIY_EVIDENCE_DIR'])
scene = bpy.context.scene
project = runtime.get_project(scene)
assert project.to_dict() == json.loads((folder / 'expected.aludiy.json').read_text())
expected = tuple(tuple(pair) for pair in json.loads((folder / 'expected-targets.json').read_text()))
assert slot_tools.target_specs(scene, project) == expected
assert slot_tools.choice_pairs(scene) == expected
assert not runtime.settings(scene).slot_only
before = runtime.settings(scene).project_json
point = project.nodes['N-009'].position_mm
candidates = engineering_candidates(
    project, origin_mm=(0,0,0), cursor_px=(point[0],point[2]),
    project_point=lambda v:(v[0],v[2]), ray_origin_mm=(point[0],-2000,point[2]),
    ray_direction=(0,1,0), catalog=runtime.get_catalog(),
    slot_targets=expected)
assert any(c.node_id == 'N-009' for c in candidates)
assert runtime.settings(scene).project_json == before
print('MULTI_SLOT_REOPEN_OK', runtime.EXTENSION_VERSION, len(expected))
addon.unregister()
