from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parents[2]
EXTENSION = ROOT / "extension" / "aludiy_designer"


def parse(relative: str) -> ast.Module:
    return ast.parse((EXTENSION / relative).read_text(encoding="utf-8"))


def _class(tree: ast.Module, name: str) -> ast.ClassDef:
    return next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name)


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    return next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)


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


def test_engineering_delete_operator_mutates_project_and_rebuilds_cache() -> None:
    tree = parse("operators.py")
    operator = _class(tree, "ALUDIY_OT_delete_selected_members")

    assert _assigned_constant(operator, "bl_idname") == "aludiy.delete_selected_members"
    assert "UNDO" in _assigned_constant(operator, "bl_options")

    execute = next(
        node for node in operator.body if isinstance(node, ast.FunctionDef) and node.name == "execute"
    )
    calls = _called_names(execute)
    assert "project.remove_members" in calls
    assert "set_project" in calls
    assert "scene_adapter.rebuild_scene" in calls


def test_engineering_delete_is_exposed_in_panel() -> None:
    source = (EXTENSION / "panels.py").read_text(encoding="utf-8")
    assert 'operator("aludiy.delete_selected_members"' in source
    assert "Ctrl + Shift + Delete" in source


def test_keymap_uses_only_ctrl_shift_delete_for_engineering_delete() -> None:
    tree = parse("operators.py")
    function = _function(tree, "register_keymaps")
    matching_calls = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "new"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "aludiy.delete_selected_members"
    ]
    assert len(matching_calls) == 1
    call = matching_calls[0]
    keywords = {keyword.arg: ast.literal_eval(keyword.value) for keyword in call.keywords}
    assert keywords == {
        "type": "DEL",
        "value": "PRESS",
        "ctrl": True,
        "shift": True,
    }


def test_entry_point_registers_and_unregisters_delete_keymap_as_optional_service() -> None:
    source = (EXTENSION / "__init__.py").read_text(encoding="utf-8")
    assert '("工程删除快捷键", operators.register_keymaps)' in source
    assert "operators.unregister_keymaps()" in source
