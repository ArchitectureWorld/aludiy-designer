"""Explicit rectangular-envelope, square-cut L/T processing rules.

Engineering axes and assembly associations are never edited here. Positive
setback shortens a physical end; negative setback extends it. Invalidated rules
produce a visible pending result, not a movement constraint or an exportable
manufacturing dimension. No connector/collision/strength certification.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
from .model import Project
from .errors import ValidationError
from .geometry import derive_member_envelope, member_length_mm, _dot, _sub, _normalize

TOL = 0.001
ANGULAR_TOL = 1e-7


@dataclass(frozen=True, slots=True)
class ButtJoint:
    id: str
    host_member_id: str
    branch_member_id: str
    branch_end: str
    gap_mm: float = 0.0
    kind: str = 'BUTT90'

    def __post_init__(self):
        if not all(isinstance(x, str) and x.strip() for x in
                   (self.id, self.host_member_id, self.branch_member_id)):
            raise ValidationError('交接 ID 或构件引用为空')
        if self.host_member_id == self.branch_member_id:
            raise ValidationError('交接主杆与支杆不能相同')
        if self.branch_end not in {'START', 'END'} or self.kind != 'BUTT90':
            raise ValidationError('仅支持有效杆端的直角端面对接')
        gap = float(self.gap_mm)
        if not math.isfinite(gap) or gap < 0:
            raise ValidationError('交接间隙必须为非负有限毫米值')
        object.__setattr__(self, 'gap_mm', gap)

    def to_dict(self):
        return dict(id=self.id, kind=self.kind, host_member_id=self.host_member_id,
                    branch_member_id=self.branch_member_id, branch_end=self.branch_end,
                    gap_mm=self.gap_mm)

    @classmethod
    def from_dict(cls, d):
        try:
            return cls(d['id'], d['host_member_id'], d['branch_member_id'],
                       d['branch_end'], d.get('gap_mm', 0), d.get('kind', 'BUTT90'))
        except (KeyError, ValueError, TypeError) as exc:
            raise ValidationError('交接规则数据不完整或无效') from exc


@dataclass(frozen=True, slots=True)
class BodyLength:
    design_length_mm: float
    cut_length_mm: float | None
    start_setback_mm: float = 0.0
    end_setback_mm: float = 0.0


@dataclass(frozen=True, slots=True)
class CutbackSolution:
    lengths: dict[str, BodyLength]
    kinds: dict[str, str]
    issues: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class JointChange:
    project: Project
    changed_count: int


def validate_joints(project):
    if project.joints and project.schema_version != '0.4.0':
        raise ValidationError('交接规则需要 0.4.0 工程格式；请使用新版本')
    used = set()
    for jid, j in project.joints.items():
        if not isinstance(j, ButtJoint) or jid != j.id:
            raise ValidationError('交接规则 ID 无效')
        if j.host_member_id not in project.members or j.branch_member_id not in project.members:
            raise ValidationError('交接规则引用了不存在的构件')
        end = j.branch_member_id, j.branch_end
        if end in used:
            raise ValidationError('同一杆端不能重复设置多条退让规则')
        used.add(end)


def _end_effect(project, catalog, host_id, branch_id, end, gap):
    """Return T/L + signed end adjustments from current design geometry."""
    h = derive_member_envelope(project, host_id, catalog)
    b = derive_member_envelope(project, branch_id, catalog)
    if any(project.members[x].anchor_ref != 'PROFILE_ORIGIN' for x in (host_id, branch_id)):
        raise ValidationError('交接暂不支持非中心截面基准')
    for mid in (host_id, branch_id):
        section = catalog.get(project.members[mid].profile_type_id).section
        if math.hypot(*section.origin_uv_mm) > TOL:
            raise ValidationError('交接暂不支持偏心截面原点')
    p, far = (b.start_mm, b.end_mm) if end == 'START' else (b.end_mm, b.start_mm)
    out = _normalize(_sub(far, p))
    if abs(_dot(out, h.axis_direction)) > ANGULAR_TOL:
        raise ValidationError('支杆必须垂直主杆；斜接/斜切尚未支持')
    basis = ((h.u_axis, h.section_width_mm/2), (h.v_axis, h.section_height_mm/2))
    normal, half = max(basis, key=lambda item: abs(_dot(out, item[0])))
    alignment = _dot(out, normal)
    if abs(abs(alignment)-1) > ANGULAR_TOL:
        raise ValidationError('支杆须垂直主杆某一截面外侧面；请调整截面朝向')
    local = _sub(p, h.start_mm)
    u, v, station = _dot(local, h.u_axis), _dot(local, h.v_axis), _dot(local, h.axis_direction)
    if abs(u) > h.section_width_mm/2+TOL or abs(v) > h.section_height_mm/2+TOL:
        raise ValidationError('支杆端点未在主杆轴线/截面外廓内；请先吸附摆准')
    if station < -TOL or station > h.length_mm+TOL:
        raise ValidationError('支杆端点超出主杆有限长度')
    signed = _dot(local, normal) * (1 if alignment > 0 else -1)
    if signed < -TOL:
        raise ValidationError('支杆从主杆背面穿入；请使用朝向支杆的接合面')
    trim = max(0.0, half-signed) + gap
    # Host-axis projection of branch half-section determines L end coverage.
    support = (abs(_dot(b.u_axis, h.axis_direction))*b.section_width_mm/2
               + abs(_dot(b.v_axis, h.axis_direction))*b.section_height_mm/2)
    effects = [(branch_id, end, trim, 'TRIM')]
    if station <= TOL:
        effects.append((host_id, 'START', -support, 'EXTEND'))
        kind = 'L'
    elif station >= h.length_mm-TOL:
        effects.append((host_id, 'END', -support, 'EXTEND'))
        kind = 'L'
    else:
        if station-support < -TOL or station+support > h.length_mm+TOL:
            raise ValidationError('T 接近主杆端部且接合面超出；移至端点用 L 接或留足长度')
        kind = 'T'
    return kind, effects


def solve_cutbacks(project, catalog, *, strict=False):
    """Evaluate, don't mutate. A pending rule cannot silently yield a cut-list.

    On any invalid rule the entire processing layer is suspended and all bodies
    display their unprocessed design extents. This is surfaced by the adapter UI.
    It lets a user reposition an unlinked rod rather than being trapped by trim.
    """
    validate_joints(project)
    base = {mid: member_length_mm(project, mid) for mid in project.members}
    effects, kinds, issues = {}, {}, []
    for jid, j in sorted(project.joints.items()):
        try:
            kind, values = _end_effect(project, catalog, j.host_member_id,
                                      j.branch_member_id, j.branch_end, j.gap_mm)
            kinds[jid] = kind
            for mid, side, offset, mode in values:
                effects.setdefault((mid, side), []).append((jid, offset, mode))
        except ValidationError as exc:
            issues.append(f'{jid}：{exc}')
    offsets = {}
    for end, values in effects.items():
        modes = {v[2] for v in values}
        if len(modes) > 1:
            issues.append(f'{end[0]} {end[1]} 同时要求退让和补长；请重新指定主支杆')
        offsets[end] = min(v[1] for v in values) if modes == {'EXTEND'} else max(v[1] for v in values)
    for mid, length in base.items():
        cut = length-offsets.get((mid, 'START'), 0)-offsets.get((mid, 'END'), 0)
        if cut <= TOL:
            issues.append(f'{mid} 退让后的实体长度不足；请减小间隙或增加设计长度')
    if issues and strict:
        raise ValidationError('交接待处理，禁止导出加工参考长度：'+'；'.join(issues))
    lengths = {mid: BodyLength(length, None) for mid, length in base.items()} if issues else {
        mid: BodyLength(length, length-offsets.get((mid, 'START'), 0)-offsets.get((mid, 'END'), 0),
                        offsets.get((mid, 'START'), 0), offsets.get((mid, 'END'), 0))
        for mid, length in base.items()}
    return CutbackSolution(lengths, kinds, tuple(issues))


def set_butt_joint(project, catalog, *, host_member_id, branch_member_id,
                   branch_end='AUTO', gap_mm=0.0):
    """Add/update a fully resolved square-cut joint without editing any axis."""
    if host_member_id not in project.members or branch_member_id not in project.members:
        raise ValidationError('请指定两根有效型材')
    if host_member_id == branch_member_id:
        raise ValidationError('主杆和支杆不能相同')
    gap = float(gap_mm)
    if not math.isfinite(gap) or gap < 0:
        raise ValidationError('交接间隙必须为非负有限毫米值')
    if branch_end == 'AUTO':
        choices = []
        for side in ('START', 'END'):
            try:
                _end_effect(project, catalog, host_member_id, branch_member_id, side, gap)
                choices.append(side)
            except ValidationError:
                pass
        if len(choices) != 1:
            raise ValidationError('无法唯一确定直角交接杆端；请摆准，并确认最后选中的是主杆')
        branch_end = choices[0]
    if branch_end not in {'START', 'END'}:
        raise ValidationError('无效的交接杆端')
    q = Project.from_dict(project.to_dict())
    existing = next((j for j in q.joints.values() if j.branch_member_id == branch_member_id
                     and j.branch_end == branch_end), None)
    if existing and existing.host_member_id != host_member_id:
        raise ValidationError('这个杆端已有另一主杆的交接；请先清除原交接')
    number = 1
    while f'J-{number:03d}' in (q.nodes.keys() | q.members.keys() | q.associations.keys() | q.joints.keys()):
        number += 1
    jid = existing.id if existing else f'J-{number:03d}'
    j = ButtJoint(jid, host_member_id, branch_member_id, branch_end, gap)
    if existing == j:
        solve_cutbacks(q, catalog, strict=True)
        return JointChange(q, 0)
    q.joints[jid] = j
    q.schema_version = '0.4.0'
    q.validate()
    solve_cutbacks(q, catalog, strict=True)
    for mid in (host_member_id, branch_member_id):
        q.members[mid].revision += 1
    return JointChange(q, 1)


def remove_joints(project, *, member_ids=()):
    mids = set(member_ids)
    if not mids or not mids <= project.members.keys():
        raise ValidationError('请选中需要清除交接的杆件')
    q = Project.from_dict(project.to_dict())
    removed = [j for j in q.joints.values() if j.host_member_id in mids or j.branch_member_id in mids]
    for j in removed:
        del q.joints[j.id]
    for mid in {m for j in removed for m in (j.host_member_id, j.branch_member_id)}:
        q.members[mid].revision += 1
    q.validate()
    return JointChange(q, len(removed))
