from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).parents[2]
EXTENSION = ROOT / "extension" / "aludiy_designer"


def parse(relative: str) -> ast.Module:
    return ast.parse((EXTENSION / relative).read_text(encoding="utf-8"))


def class_names(module: ast.Module) -> set[str]:
    return {node.name for node in module.body if isinstance(node, ast.ClassDef)}


def function_names(module: ast.Module) -> set[str]:
    return {node.name for node in module.body if isinstance(node, ast.FunctionDef)}


def test_extension_entry_point_exposes_register_and_unregister() -> None:
    functions = function_names(parse("__init__.py"))
    assert {"register", "unregister"} <= functions


def test_operator_contract_contains_first_experience_actions() -> None:
    classes = class_names(parse("operators.py"))
    assert {
        "ALUDIY_OT_setup_workspace",
        "ALUDIY_OT_create_sample_frame",
        "ALUDIY_OT_draw_member",
        "ALUDIY_OT_resize_active_member",
        "ALUDIY_OT_change_active_profile",
        "ALUDIY_OT_rebuild_scene",
        "ALUDIY_OT_export_project",
        "ALUDIY_OT_import_project",
        "ALUDIY_OT_export_cutlist",
    } <= classes


def test_vendored_engineering_core_has_no_bpy_dependency() -> None:
    vendor = EXTENSION / "vendor" / "aludiy_core"
    files = sorted(vendor.glob("*.py"))
    assert files
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        assert "bpy" not in imported, path


def test_scene_adapter_declares_single_mm_to_m_boundary() -> None:
    tree = parse("scene_adapter.py")
    assignments = {
        target.id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance((target := node.targets[0]), ast.Name)
        and isinstance(node.value, ast.Constant)
    }
    assert assignments["MM_TO_M"] == 0.001


def test_all_extension_python_files_compile() -> None:
    for path in EXTENSION.rglob("*.py"):
        compile(path.read_text(encoding="utf-8"), str(path), "exec")


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


def test_cache_cleanup_removes_object_and_orphan_mesh_data() -> None:
    adapter = parse("scene_adapter.py")
    operators = parse("operators.py")
    adapter_functions = {
        node.name: node for node in adapter.body if isinstance(node, ast.FunctionDef)
    }
    operator_functions = {
        node.name: node for node in operators.body if isinstance(node, ast.FunctionDef)
    }

    assert "remove_object_and_orphan_data" in adapter_functions
    helper_calls = _called_names(adapter_functions["remove_object_and_orphan_data"])
    assert "bpy.data.objects.remove" in helper_calls
    assert "bpy.data.meshes.remove" in helper_calls
    assert "remove_object_and_orphan_data" in _called_names(
        adapter_functions["_remove_managed_objects"]
    )
    assert "scene_adapter.remove_object_and_orphan_data" in _called_names(
        operator_functions["_remove_preview"]
    )
