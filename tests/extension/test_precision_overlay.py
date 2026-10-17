from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[2]
OVERLAY = ROOT / "extension" / "aludiy_designer" / "viewport_overlay.py"


def test_reference_dimension_utility_remains_available() -> None:
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


def test_node_reference_utility_remains_available() -> None:
    source = OVERLAY.read_text(encoding="utf-8")
    for token in (
        "active_node_id",
        "def _draw_node_coordinate_reference",
        "节点坐标",
        "position_mm",
    ):
        assert token in source


def test_static_reference_dimensions_are_not_called_by_direction_overlay() -> None:
    # v0.1.15 deliberately moves persistent measures to the top sidebar.
    import ast
    tree = ast.parse(OVERLAY.read_text(encoding="utf-8"))
    draw = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_draw_direction_overlay')
    called = {n.func.id for n in ast.walk(draw) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert '_draw_member_reference_dimension' not in called
    assert '_draw_node_coordinate_reference' not in called


def test_top_sidebar_readout_precedes_workspace_controls():
    source=(ROOT/'extension/aludiy_designer/panels.py').read_text()
    assert source.index('draw_selection_readout(box, context)') < source.index('row.operator("aludiy.setup_workspace"')
    assert 'g_move.display_project(context.scene)' in source
    assert '正在绘制' in source


def test_dimension_geometry_handles_zero_screen_length_safely() -> None:
    source = OVERLAY.read_text(encoding="utf-8")
    assert "if screen_length <= 1.0" in source
    assert "return None" in source
