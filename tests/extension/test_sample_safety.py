"""Execute the real operator bodies with a small Blender data-boundary fake."""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from aludiy_core import io
from aludiy_core.model import Project
from aludiy_core.units import parse_length_mm

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def setup():
    tree = ast.parse((ROOT / 'extension/aludiy_designer/operators.py').read_text(encoding='utf-8'))
    names = {'_editable_project', '_commit_project_update', 'ALUDIY_OT_create_sample_frame', 'ALUDIY_OT_new_project'}
    selected = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
    p = io.create_sample_frame(900, 500, 'generic:tslot-2020@0.1', project_id='P-USER-DRAWN', catalog_revision='my-catalog')
    p.members['M-001'].revision = 7
    p.members['M-001'].roll_deg = 90
    scene = SimpleNamespace(payload=p.to_dict(), sample_width_input='1200', sample_depth_input='600', cursor=SimpleNamespace(location=(0.7, 1.2, 0.8)))
    state = SimpleNamespace(cache=p.to_dict(), fail_next_rebuild=False, confirmed=[])

    def get_project(s):
        return Project.from_dict(s.payload)

    def set_project(s, project):
        s.payload = project.to_dict()

    def rebuild(s, project, catalog):
        if state.fail_next_rebuild:
            state.fail_next_rebuild = False
            raise RuntimeError('injected cache failure')
        state.cache = project.to_dict()

    def confirm(*args, **kwargs):
        state.confirmed.append(kwargs)
        return {'RUNNING_MODAL'}

    class Operator:
        def report(self, *args):
            pass

    ns = {
        'bpy': SimpleNamespace(types=SimpleNamespace(Operator=Operator, Context=object)),
        'Project': Project,
        'get_project': get_project,
        'set_project': set_project,
        'settings': lambda s: s,
        'set_status': lambda *args: None,
        'get_catalog': lambda: SimpleNamespace(get=lambda profile: None),
        '_selected_profile': lambda s: 'generic:tslot-2040@0.1',
        'create_sample_frame': io.create_sample_frame,
        'append_sample_frame': getattr(io, 'append_sample_frame', None),
        'empty_project': lambda: Project('P-NEW', 'alpha-2026.10'),
        'parse_length_mm': parse_length_mm,
        'scene_adapter': SimpleNamespace(rebuild_scene=rebuild, select_entity=lambda *args: None, MM_TO_M=0.001),
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), '<real-sample-operator>', 'exec'), ns)
    context = SimpleNamespace(scene=scene, view_layer=object(), mode='OBJECT', window_manager=SimpleNamespace(invoke_confirm=confirm))
    return context, state, ns


def test_sample_keeps_existing_engineering_data(setup):
    context, state, ns = setup
    before = context.scene.payload
    assert ns['ALUDIY_OT_create_sample_frame']().execute(context) == {'FINISHED'}
    after = context.scene.payload
    assert after['project_id'] == before['project_id'], 'Sample replaced the user project'
    assert after['catalog_revision'] == before['catalog_revision']
    assert len(after['members']) == len(before['members']) + 4
    assert len(after['nodes']) == len(before['nodes']) + 8
    assert all(item in after['members'] for item in before['members'])
    assert all(item in after['nodes'] for item in before['nodes'])
    assert state.cache == after


def test_repeated_sample_inserts_have_distinct_ids_and_no_auto_weld(setup):
    context, state, ns = setup
    context.scene.cursor.location = (0.0, 0.0, 0.0)
    op = ns['ALUDIY_OT_create_sample_frame']()
    assert op.execute(context) == {'FINISHED'}
    first = context.scene.payload
    assert op.execute(context) == {'FINISHED'}
    after = context.scene.payload
    assert len(after['members']) == 12 and len(after['nodes']) == 20
    assert all(item in after['members'] for item in first['members'])
    assert len({item['id'] for item in after['members'] + after['nodes']}) == 32


def test_insert_uses_3d_cursor_in_millimetres(setup):
    context, state, ns = setup
    old_ids = {n['id'] for n in context.scene.payload['nodes']}
    assert ns['ALUDIY_OT_create_sample_frame']().execute(context) == {'FINISHED'}
    points = {tuple(n['position_mm']) for n in context.scene.payload['nodes'] if n['id'] not in old_ids}
    assert points == {(700.0, 1200.0, 800.0), (1900.0, 1200.0, 800.0), (1900.0, 1800.0, 800.0), (700.0, 1800.0, 800.0)}


def test_sample_rebuild_failure_rolls_back_data_and_cache(setup):
    context, state, ns = setup
    before = context.scene.payload
    state.fail_next_rebuild = True
    assert ns['ALUDIY_OT_create_sample_frame']().execute(context) == {'CANCELLED'}
    assert context.scene.payload == before
    assert state.cache == before


@pytest.mark.parametrize('text', ['-20', '0', 'nan', 'invalid'])
def test_invalid_dimensions_leave_project_unchanged(setup, text):
    context, state, ns = setup
    before = context.scene.payload
    context.scene.sample_width_input = text
    assert ns['ALUDIY_OT_create_sample_frame']().execute(context) == {'CANCELLED'}
    assert context.scene.payload == before and state.cache == before


def test_new_project_invoke_requires_explicit_confirmation(setup):
    context, state, ns = setup
    before = context.scene.payload
    op = ns['ALUDIY_OT_new_project']()
    assert hasattr(op, 'invoke'), 'Reset has no UI confirmation'
    assert op.invoke(context, object()) == {'RUNNING_MODAL'}
    assert context.scene.payload == before and state.cache == before
    assert len(state.confirmed) == 1


def test_new_project_rebuild_failure_rolls_back(setup):
    context, state, ns = setup
    before = context.scene.payload
    state.fail_next_rebuild = True
    assert ns['ALUDIY_OT_new_project']().execute(context) == {'CANCELLED'}
    assert context.scene.payload == before and state.cache == before


def test_confirmed_new_project_clears_transient_slot_ui_only_after_success(setup):
    context,state,ns=setup
    state.clear_calls=0
    def clear(scene):
        state.clear_calls+=1
    ns['runtime']=SimpleNamespace(clear_slot_ui=clear)
    assert ns['ALUDIY_OT_new_project']().execute(context)=={'FINISHED'}
    assert state.clear_calls==1


def test_failed_new_project_preserves_transient_slot_ui(setup):
    context,state,ns=setup
    state.clear_calls=0;state.fail_next_rebuild=True
    ns['runtime']=SimpleNamespace(clear_slot_ui=lambda scene:setattr(state,'clear_calls',state.clear_calls+1))
    assert ns['ALUDIY_OT_new_project']().execute(context)=={'CANCELLED'}
    assert state.clear_calls==0
