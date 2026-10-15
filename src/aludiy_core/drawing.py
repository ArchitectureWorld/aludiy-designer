"""Spatial drawing math independent from Blender's viewport API."""

from __future__ import annotations

import math
from typing import Literal

from .errors import GeometryError, ValidationError
from .model import Vector3

WorkPlane = Literal["XY", "XZ", "YZ"]
AxisLock = Literal["X", "Y", "Z"]
_EPSILON = 1.0e-9

_WORKPLANE_BASIS: dict[WorkPlane, tuple[Vector3, Vector3, Vector3]] = {
    "XY": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    "XZ": ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
    "YZ": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
}

_AXIS_VECTORS: dict[AxisLock, Vector3] = {
    "X": (1.0, 0.0, 0.0),
    "Y": (0.0, 1.0, 0.0),
    "Z": (0.0, 0.0, 1.0),
}


def _add(a: Vector3, b: Vector3) -> Vector3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a: Vector3, b: Vector3) -> Vector3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _scale(vector: Vector3, factor: float) -> Vector3:
    return (vector[0] * factor, vector[1] * factor, vector[2] * factor)


def _dot(a: Vector3, b: Vector3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _length(vector: Vector3) -> float:
    return math.sqrt(_dot(vector, vector))


def _normalize(vector: Vector3) -> Vector3:
    length = _length(vector)
    if length <= _EPSILON:
        raise GeometryError("cannot normalize a zero-length vector")
    return _scale(vector, 1.0 / length)


def workplane_basis(work_plane: WorkPlane) -> tuple[Vector3, Vector3, Vector3]:
    try:
        return _WORKPLANE_BASIS[work_plane]
    except KeyError as exc:
        raise ValidationError(f"unsupported work plane {work_plane}") from exc


def axis_vector(axis: AxisLock) -> Vector3:
    try:
        return _AXIS_VECTORS[axis]
    except KeyError as exc:
        raise ValidationError(f"unsupported axis lock {axis}") from exc


def workplane_origin_mm(
    work_plane: WorkPlane,
    offset_mm: float,
    *,
    start_mm: Vector3 | None = None,
) -> Vector3:
    """Return the active construction-plane origin.

    During continuous drawing, every new segment's plane passes through its
    current start node. Before the first point, ``offset_mm`` locates the plane
    along its normal axis.
    """

    if start_mm is not None:
        return tuple(float(value) for value in start_mm)  # type: ignore[return-value]
    value = float(offset_mm)
    if not math.isfinite(value):
        raise ValidationError("work-plane offset must be finite")
    if work_plane == "XY":
        return (0.0, 0.0, value)
    if work_plane == "XZ":
        return (0.0, value, 0.0)
    if work_plane == "YZ":
        return (value, 0.0, 0.0)
    raise ValidationError(f"unsupported work plane {work_plane}")


def point_on_workplane_from_ray(
    *,
    ray_origin_mm: Vector3,
    ray_direction: Vector3,
    work_plane: WorkPlane,
    offset_mm: float,
    start_mm: Vector3 | None = None,
) -> Vector3:
    """Intersect a viewport ray with the selected construction plane."""

    _, _, normal = workplane_basis(work_plane)
    plane_origin = workplane_origin_mm(work_plane, offset_mm, start_mm=start_mm)
    direction = _normalize(ray_direction)
    denominator = _dot(direction, normal)
    if abs(denominator) <= _EPSILON:
        raise GeometryError("view ray is parallel to work plane")
    distance = _dot(_sub(plane_origin, ray_origin_mm), normal) / denominator
    return _add(ray_origin_mm, _scale(direction, distance))


def closest_point_on_axis_to_ray(
    *,
    axis_origin_mm: Vector3,
    axis: AxisLock,
    ray_origin_mm: Vector3,
    ray_direction: Vector3,
) -> Vector3:
    """Return the point on a world axis closest to a viewport ray."""

    axis_direction = axis_vector(axis)
    ray = _normalize(ray_direction)
    coupling = _dot(axis_direction, ray)
    denominator = 1.0 - coupling * coupling
    if abs(denominator) <= _EPSILON:
        raise GeometryError("view ray is parallel to locked axis")
    delta = _sub(axis_origin_mm, ray_origin_mm)
    axis_parameter = (
        coupling * _dot(ray, delta) - _dot(axis_direction, delta)
    ) / denominator
    return _add(axis_origin_mm, _scale(axis_direction, axis_parameter))


def point_is_on_axis(
    point_mm: Vector3,
    *,
    axis_origin_mm: Vector3,
    axis: AxisLock,
    tolerance_mm: float,
) -> bool:
    """Return whether a point lies on the locked world axis within tolerance."""

    tolerance = float(tolerance_mm)
    if not math.isfinite(tolerance) or tolerance < 0.0:
        raise ValidationError("axis tolerance must be finite and non-negative")
    direction = axis_vector(axis)
    delta = _sub(point_mm, axis_origin_mm)
    along = _scale(direction, _dot(delta, direction))
    perpendicular = _sub(delta, along)
    return _length(perpendicular) <= tolerance


def polar_endpoint_mm(
    start_mm: Vector3,
    work_plane: WorkPlane,
    length_mm: float,
    angle_deg: float,
) -> Vector3:
    """Map Rhino-style ``@length<angle`` input into a construction plane."""

    requested = float(length_mm)
    if not math.isfinite(requested) or requested <= 0.0:
        raise ValidationError("polar length must be positive and finite")
    u_axis, v_axis, _ = workplane_basis(work_plane)
    radians = math.radians(float(angle_deg))
    displacement = _add(
        _scale(u_axis, math.cos(radians) * requested),
        _scale(v_axis, math.sin(radians) * requested),
    )
    return _add(start_mm, displacement)


def workplane_angle_deg(start_mm: Vector3, end_mm: Vector3, work_plane: WorkPlane) -> float:
    """Measure the segment angle in the selected construction plane."""

    delta = _sub(end_mm, start_mm)
    u_axis, v_axis, _ = workplane_basis(work_plane)
    return math.degrees(math.atan2(_dot(delta, v_axis), _dot(delta, u_axis)))
