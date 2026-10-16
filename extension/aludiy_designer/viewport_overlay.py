"""Viewport overlays for engineering-line direction and Rhino-style drawing feedback."""

from __future__ import annotations

import math
from typing import Iterable

import blf
import bpy
import gpu
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from . import view_sync
from .runtime import (
    WORKSPACE_NAME,
    active_member_id,
    active_node_id,
    get_project,
    settings,
)
from .vendor.aludiy_core import member_length_mm
from .vendor.aludiy_core.snapping import describe_candidate
from .vendor.aludiy_core.drawing import axis_vector, workplane_angle_deg

MM_TO_M = 0.001

START_COLOR = (0.10, 0.92, 0.33, 1.0)
END_COLOR = (1.00, 0.16, 0.14, 1.0)
CURSOR_COLOR = (0.15, 0.82, 1.00, 1.0)
SNAP_COLOR = (1.00, 0.72, 0.12, 1.0)
GUIDE_COLOR = (0.48, 0.68, 0.82, 0.42)
DIMENSION_COLOR = (0.20, 0.82, 1.00, 0.95)
TEXT_COLOR = (0.94, 0.97, 1.00, 1.0)
PANEL_COLOR = (0.035, 0.055, 0.075, 0.90)
AXIS_COLORS = {
    "X": (1.0, 0.30, 0.25, 0.70),
    "Y": (0.30, 1.0, 0.40, 0.70),
    "Z": (0.30, 0.58, 1.0, 0.82),
}

_DIRECTION_HANDLER = None


def _project(point_mm: Iterable[float]):
    context = bpy.context
    if context.region is None or context.region_data is None:
        return None
    world = Vector(tuple(float(value) * MM_TO_M for value in point_mm))
    return view3d_utils.location_3d_to_region_2d(
        context.region,
        context.region_data,
        world,
        default=None,
    )


def _polyline(
    points: list[tuple[float, float]],
    *,
    colors: list[tuple[float, float, float, float]] | None = None,
    color: tuple[float, float, float, float] | None = None,
    width: float = 2.0,
) -> None:
    if len(points) < 2:
        return
    if colors is not None:
        shader = gpu.shader.from_builtin("POLYLINE_SMOOTH_COLOR")
        batch = batch_for_shader(
            shader,
            "LINES",
            {
                "pos": [(point[0], point[1], 0.0) for point in points],
                "color": colors,
            },
        )
    else:
        shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
        batch = batch_for_shader(
            shader,
            "LINES",
            {"pos": [(point[0], point[1], 0.0) for point in points]},
        )
    shader.bind()
    shader.uniform_float(
        "viewportSize",
        (float(bpy.context.region.width), float(bpy.context.region.height)),
    )
    shader.uniform_float("lineWidth", float(width))
    if color is not None:
        shader.uniform_float("color", color)
    batch.draw(shader)


def _points(
    points: list[tuple[float, float]],
    colors: list[tuple[float, float, float, float]],
    *,
    size: float,
) -> None:
    if not points:
        return
    shader = gpu.shader.from_builtin("POINT_FLAT_COLOR")
    batch = batch_for_shader(
        shader,
        "POINTS",
        {
            "pos": [(point[0], point[1], 0.0) for point in points],
            "color": colors,
        },
    )
    shader.bind()
    shader.uniform_float("size", float(size))
    batch.draw(shader)


def _filled_rect(x: float, y: float, width: float, height: float, color) -> None:
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    batch = batch_for_shader(
        shader,
        "TRIS",
        {
            "pos": [
                (x, y, 0.0),
                (x + width, y, 0.0),
                (x + width, y + height, 0.0),
                (x, y, 0.0),
                (x + width, y + height, 0.0),
                (x, y + height, 0.0),
            ]
        },
    )
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)


def _text(x: float, y: float, value: str, *, size: float = 13.0, color=TEXT_COLOR) -> None:
    font_id = 0
    blf.color(font_id, *color)
    blf.size(font_id, size)
    blf.position(font_id, x, y, 0)
    blf.enable(font_id, blf.SHADOW)
    blf.shadow(font_id, 3, 0.0, 0.0, 0.0, 0.85)
    blf.shadow_offset(font_id, 1, -1)
    blf.draw(font_id, value)
    blf.disable(font_id, blf.SHADOW)


def draw_crosshair(
    point: tuple[float, float],
    *,
    color=CURSOR_COLOR,
    radius: float = 8.0,
) -> None:
    x, y = point
    _polyline(
        [(x - radius, y), (x + radius, y), (x, y - radius), (x, y + radius)],
        color=color,
        width=1.4,
    )
    circle: list[tuple[float, float]] = []
    segments = 20
    for index in range(segments):
        a0 = math.tau * index / segments
        a1 = math.tau * (index + 1) / segments
        circle.extend(
            [
                (x + math.cos(a0) * radius * 0.62, y + math.sin(a0) * radius * 0.62),
                (x + math.cos(a1) * radius * 0.62, y + math.sin(a1) * radius * 0.62),
            ]
        )
    _polyline(circle, color=color, width=1.2)


def draw_snap_marker(point: tuple[float, float], *, color=SNAP_COLOR) -> None:
    x, y = point
    radius = 8.0
    diamond = [
        (x, y + radius),
        (x + radius, y),
        (x + radius, y),
        (x, y - radius),
        (x, y - radius),
        (x - radius, y),
        (x - radius, y),
        (x, y + radius),
    ]
    _polyline(diamond, color=color, width=2.2)
    _points([point], [color], size=4.0)


def format_coordinate_label(point_mm, snap_node_id: str | None) -> str:
    if snap_node_id:
        return (
            f"吸附节点 {snap_node_id}  ·  X {point_mm[0]:.1f}  "
            f"Y {point_mm[1]:.1f}  Z {point_mm[2]:.1f} mm"
        )
    return f"X {point_mm[0]:.1f}  Y {point_mm[1]:.1f}  Z {point_mm[2]:.1f} mm"


def format_measurement_label(
    start_mm,
    end_mm,
    typed_text: str = "",
    *,
    work_plane: str = "XY",
    axis_lock: str | None = None,
) -> str:
    dx = end_mm[0] - start_mm[0]
    dy = end_mm[1] - start_mm[1]
    dz = end_mm[2] - start_mm[2]
    length_mm = math.dist(tuple(start_mm), tuple(end_mm))
    angle_deg = workplane_angle_deg(start_mm, end_mm, work_plane)
    mode = f"{axis_lock} 轴" if axis_lock else f"{work_plane} 平面"
    suffix = f"  ·  输入 {typed_text}" if typed_text else ""
    return (
        f"L {length_mm:.1f} mm  ·  ΔX {dx:.1f}  ΔY {dy:.1f}  ΔZ {dz:.1f}  "
        f"·  ∠ {angle_deg:.1f}°  ·  {mode}{suffix}"
    )


def dimension_geometry_2d(
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    offset_px: float = 28.0,
):
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    screen_length = math.hypot(dx, dy)
    if screen_length <= 1.0:
        return None
    tangent = (dx / screen_length, dy / screen_length)
    normal = (-tangent[1], tangent[0])
    witness_start = (
        start[0] + normal[0] * offset_px,
        start[1] + normal[1] * offset_px,
    )
    witness_end = (
        end[0] + normal[0] * offset_px,
        end[1] + normal[1] * offset_px,
    )
    label = (
        (witness_start[0] + witness_end[0]) * 0.5 + normal[0] * 7.0,
        (witness_start[1] + witness_end[1]) * 0.5 + normal[1] * 7.0,
    )
    return {
        "witness_start": witness_start,
        "witness_end": witness_end,
        "label": label,
        "tangent": tangent,
        "normal": normal,
    }


def _draw_member_reference_dimension(project, member_id: str) -> None:
    member = project.members.get(member_id)
    if member is None:
        return
    start = _project(project.nodes[member.start_node_id].position_mm)
    end = _project(project.nodes[member.end_node_id].position_mm)
    if start is None or end is None:
        return
    start_2d = (start.x, start.y)
    end_2d = (end.x, end.y)
    geometry = dimension_geometry_2d(start_2d, end_2d)
    if geometry is None:
        return
    witness_start = geometry["witness_start"]
    witness_end = geometry["witness_end"]
    tangent = geometry["tangent"]
    _polyline([start_2d, witness_start], color=DIMENSION_COLOR, width=1.2)
    _polyline([end_2d, witness_end], color=DIMENSION_COLOR, width=1.2)
    _polyline([witness_start, witness_end], color=DIMENSION_COLOR, width=1.8)
    tick = 5.0
    for point in (witness_start, witness_end):
        a = (point[0] - tangent[0] * tick, point[1] - tangent[1] * tick)
        b = (point[0] + tangent[0] * tick, point[1] + tangent[1] * tick)
        _polyline([a, b], color=DIMENSION_COLOR, width=1.8)
    label = geometry["label"]
    _text(
        label[0],
        label[1],
        f"参考尺寸  {member_length_mm(project, member_id):.1f} mm",
        size=12.5,
        color=DIMENSION_COLOR,
    )


def _draw_node_coordinate_reference(project, node_id: str) -> None:
    node = project.nodes.get(node_id)
    if node is None:
        return
    point = _project(node.position_mm)
    if point is None:
        return
    point_2d = (point.x, point.y)
    _points([point_2d], [DIMENSION_COLOR], size=13.0)
    _draw_dimension_panel(
        point_2d,
        [
            f"节点坐标  {node.id}",
            (
                f"X {node.position_mm[0]:.1f}  Y {node.position_mm[1]:.1f}  "
                f"Z {node.position_mm[2]:.1f} mm"
            ),
        ],
    )


def _draw_direction_overlay() -> None:
    context = bpy.context
    if (
        context.area is None
        or context.region is None
        or context.region_data is None
        or context.workspace is None
        or context.workspace.name != WORKSPACE_NAME
        or not view_sync.is_line_view_context(context)
    ):
        return
    try:
        if not settings(context.scene).project_json.strip():
            return
        from . import g_move
        project = g_move.display_project(context.scene)
        selected_id = active_member_id(context)
        selected_ids, selected_nodes = g_move.selection_summary(context)
        selected_node_id = active_node_id(context)
        if g_move._ACTIVE is not None and g_move._ACTIVE._candidate is not None:
            selected_node_id = g_move._ACTIVE._candidate.detached_node_id or selected_node_id
        gpu.state.blend_set("ALPHA")
        for member_id in sorted(project.members):
            member = project.members[member_id]
            start = _project(project.nodes[member.start_node_id].position_mm)
            end = _project(project.nodes[member.end_node_id].position_mm)
            if start is None or end is None:
                continue
            width = 4.5 if member_id in selected_ids else 2.8
            _polyline(
                [(start.x, start.y), (end.x, end.y)],
                colors=[START_COLOR, END_COLOR],
                width=width,
            )
            point_size = 11.0 if member_id in selected_ids else 8.0
            _points(
                [(start.x, start.y), (end.x, end.y)],
                [START_COLOR, END_COLOR],
                size=point_size,
            )
        if selected_id:
            _draw_member_reference_dimension(project, selected_id)
        elif selected_node_id:
            _draw_node_coordinate_reference(project, selected_node_id)
    except Exception as exc:
        print(f"AluDIY direction overlay warning: {exc}")
    finally:
        gpu.state.blend_set("NONE")


def _draw_dimension_panel(anchor, lines) -> None:
    from .vendor.aludiy_core.overlay_layout import wrap_lines, place_box
    region = bpy.context.region
    left, bottom, right, top = 8.0, 8.0, region.width-8.0, region.height-8.0
    # Overlaid sidebars/tools occupy WINDOW pixels even when the region width
    # still reports the whole area. Avoid them instead of drawing behind them.
    for other in bpy.context.area.regions:
        if other.width <= 1 or other.height <= 1:
            continue
        if other.type in {'UI', 'TOOLS'}:
            if other.x < region.x+region.width/2:
                left = max(left, other.x+other.width-region.x+8)
            else:
                right = min(right, other.x-region.x-8)
        elif other.type in {'HEADER', 'TOOL_HEADER'} and other.y > region.y+region.height/2:
            top = min(top, other.y-region.y-8)
    available = max(60.0, right-left)
    blf.size(0, 12.0)
    measure = lambda value: blf.dimensions(0, value)[0]
    rows = wrap_lines(lines, measure, max(30.0, available-24))
    width = min(available, max((measure(line) for line in rows), default=0.0)+24)
    height = len(rows)*21.0+18.0
    x,y = place_box(anchor, (width,height), (left,bottom,right,top))
    _filled_rect(x,y,width,height,PANEL_COLOR)
    for i,line in enumerate(rows):
        _text(x+12, y+height-21*(i+1), line, size=12.0)


def _draw_guides(start: tuple[float, float], end: tuple[float, float]) -> None:
    corner = (end[0], start[1])
    _polyline([start, corner, corner, end], color=GUIDE_COLOR, width=1.0)


def _draw_axis_guide(start_mm, axis_lock: str, span_mm: float = 5000.0) -> None:
    direction = axis_vector(axis_lock)
    before = tuple(start_mm[index] - direction[index] * span_mm for index in range(3))
    after = tuple(start_mm[index] + direction[index] * span_mm for index in range(3))
    start = _project(before)
    end = _project(after)
    if start is None or end is None:
        return
    _polyline(
        [(start.x, start.y), (end.x, end.y)],
        color=AXIS_COLORS[axis_lock],
        width=1.6,
    )


def _draw_member_feedback(operator) -> None:
    context = bpy.context
    if (
        context.area is None
        or context.region is None
        or context.region_data is None
        or context.region.type != "WINDOW"
        or context.window.as_pointer() != getattr(operator, "_source_window_pointer", -1)
        or context.scene != getattr(operator, "_scene", None)
    ):
        return
    current_mm = getattr(operator, "_display_point", None)
    if current_mm is None:
        return
    current = _project(current_mm)
    if current is None:
        return
    current_2d = (current.x, current.y)
    snap = getattr(operator, "_display_snap", None)
    snap_node_id = snap.node_id if snap else None
    typed_text = getattr(operator, "_typed", "")
    work_plane = getattr(operator, "_work_plane", "XY")
    axis_lock = getattr(operator, "_axis_lock", None)

    gpu.state.blend_set("ALPHA")
    try:
        if snap:
            draw_snap_marker(current_2d)
        else:
            draw_crosshair(current_2d)

        plane_lock = getattr(operator, "_plane_lock", False)
        mode_label = f"自由定位面 {work_plane}"
        if axis_lock:
            mode_label = f"排除 {axis_lock} 平面锁定" if plane_lock else f"{axis_lock} 轴锁定"
        project = get_project(context.scene)
        hint = ("Ctrl 自由定位 · 不吸附" if getattr(operator, "_free", False) else
                "精确输入优先 · 仅定位" if typed_text and snap is None else describe_candidate(snap, project))
        if snap and len(getattr(operator, '_snap_options', ())) > 1:
            hint += f" · Tab {operator._snap_choice % len(operator._snap_options)+1}/{len(operator._snap_options)}"
        error = getattr(operator, '_input_error', '') or getattr(operator, '_cursor_error', '')
        if snap and snap.member_id:
            host = project.members[snap.member_id]
            a = _project(project.nodes[host.start_node_id].position_mm)
            b = _project(project.nodes[host.end_node_id].position_mm)
            if a is not None and b is not None:
                _polyline([(a.x,a.y),(b.x,b.y)],color=SNAP_COLOR,width=1.5)
        lines = [mode_label, hint, format_coordinate_label(current_mm, None)]
        if error:
            lines.append('不可提交：' + error)
        start_mm = getattr(operator, "_start_mm", None)
        if start_mm is not None:
            try:
                end_mm = operator._resolved_end()
            except Exception:
                end_mm = current_mm
            start = _project(start_mm)
            end = _project(end_mm)
            if start is not None and end is not None:
                start_2d = (start.x, start.y)
                end_2d = (end.x, end.y)
                if axis_lock and not plane_lock:
                    _draw_axis_guide(start_mm, axis_lock)
                elif work_plane == "XY":
                    _draw_guides(start_2d, end_2d)
                _polyline(
                    [start_2d, end_2d],
                    colors=[START_COLOR, END_COLOR],
                    width=3.6,
                )
                _points(
                    [start_2d, end_2d],
                    [START_COLOR, END_COLOR],
                    size=12.0,
                )
                lines.insert(
                    0,
                    format_measurement_label(
                        start_mm,
                        end_mm,
                        typed_text,
                        work_plane=work_plane,
                        axis_lock=axis_lock,
                    ),
                )
        _draw_dimension_panel(current_2d, lines)
    finally:
        gpu.state.blend_set("NONE")


def add_draw_feedback(operator):
    handler = bpy.types.SpaceView3D.draw_handler_add(
        _draw_member_feedback,
        (operator,),
        "WINDOW",
        "POST_PIXEL",
    )
    operator._draw_feedback_handle = handler
    return handler


def remove_draw_feedback(operator) -> None:
    handler = getattr(operator, "_draw_feedback_handle", None)
    if handler is None:
        return
    try:
        bpy.types.SpaceView3D.draw_handler_remove(handler, "WINDOW")
    finally:
        operator._draw_feedback_handle = None


def register_direction_overlay() -> None:
    global _DIRECTION_HANDLER
    if _DIRECTION_HANDLER is None:
        _DIRECTION_HANDLER = bpy.types.SpaceView3D.draw_handler_add(
            _draw_direction_overlay,
            (),
            "WINDOW",
            "POST_PIXEL",
        )


def unregister_direction_overlay() -> None:
    global _DIRECTION_HANDLER
    if _DIRECTION_HANDLER is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_DIRECTION_HANDLER, "WINDOW")
        _DIRECTION_HANDLER = None
