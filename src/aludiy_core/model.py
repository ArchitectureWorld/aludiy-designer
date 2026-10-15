"""Authoritative engineering data structures for AluDIY projects and profiles."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Iterable, Mapping

from .errors import DuplicateIdError, MissingReferenceError, ValidationError

Vector2 = tuple[float, float]
Vector3 = tuple[float, float, float]


def _non_empty(value: str, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValidationError(f"{field_name} must not be empty")
    return normalized


def _finite_tuple(values: Iterable[float], length: int, field_name: str) -> tuple[float, ...]:
    converted = tuple(float(value) for value in values)
    if len(converted) != length:
        raise ValidationError(f"{field_name} must contain {length} values")
    if not all(math.isfinite(value) for value in converted):
        raise ValidationError(f"{field_name} must contain finite values")
    return converted


@dataclass(slots=True)
class Node:
    id: str
    position_mm: Vector3

    def __post_init__(self) -> None:
        self.id = _non_empty(self.id, "node.id")
        self.position_mm = _finite_tuple(self.position_mm, 3, "node.position_mm")  # type: ignore[assignment]

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "position_mm": list(self.position_mm)}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Node":
        return cls(id=str(payload["id"]), position_mm=tuple(payload["position_mm"]))


@dataclass(slots=True)
class Member:
    id: str
    start_node_id: str
    end_node_id: str
    profile_type_id: str
    anchor_ref: str = "PROFILE_ORIGIN"
    roll_deg: float = 0.0
    revision: int = 1

    def __post_init__(self) -> None:
        self.id = _non_empty(self.id, "member.id")
        self.start_node_id = _non_empty(self.start_node_id, "member.start_node_id")
        self.end_node_id = _non_empty(self.end_node_id, "member.end_node_id")
        self.profile_type_id = _non_empty(self.profile_type_id, "member.profile_type_id")
        self.anchor_ref = _non_empty(self.anchor_ref, "member.anchor_ref")
        self.roll_deg = float(self.roll_deg)
        if not math.isfinite(self.roll_deg):
            raise ValidationError("member.roll_deg must be finite")
        self.revision = int(self.revision)
        if self.revision < 1:
            raise ValidationError("member.revision must be >= 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "start_node_id": self.start_node_id,
            "end_node_id": self.end_node_id,
            "profile_type_id": self.profile_type_id,
            "anchor_ref": self.anchor_ref,
            "roll_deg": self.roll_deg,
            "revision": self.revision,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Member":
        return cls(
            id=str(payload["id"]),
            start_node_id=str(payload["start_node_id"]),
            end_node_id=str(payload["end_node_id"]),
            profile_type_id=str(payload["profile_type_id"]),
            anchor_ref=str(payload.get("anchor_ref", "PROFILE_ORIGIN")),
            roll_deg=float(payload.get("roll_deg", 0.0)),
            revision=int(payload.get("revision", 1)),
        )


@dataclass(slots=True)
class InterfaceDefinition:
    id: str
    kind: str
    host_face_id: str
    center_uv_mm: Vector2
    outward_normal_uv: Vector2
    face_tangent_uv: Vector2
    lane_index: int
    lane_count: int
    interface_standard_id: str
    station_domain: str = "FULL_MEMBER_LENGTH"

    def __post_init__(self) -> None:
        self.id = _non_empty(self.id, "interface.id")
        self.kind = _non_empty(self.kind, "interface.kind")
        self.host_face_id = _non_empty(self.host_face_id, "interface.host_face_id")
        self.center_uv_mm = _finite_tuple(self.center_uv_mm, 2, "interface.center_uv_mm")  # type: ignore[assignment]
        self.outward_normal_uv = _finite_tuple(
            self.outward_normal_uv, 2, "interface.outward_normal_uv"
        )  # type: ignore[assignment]
        self.face_tangent_uv = _finite_tuple(
            self.face_tangent_uv, 2, "interface.face_tangent_uv"
        )  # type: ignore[assignment]
        self.lane_index = int(self.lane_index)
        self.lane_count = int(self.lane_count)
        if self.lane_count < 1 or not 0 <= self.lane_index < self.lane_count:
            raise ValidationError(
                f"interface {self.id} has invalid lane {self.lane_index}/{self.lane_count}"
            )
        self.interface_standard_id = _non_empty(
            self.interface_standard_id, "interface.interface_standard_id"
        )
        self.station_domain = _non_empty(self.station_domain, "interface.station_domain")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "host_face_id": self.host_face_id,
            "center_uv_mm": list(self.center_uv_mm),
            "outward_normal_uv": list(self.outward_normal_uv),
            "face_tangent_uv": list(self.face_tangent_uv),
            "lane_index": self.lane_index,
            "lane_count": self.lane_count,
            "interface_standard_id": self.interface_standard_id,
            "station_domain": self.station_domain,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "InterfaceDefinition":
        return cls(
            id=str(payload["id"]),
            kind=str(payload["kind"]),
            host_face_id=str(payload["host_face_id"]),
            center_uv_mm=tuple(payload["center_uv_mm"]),
            outward_normal_uv=tuple(payload["outward_normal_uv"]),
            face_tangent_uv=tuple(payload["face_tangent_uv"]),
            lane_index=int(payload["lane_index"]),
            lane_count=int(payload["lane_count"]),
            interface_standard_id=str(payload["interface_standard_id"]),
            station_domain=str(payload.get("station_domain", "FULL_MEMBER_LENGTH")),
        )


@dataclass(slots=True)
class FaceDefinition:
    id: str
    outward_normal_uv: Vector2
    tangent_uv: Vector2
    interface_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        self.id = _non_empty(self.id, "face.id")
        self.outward_normal_uv = _finite_tuple(
            self.outward_normal_uv, 2, "face.outward_normal_uv"
        )  # type: ignore[assignment]
        self.tangent_uv = _finite_tuple(self.tangent_uv, 2, "face.tangent_uv")  # type: ignore[assignment]
        self.interface_ids = tuple(str(value) for value in self.interface_ids)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "outward_normal_uv": list(self.outward_normal_uv),
            "tangent_uv": list(self.tangent_uv),
            "interface_ids": list(self.interface_ids),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FaceDefinition":
        return cls(
            id=str(payload["id"]),
            outward_normal_uv=tuple(payload["outward_normal_uv"]),
            tangent_uv=tuple(payload["tangent_uv"]),
            interface_ids=tuple(payload.get("interface_ids", ())),
        )


@dataclass(slots=True)
class SectionDefinition:
    section_id: str
    width_mm: float
    height_mm: float
    origin_uv_mm: Vector2
    faces: dict[str, FaceDefinition]
    interfaces: dict[str, InterfaceDefinition]
    geometry_hash: str
    representations: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.section_id = _non_empty(self.section_id, "section.section_id")
        self.width_mm = float(self.width_mm)
        self.height_mm = float(self.height_mm)
        if not math.isfinite(self.width_mm) or self.width_mm <= 0:
            raise ValidationError("section.width_mm must be positive and finite")
        if not math.isfinite(self.height_mm) or self.height_mm <= 0:
            raise ValidationError("section.height_mm must be positive and finite")
        self.origin_uv_mm = _finite_tuple(self.origin_uv_mm, 2, "section.origin_uv_mm")  # type: ignore[assignment]
        self.geometry_hash = _non_empty(self.geometry_hash, "section.geometry_hash")
        for face_id, face in self.faces.items():
            if face_id != face.id:
                raise ValidationError(f"face map key {face_id} does not match {face.id}")
            for interface_id in face.interface_ids:
                if interface_id not in self.interfaces:
                    raise MissingReferenceError(
                        f"face {face_id} references missing interface {interface_id}"
                    )
                if self.interfaces[interface_id].host_face_id != face_id:
                    raise ValidationError(
                        f"interface {interface_id} is assigned to {self.interfaces[interface_id].host_face_id}, not {face_id}"
                    )
        for interface_id, interface in self.interfaces.items():
            if interface_id != interface.id:
                raise ValidationError(
                    f"interface map key {interface_id} does not match {interface.id}"
                )
            if interface.host_face_id not in self.faces:
                raise MissingReferenceError(
                    f"interface {interface_id} references missing face {interface.host_face_id}"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_id": self.section_id,
            "width_mm": self.width_mm,
            "height_mm": self.height_mm,
            "origin_uv_mm": list(self.origin_uv_mm),
            "geometry_hash": self.geometry_hash,
            "representations": dict(sorted(self.representations.items())),
            "faces": [self.faces[key].to_dict() for key in sorted(self.faces)],
            "interfaces": [
                self.interfaces[key].to_dict() for key in sorted(self.interfaces)
            ],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SectionDefinition":
        faces = _unique_map(
            (FaceDefinition.from_dict(item) for item in payload["faces"]),
            "face",
        )
        interfaces = _unique_map(
            (InterfaceDefinition.from_dict(item) for item in payload["interfaces"]),
            "interface",
        )
        return cls(
            section_id=str(payload["section_id"]),
            width_mm=float(payload["width_mm"]),
            height_mm=float(payload["height_mm"]),
            origin_uv_mm=tuple(payload.get("origin_uv_mm", (0.0, 0.0))),
            faces=faces,
            interfaces=interfaces,
            geometry_hash=str(payload["geometry_hash"]),
            representations=dict(payload.get("representations", {})),
        )


@dataclass(slots=True)
class ProfileType:
    profile_type_id: str
    section: SectionDefinition
    supplier_id: str
    supplier_sku: str
    series_id: str
    catalog_revision: str
    interface_standard_id: str
    display_name: str
    material: dict[str, str] = field(default_factory=dict)
    finish_options: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        self.profile_type_id = _non_empty(self.profile_type_id, "profile.profile_type_id")
        self.supplier_id = _non_empty(self.supplier_id, "profile.supplier_id")
        self.supplier_sku = _non_empty(self.supplier_sku, "profile.supplier_sku")
        self.series_id = _non_empty(self.series_id, "profile.series_id")
        self.catalog_revision = _non_empty(
            self.catalog_revision, "profile.catalog_revision"
        )
        self.interface_standard_id = _non_empty(
            self.interface_standard_id, "profile.interface_standard_id"
        )
        self.display_name = _non_empty(self.display_name, "profile.display_name")
        self.finish_options = tuple(str(value) for value in self.finish_options)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "0.1.0",
            "profile_type_id": self.profile_type_id,
            "supplier_id": self.supplier_id,
            "supplier_sku": self.supplier_sku,
            "series_id": self.series_id,
            "catalog_revision": self.catalog_revision,
            "interface_standard_id": self.interface_standard_id,
            "display_name": self.display_name,
            "material": dict(sorted(self.material.items())),
            "finish_options": list(self.finish_options),
            "section": self.section.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProfileType":
        return cls(
            profile_type_id=str(payload["profile_type_id"]),
            section=SectionDefinition.from_dict(payload["section"]),
            supplier_id=str(payload["supplier_id"]),
            supplier_sku=str(payload["supplier_sku"]),
            series_id=str(payload["series_id"]),
            catalog_revision=str(payload["catalog_revision"]),
            interface_standard_id=str(payload["interface_standard_id"]),
            display_name=str(payload["display_name"]),
            material=dict(payload.get("material", {})),
            finish_options=tuple(payload.get("finish_options", ())),
        )


@dataclass(frozen=True, slots=True)
class MemberRemovalResult:
    removed_member_ids: tuple[str, ...]
    removed_node_ids: tuple[str, ...]


@dataclass(slots=True)
class Project:
    project_id: str
    catalog_revision: str
    schema_version: str = "0.1.0"
    nodes: dict[str, Node] = field(default_factory=dict)
    members: dict[str, Member] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.project_id = _non_empty(self.project_id, "project.project_id")
        self.catalog_revision = _non_empty(
            self.catalog_revision, "project.catalog_revision"
        )
        self.schema_version = _non_empty(self.schema_version, "project.schema_version")

    def add_node(self, node: Node) -> None:
        if node.id in self.nodes or node.id in self.members:
            raise DuplicateIdError(f"duplicate entity id {node.id}")
        self.nodes[node.id] = node

    def add_member(self, member: Member) -> None:
        if member.id in self.members or member.id in self.nodes:
            raise DuplicateIdError(f"duplicate entity id {member.id}")
        for node_id in (member.start_node_id, member.end_node_id):
            if node_id not in self.nodes:
                raise MissingReferenceError(
                    f"member {member.id} references missing node {node_id}"
                )
        start = self.nodes[member.start_node_id].position_mm
        end = self.nodes[member.end_node_id].position_mm
        if math.dist(start, end) <= 1.0e-6:
            raise ValidationError(f"member {member.id} is zero-length")
        self.members[member.id] = member

    def remove_members(self, member_ids: Iterable[str]) -> MemberRemovalResult:
        normalized = tuple(
            sorted({_non_empty(member_id, "member_id") for member_id in member_ids})
        )
        missing = tuple(
            member_id for member_id in normalized if member_id not in self.members
        )
        if missing:
            raise MissingReferenceError(f"missing member {missing[0]}")

        candidate_node_ids: set[str] = set()
        for member_id in normalized:
            member = self.members[member_id]
            candidate_node_ids.update((member.start_node_id, member.end_node_id))
        for member_id in normalized:
            del self.members[member_id]

        referenced_node_ids = {
            node_id
            for member in self.members.values()
            for node_id in (member.start_node_id, member.end_node_id)
        }
        removed_node_ids = tuple(
            sorted(candidate_node_ids.difference(referenced_node_ids))
        )
        for node_id in removed_node_ids:
            self.nodes.pop(node_id, None)

        self.validate()
        return MemberRemovalResult(
            removed_member_ids=normalized,
            removed_node_ids=removed_node_ids,
        )

    def validate(self) -> None:
        seen = set(self.nodes)
        duplicate = seen.intersection(self.members)
        if duplicate:
            raise DuplicateIdError(f"duplicate entity id {sorted(duplicate)[0]}")
        for member in self.members.values():
            for node_id in (member.start_node_id, member.end_node_id):
                if node_id not in self.nodes:
                    raise MissingReferenceError(
                        f"member {member.id} references missing node {node_id}"
                    )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "catalog_revision": self.catalog_revision,
            "nodes": [self.nodes[key].to_dict() for key in sorted(self.nodes)],
            "members": [self.members[key].to_dict() for key in sorted(self.members)],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Project":
        project = cls(
            project_id=str(payload["project_id"]),
            catalog_revision=str(payload["catalog_revision"]),
            schema_version=str(payload.get("schema_version", "0.1.0")),
        )
        for item in payload.get("nodes", []):
            project.add_node(Node.from_dict(item))
        for item in payload.get("members", []):
            project.add_member(Member.from_dict(item))
        project.validate()
        return project


def _unique_map(items: Iterable[Any], kind: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in items:
        if item.id in result:
            raise DuplicateIdError(f"duplicate {kind} id {item.id}")
        result[item.id] = item
    return result
