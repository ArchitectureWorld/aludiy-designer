"""Atomic member-parameter editing and read-only semantic slot inspection.

No bpy dependency. A profile replacement or roll must never move nodes, break
axis associations, or imply that a physical connector is compatible.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import re
from typing import Iterable
from .catalog import ProfileCatalog
from .model import Project, Vector3
from .errors import ValidationError, InputParseError
from .geometry import derive_member_envelope
from .units import _evaluate_numeric_expression


@dataclass(frozen=True, slots=True)
class ProfileEdit:
    project: Project
    changed_member_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InterfaceRail:
    interface_id: str
    face_id: str
    lane_index: int
    lane_count: int
    start_mm: Vector3
    end_mm: Vector3
    normal: Vector3


def parse_angle_deg(text: str) -> float:
    """Degrees and arithmetic, but never length units or executable input."""
    value = re.sub(r'(?:deg|°|度)\s*$', '', str(text).strip(), flags=re.I).strip()
    if re.search(r'[A-Za-z_]', value):
        raise InputParseError('角度请用度数或算式，例如 90、45+45；不要输入 mm/m')
    angle = _evaluate_numeric_expression(value)
    if abs(angle) > 1e9:
        raise InputParseError('角度数值过大')
    return angle


def edit_profiles(project: Project, member_ids: Iterable[str], catalog: ProfileCatalog,
                  *, profile_type_id: str | None = None, roll_deg: float | None = None,
                  relative: bool = False) -> ProfileEdit:
    """Return an isolated candidate; validate the whole batch before changing it."""
    ids = tuple(sorted(set(member_ids)))
    if not ids or any(mid not in project.members for mid in ids):
        raise ValidationError('请选择有效型材；单独节点不是换型或截面旋转对象')
    if profile_type_id is not None:
        catalog.get(profile_type_id)
    if roll_deg is not None and (not math.isfinite(roll_deg) or abs(roll_deg) > 1e9):
        raise ValidationError('截面角度必须是有限且合理的度数')
    project.validate()
    from .associations import validate_slot_catalog
    validate_slot_catalog(project, catalog)
    if profile_type_id is not None:
        for r in project.associations.values():
            if (r.kind=='ON_SLOT' and r.host_member_id in ids and
                    project.members[r.host_member_id].profile_type_id!=profile_type_id):
                raise ValidationError('主杆存在槽轨附着；请先解除关联，换型后重新指定接口，不能按同名槽猜测兼容')
    for mid in ids:
        m = project.members[mid]
        catalog.get(m.profile_type_id)
        if m.anchor_ref != 'PROFILE_ORIGIN':
            raise ValidationError(f'{mid} 使用尚未支持的截面定位基准，操作未提交')
    candidate = Project.from_dict(project.to_dict())
    changed = []
    for mid in ids:
        m = candidate.members[mid]
        profile = m.profile_type_id if profile_type_id is None else profile_type_id
        angle = m.roll_deg if roll_deg is None else ((m.roll_deg if relative else 0) + roll_deg) % 360
        equivalent = abs((angle - m.roll_deg + 180) % 360 - 180) < 1e-10
        if profile == m.profile_type_id and equivalent:
            continue
        m.profile_type_id = profile
        m.roll_deg = angle
        m.revision += 1
        changed.append(mid)
    # Roll changes have no direct node displacement but move off-axis slot rails.
    from .geometry import _apply_node_positions
    result = _apply_node_positions(candidate, {}, changed_member_ids=changed)
    changed = sorted(set(changed) | set(result.affected_member_ids))
    for mid in changed:
        candidate.members[mid].revision=project.members[mid].revision+1
    candidate.validate()
    return ProfileEdit(candidate, tuple(changed))


def interface_rails(project: Project, member_id: str, catalog: ProfileCatalog) -> tuple[InterfaceRail, ...]:
    """Physical-location *preview* of each semantic slot, in authoritative mm.

    The catalog's center_uv_mm shares its outline coordinate system. Do not
    subtract the section origin a second time or rotate the stable slot IDs.
    """
    e = derive_member_envelope(project, member_id, catalog)
    section = catalog.get(e.profile_type_id).section
    rails = []
    for slot in sorted(section.interfaces.values(), key=lambda s: s.id):
        uv = slot.center_uv_mm
        offset = tuple(e.u_axis[i]*uv[0] + e.v_axis[i]*uv[1] for i in range(3))
        normal = tuple(e.u_axis[i]*slot.outward_normal_uv[0] + e.v_axis[i]*slot.outward_normal_uv[1] for i in range(3))
        rails.append(InterfaceRail(slot.id, slot.host_face_id, slot.lane_index, slot.lane_count,
            tuple(e.start_mm[i]+offset[i] for i in range(3)),
            tuple(e.end_mm[i]+offset[i] for i in range(3)), normal))
    return tuple(rails)
