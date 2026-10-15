"""Deterministic geometry derivation independent of Blender."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

from .catalog import ProfileCatalog
from .errors import GeometryError, MissingReferenceError, ValidationError
from .model import Project, SectionDefinition, Vector2, Vector3

AnchorMode = Literal["START", "END", "CENTER"]
MeshMode = Literal["BOX", "PROFILE"]
_EPSILON_MM = 1.0e-6


@dataclass(frozen=True, slots=True)
class MemberEnvelope:
    member_id: str
    start_mm: Vector3
    end_mm: Vector3
    center_mm: Vector3
    axis_direction: Vector3
    u_axis: Vector3
    v_axis: Vector3
    length_mm: float
    section_width_mm: float
    section_height_mm: float
    world_half_extents_mm: Vector3
    profile_type_id: str
    roll_deg: float


@dataclass(frozen=True, slots=True)
class MemberMesh:
    member_id: str
    mode: MeshMode
    vertices_mm: tuple[Vector3, ...]
    faces: tuple[tuple[int, ...], ...]


@dataclass(frozen=True, slots=True)
class _FacePath:
    face_id: str
    start_uv: Vector2
    end_uv: Vector2
    tangent_uv: Vector2
    outward_normal_uv: Vector2


def _add2(a: Vector2, b: Vector2) -> Vector2:
    return (a[0] + b[0], a[1] + b[1])


def _sub2(a: Vector2, b: Vector2) -> Vector2:
    return (a[0] - b[0], a[1] - b[1])


def _scale2(vector: Vector2, factor: float) -> Vector2:
    return (vector[0] * factor, vector[1] * factor)


def _dot2(a: Vector2, b: Vector2) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _append_unique(points: list[Vector2], point: Vector2) -> None:
    converted = (float(point[0]), float(point[1]))
    if not points or math.dist(points[-1], converted) > _EPSILON_MM:
        points.append(converted)


def _section_face_paths(section: SectionDefinition) -> tuple[_FacePath, ...]:
    origin_u, origin_v = section.origin_uv_mm
    half_width = section.width_mm * 0.5
    half_height = section.height_mm * 0.5
    left = origin_u - half_width
    right = origin_u + half_width
    bottom = origin_v - half_height
    top = origin_v + half_height
    return (
        _FacePath("FACE_NV", (left, bottom), (right, bottom), (1.0, 0.0), (0.0, -1.0)),
        _FacePath("FACE_PU", (right, bottom), (right, top), (0.0, 1.0), (1.0, 0.0)),
        _FacePath("FACE_PV", (right, top), (left, top), (-1.0, 0.0), (0.0, 1.0)),
        _FacePath("FACE_NU", (left, top), (left, bottom), (0.0, -1.0), (-1.0, 0.0)),
    )


def _slot_preview_dimensions(section: SectionDefinition) -> tuple[float, float, float, float]:
    minimum = min(section.width_mm, section.height_mm)
    opening = 6.0 if minimum <= 20.0 else 8.0
    depth = minimum * 0.22
    neck_depth = depth * 0.38
    cavity_width = min(opening * 1.55, minimum * 0.58)
    return opening, neck_depth, cavity_width, depth


def section_outline_uv(
    section: SectionDefinition,
    *,
    detailed: bool,
) -> tuple[Vector2, ...]:
    """Return a deterministic CCW LOD0 or semantic T-slot preview outline.

    The detailed representation is intentionally an interaction LOD derived from
    stable interface positions. It is not a manufacturing-accurate supplier DXF.
    """

    face_paths = _section_face_paths(section)
    if not detailed:
        return tuple(path.start_uv for path in face_paths)

    opening, neck_depth, cavity_width, depth = _slot_preview_dimensions(section)
    points: list[Vector2] = []
    _append_unique(points, face_paths[0].start_uv)
    for path in face_paths:
        face = section.faces.get(path.face_id)
        interface_ids = face.interface_ids if face is not None else ()
        interfaces = [section.interfaces[interface_id] for interface_id in interface_ids]
        interfaces.sort(
            key=lambda interface: _dot2(
                _sub2(interface.center_uv_mm, path.start_uv), path.tangent_uv
            )
        )
        for interface in interfaces:
            center = interface.center_uv_mm
            mouth_half = opening * 0.5
            cavity_half = cavity_width * 0.5
            inward = _scale2(path.outward_normal_uv, -1.0)
            before = _add2(center, _scale2(path.tangent_uv, -mouth_half))
            after = _add2(center, _scale2(path.tangent_uv, mouth_half))
            _append_unique(points, before)
            _append_unique(points, _add2(before, _scale2(inward, neck_depth)))
            _append_unique(
                points,
                _add2(
                    _add2(center, _scale2(path.tangent_uv, -cavity_half)),
                    _scale2(inward, neck_depth),
                ),
            )
            _append_unique(
                points,
                _add2(
                    _add2(center, _scale2(path.tangent_uv, -cavity_half)),
                    _scale2(inward, depth),
                ),
            )
            _append_unique(
                points,
                _add2(
                    _add2(center, _scale2(path.tangent_uv, cavity_half)),
                    _scale2(inward, depth),
                ),
            )
            _append_unique(
                points,
                _add2(
                    _add2(center, _scale2(path.tangent_uv, cavity_half)),
                    _scale2(inward, neck_depth),
                ),
            )
            _append_unique(points, _add2(after, _scale2(inward, neck_depth)))
            _append_unique(points, after)
        _append_unique(points, path.end_uv)
    if len(points) > 1 and math.dist(points[0], points[-1]) <= _EPSILON_MM:
        points.pop()
    return tuple(points)


def _world_section_point(origin: Vector3, u_axis: Vector3, v_axis: Vector3, uv: Vector2) -> Vector3:
    return tuple(
        origin[index] + u_axis[index] * uv[0] + v_axis[index] * uv[1]
        for index in range(3)
    )  # type: ignore[return-value]


def derive_member_mesh(
    project: Project,
    member_id: str,
    catalog: ProfileCatalog,
    *,
    mode: MeshMode,
) -> MemberMesh:
    """Derive a box or semantic profile mesh without Blender dependencies."""

    if mode not in {"BOX", "PROFILE"}:
        raise ValidationError(f"unsupported member mesh mode {mode}")
    envelope = derive_member_envelope(project, member_id, catalog)
    profile = catalog.get(envelope.profile_type_id)
    outline = section_outline_uv(profile.section, detailed=mode == "PROFILE")
    start_ring = tuple(
        _world_section_point(envelope.start_mm, envelope.u_axis, envelope.v_axis, uv)
        for uv in outline
    )
    end_ring = tuple(
        _world_section_point(envelope.end_mm, envelope.u_axis, envelope.v_axis, uv)
        for uv in outline
    )
    count = len(outline)
    faces: list[tuple[int, ...]] = [tuple(reversed(range(count))), tuple(range(count, count * 2))]
    for index in range(count):
        next_index = (index + 1) % count
        faces.append((index, next_index, next_index + count, index + count))
    return MemberMesh(
        member_id=member_id,
        mode=mode,
        vertices_mm=start_ring + end_ring,
        faces=tuple(faces),
    )


def _add(a: Vector3, b: Vector3) -> Vector3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a: Vector3, b: Vector3) -> Vector3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _scale(vector: Vector3, factor: float) -> Vector3:
    return (vector[0] * factor, vector[1] * factor, vector[2] * factor)


def _dot(a: Vector3, b: Vector3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vector3, b: Vector3) -> Vector3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _length(vector: Vector3) -> float:
    return math.sqrt(_dot(vector, vector))


def _normalize(vector: Vector3) -> Vector3:
    length = _length(vector)
    if length <= _EPSILON_MM:
        raise GeometryError("cannot normalize a zero-length vector")
    return _scale(vector, 1.0 / length)


def _member(project: Project, member_id: str):
    try:
        return project.members[member_id]
    except KeyError as exc:
        raise MissingReferenceError(f"unknown member {member_id}") from exc


def member_length_mm(project: Project, member_id: str) -> float:
    member = _member(project, member_id)
    start = project.nodes[member.start_node_id].position_mm
    end = project.nodes[member.end_node_id].position_mm
    return _length(_sub(end, start))


def resize_member(
    project: Project,
    member_id: str,
    length_mm: float,
    *,
    anchor: AnchorMode,
) -> None:
    """Resize a member along its current axis while explicitly anchoring it."""

    member = _member(project, member_id)
    requested = float(length_mm)
    if not math.isfinite(requested) or requested <= _EPSILON_MM:
        raise ValidationError("member length must be positive and finite")
    if anchor not in {"START", "END", "CENTER"}:
        raise ValidationError(f"unsupported resize anchor {anchor}")
    start_node = project.nodes[member.start_node_id]
    end_node = project.nodes[member.end_node_id]
    direction = _normalize(_sub(end_node.position_mm, start_node.position_mm))

    if anchor == "START":
        end_node.position_mm = _add(start_node.position_mm, _scale(direction, requested))
    elif anchor == "END":
        start_node.position_mm = _sub(end_node.position_mm, _scale(direction, requested))
    else:
        center = _scale(_add(start_node.position_mm, end_node.position_mm), 0.5)
        half = _scale(direction, requested * 0.5)
        start_node.position_mm = _sub(center, half)
        end_node.position_mm = _add(center, half)
    member.revision += 1


def _section_frame(axis: Vector3, roll_deg: float) -> tuple[Vector3, Vector3]:
    reference_up: Vector3 = (0.0, 0.0, 1.0)
    if abs(_dot(axis, reference_up)) > 0.99:
        reference_up = (0.0, 1.0, 0.0)
    base_u = _normalize(_cross(reference_up, axis))
    base_v = _normalize(_cross(axis, base_u))
    radians = math.radians(roll_deg)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    u_axis = _add(_scale(base_u, cosine), _scale(base_v, sine))
    v_axis = _add(_scale(base_u, -sine), _scale(base_v, cosine))
    return _normalize(u_axis), _normalize(v_axis)


def derive_member_envelope(
    project: Project,
    member_id: str,
    catalog: ProfileCatalog,
) -> MemberEnvelope:
    """Derive a rectangular LOD0 envelope and stable local frame."""

    member = _member(project, member_id)
    start = project.nodes[member.start_node_id].position_mm
    end = project.nodes[member.end_node_id].position_mm
    delta = _sub(end, start)
    length = _length(delta)
    if length <= _EPSILON_MM:
        raise GeometryError(f"member {member_id} is zero-length")
    axis = _normalize(delta)
    u_axis, v_axis = _section_frame(axis, member.roll_deg)
    profile = catalog.get(member.profile_type_id)
    width = profile.section.width_mm
    height = profile.section.height_mm
    center = _scale(_add(start, end), 0.5)
    half_extents = tuple(
        abs(axis[index]) * length * 0.5
        + abs(u_axis[index]) * width * 0.5
        + abs(v_axis[index]) * height * 0.5
        for index in range(3)
    )
    return MemberEnvelope(
        member_id=member_id,
        start_mm=start,
        end_mm=end,
        center_mm=center,
        axis_direction=axis,
        u_axis=u_axis,
        v_axis=v_axis,
        length_mm=length,
        section_width_mm=width,
        section_height_mm=height,
        world_half_extents_mm=half_extents,  # type: ignore[arg-type]
        profile_type_id=member.profile_type_id,
        roll_deg=member.roll_deg,
    )
