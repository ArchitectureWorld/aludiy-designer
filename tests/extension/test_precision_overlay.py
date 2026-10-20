from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[2]
OVERLAY = ROOT / "extension" / "aludiy_designer" / "viewport_overlay.py"


def test_selected_member_overlay_draws_reference_dimension_in_line_view() -> None:
    source = OVERLAY.read_text(encoding="utf-8")
    for token in (
        "def dimension_geometry_2d",
        "def _draw_member_reference_dimension",
        "DIMENSION_COLOR",
        "member_length_mm",
        "参考尺寸",
        "witness_start",
        "witness_end",
    ):
        assert token in source


def test_selected_node_overlay_draws_exact_xyz_label() -> None:
    source = OVERLAY.read_text(encoding="utf-8")
    for token in (
        "active_node_id",
        "def _draw_node_coordinate_reference",
        "节点坐标",
        "position_mm",
    ):
        assert token in source


def test_direction_overlay_invokes_member_or_node_reference_feedback() -> None:
    source = OVERLAY.read_text(encoding="utf-8")
    assert "_draw_member_reference_dimension(project, selected_id)" in source
    assert "_draw_node_coordinate_reference(project, selected_node_id)" in source
    assert "if selected_id" in source
    assert "elif selected_node_id" in source


def test_dimension_geometry_handles_zero_screen_length_safely() -> None:
    source = OVERLAY.read_text(encoding="utf-8")
    assert "if screen_length <= 1.0" in source
    assert "return None" in source
