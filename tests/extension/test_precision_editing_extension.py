from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parents[2]
EXTENSION = ROOT / "extension" / "aludiy_designer"


def parse(relative: str) -> ast.Module:
    return ast.parse((EXTENSION / relative).read_text(encoding="utf-8"))


def _class(tree: ast.Module, name: str) -> ast.ClassDef:
    return next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name)


def _assigned_constant(class_node: ast.ClassDef, name: str):
    assignment = next(
        node
        for node in class_node.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == name
    )
    return ast.literal_eval(assignment.value)


def _method(class_node: ast.ClassDef, name: str) -> ast.FunctionDef:
    return next(
        node for node in class_node.body if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _called_names(function: ast.FunctionDef) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            parts = [target.attr]
            value = target.value
            while isinstance(value, ast.Attribute):
                parts.append(value.attr)
                value = value.value
            if isinstance(value, ast.Name):
                parts.append(value.id)
            names.add(".".join(reversed(parts)))
    return names


def test_runtime_exposes_active_node_selection_without_changing_member_selection() -> None:
    source = (EXTENSION / "runtime.py").read_text(encoding="utf-8")
    assert "def selected_node_ids" in source
    assert "def active_node_id" in source
    assert 'entity_id.startswith("N-")' in source
    assert 'entity_id.startswith("M-")' in source


def test_exact_edit_operators_use_core_mutations_and_undo() -> None:
    tree = parse("operators.py")
    expected = {
        "ALUDIY_OT_edit_active_node": ("aludiy.edit_active_node", "move_node"),
        "ALUDIY_OT_edit_member_endpoint": ("aludiy.edit_member_endpoint", "move_node"),
        "ALUDIY_OT_translate_active_member": (
            "aludiy.translate_active_member",
            "translate_member",
        ),
    }
    for class_name, (operator_id, mutation) in expected.items():
        operator = _class(tree, class_name)
        assert _assigned_constant(operator, "bl_idname") == operator_id
        assert "UNDO" in _assigned_constant(operator, "bl_options")
        execute = _method(operator, "execute")
        calls = _called_names(execute)
        assert mutation in calls
        assert "parse_distance_mm" in calls or "self._position" in calls
        assert "_editable_project" in calls
        assert "_commit_project_update" in calls


def test_endpoint_operator_supports_start_and_end() -> None:
    source = (EXTENSION / "operators.py").read_text(encoding="utf-8")
    assert '("START", "起点"' in source
    assert '("END", "终点"' in source
    assert "member.start_node_id" in source
    assert "member.end_node_id" in source


def test_selection_panel_exposes_node_endpoint_and_translation_controls() -> None:
    source = (EXTENSION / "panels.py").read_text(encoding="utf-8")
    for token in (
        'operator("aludiy.edit_active_node"',
        'operator("aludiy.edit_member_endpoint"',
        'operator("aludiy.translate_active_member"',
        "起点坐标",
        "终点坐标",
        "精确平移",
    ):
        assert token in source


def test_new_operator_classes_are_registered() -> None:
    source = (EXTENSION / "operators.py").read_text(encoding="utf-8")
    classes_block = source[source.index("CLASSES = (") :]
    for class_name in (
        "ALUDIY_OT_edit_active_node",
        "ALUDIY_OT_edit_member_endpoint",
        "ALUDIY_OT_translate_active_member",
    ):
        assert class_name in classes_block


def test_precise_edit_operators_use_transactional_project_commit() -> None:
    source = (EXTENSION / "operators.py").read_text(encoding="utf-8")
    assert "def _editable_project" in source
    assert "def _commit_project_update" in source
    assert "Project.from_dict(project.to_dict())" in source
    for class_name in (
        "ALUDIY_OT_edit_active_node",
        "ALUDIY_OT_edit_member_endpoint",
        "ALUDIY_OT_translate_active_member",
        "ALUDIY_OT_resize_active_member",
    ):
        tree = parse("operators.py")
        execute = _method(_class(tree, class_name), "execute")
        calls = _called_names(execute)
        assert "_editable_project" in calls
        assert "_commit_project_update" in calls
