"""Non-destructive local recipe options over existing square-cut processing.

Options are computed from a snapshot, not progressively from preceding previews.
A three-member recipe is atomic, but persists as ordinary stable ButtJoint rules.
"""
from __future__ import annotations
from dataclasses import dataclass
from itertools import product
import math
from .model import Project
from .errors import ValidationError
from .geometry import _dot, _sub
from .joints import (ButtJoint, CutbackSolution, JointChange,
                     solve_cutbacks, _end_effect, _body_box, TOL, ANGULAR_TOL)


@dataclass(frozen=True, slots=True)
class JointOption:
    host_member_id: str
    member_ids: tuple[str, ...]
    kind: str
    project: Project | None
    solution: CutbackSolution | None
    message: str
    changed_count: int
    before_bounds: tuple
    after_bounds: tuple | None

    @property
    def valid(self):
        return self.project is not None and not self.message


def selection_members(project, member_ids):
    ids = tuple(sorted(set(member_ids)))
    if len(ids) not in (2, 3) or any(mid not in project.members for mid in ids):
        raise ValidationError('请选择 2 或 3 根完整有效型材，单个端点不作为交接选区')
    if len(ids) == 3:
        points = [(project.nodes[project.members[mid].start_node_id].position_mm,
                   project.nodes[project.members[mid].end_node_id].position_mm) for mid in ids]
        common = [ps for ps in product(*points)
                  if max(math.dist(ps[0], p) for p in ps) <= TOL]
        if len(common) != 1:
            raise ValidationError('首版三向角点需要三根型材端点位于同一位置；错位三向暂未支持')
        directions = []
        for a, b in points:
            d = _sub(b, a); length = math.sqrt(_dot(d, d))
            if length <= TOL:
                raise ValidationError('角点型材长度不足')
            directions.append(tuple(x/length for x in d))
        if any(abs(_dot(directions[i], directions[j])) > ANGULAR_TOL
               for i in range(3) for j in range(i+1, 3)):
            raise ValidationError('首版三向角点需要轴线两两垂直；斜向和共线方案暂未支持')
    return ids


def body_corners(project, catalog, mid, solution=None):
    """8 actual envelope vertices for preview/bounds; no Blender math rounding."""
    solution = solution or solve_cutbacks(project, catalog)
    offsets = {}
    if not solution.issues:
        for key, v in solution.lengths.items():
            offsets[key, 'START'] = v.start_setback_mm
            offsets[key, 'END'] = v.end_setback_mm
    center, axes, half = _body_box(project, catalog, mid, offsets)
    return tuple(tuple(center[i]+sum(signs[j]*half[j]*axes[j][i] for j in range(3))
                       for i in range(3)) for signs in product((-1, 1), repeat=3))


def group_bounds(project, catalog, member_ids, solution=None):
    solution = solution or solve_cutbacks(project, catalog)
    points = [p for mid in member_ids for p in body_corners(project, catalog, mid, solution)]
    return (tuple(min(p[i] for p in points) for i in range(3)),
            tuple(max(p[i] for p in points) for i in range(3)))


def _candidate(project, catalog, ids, host, gap):
    q = Project.from_dict(project.to_dict())
    local = {jid: j for jid, j in q.joints.items()
             if j.host_member_id in ids and j.branch_member_id in ids}
    for jid in local:
        del q.joints[jid]
    kinds = []
    for branch in ids:
        if branch == host:
            continue
        ends = []
        for side in ('START', 'END'):
            try:
                kind, _ = _end_effect(q, catalog, host, branch, side, gap)
                ends.append((side, kind))
            except ValidationError:
                pass
        if len(ends) != 1:
            raise ValidationError('该贯通方案没有唯一合法接合端；请摆准直角接点或改选贯通杆')
        end, kind = ends[0]
        if any(j.branch_member_id == branch and j.branch_end == end for j in q.joints.values()):
            raise ValidationError(f'{branch} {end} 已连接未选中的主杆；保留原规则，请先明确清除冲突')
        existing = next((j for j in local.values() if
                         j.host_member_id == host and j.branch_member_id == branch and j.branch_end == end), None)
        occupied = q.nodes.keys() | q.members.keys() | q.associations.keys() | q.joints.keys() | local.keys()
        i = 1
        while f'J-{i:03d}' in occupied:
            i += 1
        jid = existing.id if existing else f'J-{i:03d}'
        q.joints[jid] = ButtJoint(jid, host, branch, end, gap)
        kinds.append(kind)
    q.schema_version = '0.4.0'
    q.validate()
    result = solve_cutbacks(q, catalog, strict=True)
    changed = len({k for k in project.joints.keys() | q.joints.keys()
                   if project.joints.get(k) != q.joints.get(k)})
    if changed:
        for mid in ids:
            q.members[mid].revision += 1
    return q, result, ('CORNER3' if len(ids) == 3 else kinds[0]), changed


def joint_choices(project, catalog, *, member_ids, gap_mm=0.0):
    """Stable candidate order independent of selection order; invalid choices explain why."""
    project.validate()
    ids = selection_members(project, member_ids)
    try:
        gap = float(gap_mm)
    except (TypeError, ValueError) as exc:
        raise ValidationError('交接间隙必须是非负有限毫米值') from exc
    if not math.isfinite(gap) or gap < 0:
        raise ValidationError('交接间隙必须是非负有限毫米值')
    before = group_bounds(project, catalog, ids)
    choices = []
    for host in ids:
        try:
            q, result, kind, count = _candidate(project, catalog, ids, host, gap)
            choices.append(JointOption(host, ids, kind, q, result, '', count,
                                       before, group_bounds(q, catalog, ids, result)))
        except ValidationError as exc:
            choices.append(JointOption(host, ids, 'CORNER3' if len(ids) == 3 else 'L/T',
                                       None, None, str(exc), 0, before, None))
    return tuple(choices)


def apply_joint_choice(project, catalog, *, member_ids, host_member_id, gap_mm=0.0):
    option = next((c for c in joint_choices(project, catalog, member_ids=member_ids, gap_mm=gap_mm)
                   if c.host_member_id == host_member_id), None)
    if option is None:
        raise ValidationError('所指定贯通杆不在交接选区中')
    if not option.valid:
        raise ValidationError(option.message)
    return JointChange(option.project, option.changed_count)
