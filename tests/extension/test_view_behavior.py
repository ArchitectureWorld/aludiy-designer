from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parents[2]
EXTENSION = ROOT / "extension" / "aludiy_designer"


def parse(relative: str) -> ast.Module:
    return ast.parse((EXTENSION / relative).read_text(encoding="utf-8"))


def _class(tree: ast.Module, name: str) -> ast.ClassDef:
    return next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name)


def _enum_default(tree: ast.Module, property_name: str) -> str:
    settings_class = _class(tree, "AluDIYSceneSettings")
    assignment = next(
        node
        for node in settings_class.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == property_name
    )
    call = assignment.value if isinstance(assignment.value, ast.Call) else assignment.annotation
    assert isinstance(call, ast.Call)
    default = next(
        keyword.value
        for keyword in call.keywords
        if keyword.arg == "default"
    )
    assert isinstance(default, ast.Constant)
    return str(default.value)


def _called_attributes(function: ast.FunctionDef) -> set[str]:
    values: set[str] = set()
    for node in ast.walk(function):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            parts = [node.func.attr]
            value = node.func.value
            while isinstance(value, ast.Attribute):
                parts.append(value.attr)
                value = value.value
            if isinstance(value, ast.Name):
                parts.append(value.id)
            values.add(".".join(reversed(parts)))
    return values


def test_view_sync_defaults_to_full_zoom_linking() -> None:
    runtime = parse("runtime.py")
    view_sync = parse("view_sync.py")

    assert _enum_default(runtime, "view_sync_mode") == "FULL"
    copy_view = next(
        node for node in view_sync.body if isinstance(node, ast.FunctionDef) and node.name == "_copy_view"
    )
    assignments = {
        ast.unparse(node.targets[0]): ast.unparse(node.value)
        for node in ast.walk(copy_view)
        if isinstance(node, ast.Assign) and len(node.targets) == 1
    }
    assert assignments["target_region.view_distance"] == "source_region.view_distance"
    source = (EXTENSION / "view_sync.py").read_text(encoding="utf-8")
    assert 'settings(context.scene).view_sync_mode = "FULL"' in source


def test_dual_view_setup_uses_per_viewport_collection_isolation() -> None:
    view_sync = parse("view_sync.py")
    functions = {
        node.name: node for node in view_sync.body if isinstance(node, ast.FunctionDef)
    }

    assert "_configure_view_collections" in functions
    calls = _called_attributes(functions["_isolate_collections"])
    assert "bpy.ops.object.hide_collection" in calls
    source = (EXTENSION / "view_sync.py").read_text(encoding="utf-8")
    assert "use_local_collections" in source
    assert "AXIS_COLLECTION" in source
    assert "SOLID_COLLECTION" in source
    assert "HELPER_COLLECTION" in source
    assert '_isolate_collections(window, left, (AXIS_COLLECTION, HELPER_COLLECTION))' in source
    assert '_isolate_collections(window, right, (SOLID_COLLECTION,))' in source


def test_solid_display_mode_is_exposed_and_defaults_to_box() -> None:
    runtime = parse("runtime.py")
    assert _enum_default(runtime, "solid_display_mode") == "BOX"

    panels_source = (EXTENSION / "panels.py").read_text(encoding="utf-8")
    adapter_source = (EXTENSION / "scene_adapter.py").read_text(encoding="utf-8")
    assert 'prop(scene_settings, "solid_display_mode")' in panels_source
    assert "derive_member_mesh" in adapter_source
