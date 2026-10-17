"""Execute the real runtime read path with an RNA write tripwire."""
from __future__ import annotations
import ast
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from aludiy_core import Project

ROOT = Path(__file__).resolve().parents[2]

class ReadOnlySettings:
    def __init__(self, raw):
        self._raw = raw
    @property
    def project_json(self):
        return self._raw
    @project_json.setter
    def project_json(self, value):
        pytest.fail('A project read attempted an RNA data write')


def reader(raw):
    tree = ast.parse((ROOT/'extension/aludiy_designer/runtime.py').read_text())
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name in {'get_project','set_project'}]
    state = ReadOnlySettings(raw)
    ns = dict(json=json, Project=Project, settings=lambda scene: state,
              empty_project=lambda: Project('P-BLENDER-001','alpha-2026.10'))
    # The relative import used by valid projects is exercised in real Blender;
    # for the empty-reader tripwire replace set_project by an equally strict writer.
    def forbidden_write(scene, project):
        state.project_json = json.dumps(project.to_dict())
    exec(compile(ast.Module(body=[n for n in functions if n.name=='get_project'], type_ignores=[]),
                 '<actual-get-project>', 'exec'), ns)
    ns['set_project'] = forbidden_write
    return ns['get_project'], state

@pytest.mark.parametrize('raw', ['', ' ', '\n\t'])
def test_empty_project_read_is_read_only(raw):
    get, state = reader(raw)
    p = get(object())
    assert isinstance(p, Project) and not p.members
    assert state.project_json == raw


def test_empty_reads_do_not_share_mutable_project_state():
    get, _ = reader('')
    a, b = get(object()), get(object())
    assert a is not b
    a.project_id = 'not-persisted'
    assert b.project_id == 'P-BLENDER-001'

@pytest.mark.parametrize('raw', ['{bad-json', '{"schema_version":"999.0.0"}'])
def test_invalid_nonempty_data_is_not_replaced_by_empty_project(raw):
    get, state = reader(raw)
    with pytest.raises((ValueError, KeyError, TypeError)):
        get(object())
    assert state.project_json == raw
