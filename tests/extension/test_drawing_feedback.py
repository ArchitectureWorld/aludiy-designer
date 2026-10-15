from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parents[2]
EXTENSION = ROOT / "extension" / "aludiy_designer"


def parse(relative: str) -> ast.Module:
    return ast.parse((EXTENSION / relative).read_text(encoding="utf-8"))


def _called_names(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
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


def _class_method(tree: ast.Module, class_name: str, method_name: str) -> ast.FunctionDef:
    class_node = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    return next(
        node
        for node in class_node.body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )


def test_line_direction_overlay_uses_green_to_red_gradient_and_endpoint_points() -> None:
    overlay = EXTENSION / "viewport_overlay.py"
    assert overlay.is_file()
    source = overlay.read_text(encoding="utf-8")

    assert 'from_builtin("POLYLINE_SMOOTH_COLOR")' in source
    assert 'from_builtin("POINT_FLAT_COLOR")' in source
    assert "START_COLOR" in source
    assert "END_COLOR" in source
    assert "location_3d_to_region_2d" in source
    assert "register_direction_overlay" in source
    assert "unregister_direction_overlay" in source


def test_extension_registers_and_unregisters_persistent_direction_overlay() -> None:
    init_source = (EXTENSION / "__init__.py").read_text(encoding="utf-8")
    assert "viewport_overlay.register_direction_overlay()" in init_source
    assert "viewport_overlay.unregister_direction_overlay()" in init_source


def test_draw_member_operator_uses_crosshair_and_modal_feedback_handler() -> None:
    tree = parse("operators.py")
    invoke = _class_method(tree, "ALUDIY_OT_draw_member", "invoke")
    modal = _class_method(tree, "ALUDIY_OT_draw_member", "modal")
    invoke_calls = _called_names(invoke)
    modal_calls = _called_names(modal)

    assert "context.window.cursor_modal_set" in invoke_calls
    assert "_overlay_module" in invoke_calls
    assert "add_draw_feedback" in invoke_calls
    assert "_remove_draw_feedback_safely" in modal_calls
    assert "context.window.cursor_modal_restore" in modal_calls


def test_rhino_style_feedback_has_cursor_snap_coordinates_length_and_angle() -> None:
    source = (EXTENSION / "viewport_overlay.py").read_text(encoding="utf-8")
    for token in (
        "draw_crosshair",
        "draw_snap_marker",
        "format_coordinate_label",
        "format_measurement_label",
        "typed_text",
        "angle_deg",
        "length_mm",
    ):
        assert token in source


def test_line_view_helper_distinguishes_left_engineering_view() -> None:
    source = (EXTENSION / "view_sync.py").read_text(encoding="utf-8")
    assert "def is_line_view_area" in source
    assert "def is_line_view_context" in source


def test_draw_operator_resolves_window_region_even_when_started_from_sidebar() -> None:
    source = (EXTENSION / "operators.py").read_text(encoding="utf-8")
    assert "def _window_region" in source
    assert "event.mouse_x - region.x" in source
    assert "event.mouse_y - region.y" in source
    assert "self._source_region_pointer = window_region.as_pointer()" in source


def test_draw_member_is_restricted_to_left_line_view_in_aludiy_workspace() -> None:
    source = (EXTENSION / "operators.py").read_text(encoding="utf-8")
    assert "view_sync.is_line_view_context(context)" in source
    panels = (EXTENSION / "panels.py").read_text(encoding="utf-8")
    assert "请在线图视窗启动画线" in panels


def test_typed_length_updates_preview_without_waiting_for_mouse_move() -> None:
    source = (EXTENSION / "operators.py").read_text(encoding="utf-8")
    assert "def _refresh_preview" in source
    assert source.count("self._refresh_preview(context)") >= 3


def test_spatial_draw_settings_expose_workplane_offset_and_screen_snap() -> None:
    source = (EXTENSION / "runtime.py").read_text(encoding="utf-8")
    for token in (
        "work_plane",
        "workplane_offset_input",
        "snap_pixel_radius",
        '("XY", "XY 平面"',
        '("XZ", "XZ 平面"',
        '("YZ", "YZ 平面"',
    ):
        assert token in source


def test_draw_member_uses_generic_workplane_and_world_axis_lock() -> None:
    source = (EXTENSION / "operators.py").read_text(encoding="utf-8")
    assert "_point_on_xy_plane" not in source
    for token in (
        "point_on_workplane_from_ray",
        "closest_point_on_axis_to_ray",
        "_nearest_node_in_view",
        "_axis_lock",
        'event.type in {"X", "Y", "Z"}',
        "work_plane",
        "workplane_offset_input",
    ):
        assert token in source


def test_spatial_feedback_reports_xyz_delta_workplane_and_axis_lock() -> None:
    source = (EXTENSION / "viewport_overlay.py").read_text(encoding="utf-8")
    for token in (
        "ΔX",
        "ΔY",
        "ΔZ",
        "work_plane",
        "axis_lock",
        "math.dist",
    ):
        assert token in source


def test_panel_exposes_spatial_drawing_controls_and_hotkey_help() -> None:
    source = (EXTENSION / "panels.py").read_text(encoding="utf-8")
    assert 'box.prop(scene_settings, "work_plane"' in source
    assert 'box.prop(scene_settings, "workplane_offset_input")' in source
    assert "X / Y / Z 锁轴" in source
