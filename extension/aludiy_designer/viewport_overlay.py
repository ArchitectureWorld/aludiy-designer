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
from .runtime import WORKSPACE_NAME, active_member_id, get_project, settings
from .vendor.aludiy_core.drawing import axis_vector, workplane_angle_deg

MM_TO_M = 0.001

START_COLOR = (0.10, 0.92, 0.33, 1.0)
END_COLOR = (1.00, 0.16, 0.14, 1.0)
CURSOR_COLOR = (0.15, 0.82, 1.00, 1.0)
SNAP_COLOR = (1.00, 0.72, 0.12, 1.0)
GUIDE_COLOR = (0.48, 0.68, 0.82, 0.42)
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
        project = get_project(context.scene)
        selected_id = active_member_id(context)
        gpu.state.blend_set("ALPHA")
        for member_id in sorted(project.members):
            member = project.members[member_id]
            start = _project(project.nodes[member.start_node_id].position_mm)
            end = _project(project.nodes[member.end_node_id].position_mm)
            if start is None or end is None:
                continue
            width = 4.5 if member_id == selected_id else 2.8
            _polyline(
                [(start.x, start.y), (end.x, end.y)],
                colors=[START_COLOR, END_COLOR],
                width=width,
            )
            point_size = 11.0 if member_id == selected_id else 8.0
            _points(
                [(start.x, start.y), (end.x, end.y)],
                [START_COLOR, END_COLOR],
                size=point_size,
            )
    except Exception as exc:
        print(f"AluDIY direction overlay warning: {exc}")
    finally:
        gpu.state.blend_set("NONE")


def _draw_dimension_panel(anchor: tuple[float, float], lines: list[str]) -> None:
    if not lines:
        return
    blf.size(0, 12.0)
    widths = [blf.dimensions(0, line)[0] for line in lines]
    width = max(widths, default=140.0) + 24.0
    height = 23.0 * len(lines) + 14.0
    x = anchor[0] + 16.0
    y = anchor[1] + 18.0
    _filled_rect(x, y, width, height, PANEL_COLOR)
    for index, line in enumerate(lines):
        _text(x + 12.0, y + height - 23.0 * (index + 1), line, size=12.0)


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
        or context.area.as_pointer() != getattr(operator, "_source_area_pointer", -1)
        or context.region.as_pointer() != getattr(operator, "_source_region_pointer", -1)
    ):
        return
    current_mm = getattr(operator, "_current_mm", None)
    if current_mm is None:
        return
    current = _project(current_mm)
    if current is None:
        return
    current_2d = (current.x, current.y)
    snap_node_id = getattr(operator, "_snap_node_id", None)
    typed_text = getattr(operator, "_typed", "")
    work_plane = getattr(operator, "_work_plane", "XY")
    axis_lock = getattr(operator, "_axis_lock", None)

    gpu.state.blend_set("ALPHA")
    try:
        if snap_node_id:
            draw_snap_marker(current_2d)
        else:
            draw_crosshair(current_2d)

        mode_label = f"工作平面 {work_plane}"
        if axis_lock:
            mode_label += f"  ·  {axis_lock} 轴锁定"
        lines = [mode_label, format_coordinate_label(current_mm, snap_node_id)]
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
                if axis_lock:
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
