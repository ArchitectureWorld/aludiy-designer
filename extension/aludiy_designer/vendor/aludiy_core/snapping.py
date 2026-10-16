"""Engineering snap candidates and transactional endpoint reconnection.

Screen projection is injected: this module has no bpy, mesh or GPU dependency.
Geometry coincidence alone never joins anything; a confirmed explicit target ID
is required, and ground candidates deliberately have no node ID.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Iterable

from .errors import ValidationError
from .model import Project, Node, Vector3
from .movement import movement_node_ids, preview_move, _next_node_id
from .geometry import _vector3

JOIN_TOLERANCE_MM = 1e-4
Projection = Callable[[Vector3], tuple[float, float] | None]


@dataclass(frozen=True, slots=True)
class SnapCandidate:
    kind: str
    position_mm: Vector3
    distance_px: float
    node_id: str | None = None
    member_id: str | None = None
    station: float | None = None

    @property
    def key(self) -> str:
        return self.node_id or (f"{self.kind}:{self.member_id}" if self.member_id else self.kind)


@dataclass(frozen=True, slots=True)
class ReconnectPreview:
    project: Project
    moved_node_ids: tuple[str, ...]
    affected_member_ids: tuple[str, ...]
    detached_node_id: str | None = None
    reconnected_node_id: str | None = None
    removed_node_id: str | None = None


def allowed_position(origin_mm, position_mm, axis: str | None, plane_lock=False) -> bool:
    if axis is None:
        return True
    if axis not in {'X', 'Y', 'Z'}:
        raise ValidationError('Invalid snap axis')
    k = 'XYZ'.index(axis)
    indices = (k,) if plane_lock else tuple(i for i in range(3) if i != k)
    return all(abs(position_mm[i] - origin_mm[i]) <= JOIN_TOLERANCE_MM for i in indices)


def node_candidates(project: Project, *, origin_mm, cursor_px, project_point: Projection,
                    excluded_node_ids: Iterable[str] = (), radius_px=14.0,
                    axis: str | None = None, plane_lock=False,
                    exact_position_mm=None) -> tuple[SnapCandidate, ...]:
    """Unique stable Node targets in the cursor aperture and allowed movement plane.

    Numeric input is not rounded: only an exactly reached node is a candidate.
    At ambiguous projected overlaps callers expose candidate cycling.
    """
    excluded = set(excluded_node_ids)
    result = []
    for nid, node in project.nodes.items():
        if nid in excluded or not allowed_position(origin_mm, node.position_mm, axis, plane_lock):
            continue
        if exact_position_mm is not None and math.dist(exact_position_mm, node.position_mm) > JOIN_TOLERANCE_MM:
            continue
        point = project_point(node.position_mm)
        if point is None:
            continue
        distance = math.dist(cursor_px, point)
        if distance <= radius_px:
            result.append(SnapCandidate('NODE', node.position_mm, distance, nid))
    return tuple(sorted(result, key=lambda c: (c.distance_px, c.node_id)))


def ground_candidate(origin_mm, raw_position_mm, *, ground_mm: float,
                     project_point: Projection, radius_px=14.0, axis=None,
                     plane_lock=False) -> SnapCandidate | None:
    """Vertical projection to an elevation, never a support/constraint relationship.

    Reject visually coincident but depth-ambiguous top-view projections. A pixel
    aperture measures proximity in other views, consistent with endpoint snapping.
    """
    ground = float(ground_mm)
    if not math.isfinite(ground):
        raise ValidationError('Ground elevation must be finite')
    position = (float(raw_position_mm[0]), float(raw_position_mm[1]), ground)
    if not allowed_position(origin_mm, position, axis, plane_lock):
        return None
    raw_screen, target_screen = project_point(raw_position_mm), project_point(position)
    if raw_screen is None or target_screen is None:
        return None
    gap = math.dist(raw_screen, target_screen)
    height = abs(raw_position_mm[2] - ground)
    if gap <= 0.01 and height > JOIN_TOLERANCE_MM:
        return None  # top-view depth cannot be guessed
    if gap > radius_px:
        return None
    return SnapCandidate('GROUND', position, gap)


def preview_reconnect(project: Project, delta_mm, *, anchor_node_id: str,
                      target_node_id: str, member_ids: Iterable[str] = (),
                      node_ids: Iterable[str] = (), endpoint=None,
                      detach=False) -> ReconnectPreview:
    """Move selected engineering nodes and connect exactly the indicated anchor.

    KEEP remaps all references to the moving junction. DETACH only remaps the
    explicitly owned rod end. Original project and stationary target are never
    mutated; zero-distance topology changes remain real undoable operations.
    """
    delta = _vector3(delta_mm, 'displacement')
    spec = dict(member_ids=tuple(member_ids), node_ids=tuple(node_ids), endpoint=endpoint)
    moving = set(movement_node_ids(project, **spec))
    if anchor_node_id not in moving or target_node_id not in project.nodes:
        raise ValidationError('连接源或目标节点无效')
    if detach and endpoint is None:
        raise ValidationError('分离连接需要先选定一根型材的具体端点')
    # A detached shared source is stationary for its remaining rods.
    shared_detach = bool(detach and any(m.id != endpoint[0] and anchor_node_id in
                         (m.start_node_id, m.end_node_id) for m in project.members.values()))
    excluded = moving - ({anchor_node_id} if shared_detach else set())
    if target_node_id in excluded:
        raise ValidationError('不能连接到本次一起移动的节点')
    requested = tuple(project.nodes[anchor_node_id].position_mm[i] + delta[i] for i in range(3))
    if math.dist(requested, project.nodes[target_node_id].position_mm) > JOIN_TOLERANCE_MM:
        raise ValidationError('端点尚未到达目标，不能只合并数据而保留错误位置')
    result = preview_move(project, delta, detach=detach, **spec)
    candidate = result.project
    source_id = result.detached_node_id or anchor_node_id
    # preview_move intentionally does nothing for delta=0. Explicit reconnect is
    # different: a co-located endpoint may need detaching without geometric motion.
    if shared_detach and result.detached_node_id is None and target_node_id != anchor_node_id:
        source_id = _next_node_id(candidate)
        candidate.add_node(Node(source_id, candidate.nodes[anchor_node_id].position_mm))
        owner, side = endpoint
        member = candidate.members[owner]
        if side == 'START':
            member.start_node_id = source_id
        else:
            member.end_node_id = source_id
    if source_id == target_node_id:
        return ReconnectPreview(candidate, result.moved_node_ids, result.affected_member_ids)
    affected = set(result.affected_member_ids)
    for member in candidate.members.values():
        changed = False
        if member.start_node_id == source_id:
            member.start_node_id = target_node_id
            changed = True
        if member.end_node_id == source_id:
            member.end_node_id = target_node_id
            changed = True
        a = candidate.nodes[member.start_node_id].position_mm
        b = candidate.nodes[member.end_node_id].position_mm
        if member.start_node_id == member.end_node_id or math.dist(a, b) <= 1e-6:
            raise ValidationError(f'连接会使 {member.id} 变成零长度，操作未提交')
        if changed:
            affected.add(member.id)
    # Every old-source reference has been remapped. Do not delete unrelated nodes.
    del candidate.nodes[source_id]
    for mid in affected:
        candidate.members[mid].revision = project.members[mid].revision + 1
    candidate.validate()
    moved = tuple(sorted((set(result.moved_node_ids) - {source_id}) | {target_node_id}))
    return ReconnectPreview(candidate, moved, tuple(sorted(affected)), None,
                            target_node_id, source_id)


def member_candidates(project: Project, *, origin_mm, cursor_px, project_point,
                      ray_origin_mm, ray_direction, excluded_member_ids=(),
                      radius_px=14.0, axis=None, plane_lock=False,
                      exact_position_mm=None):
    """Closest design-axis station and midpoint in the screen aperture.

    Ray/line minimization uses float64 Python values. This is axis snapping,
    not a claim that the physical slot or outside face has been fitted.
    """
    result=[];excluded=set(excluded_member_ids)
    for mid,m in project.members.items():
        if mid in excluded: continue
        a=project.nodes[m.start_node_id].position_mm;b=project.nodes[m.end_node_id].position_mm
        u=tuple(b[i]-a[i] for i in range(3));r=tuple(ray_origin_mm[i]-a[i] for i in range(3))
        d=tuple(float(v) for v in ray_direction); dn=math.sqrt(sum(v*v for v in d))
        d=tuple(v/dn for v in d); uu=sum(v*v for v in u);ud=sum(u[i]*d[i] for i in range(3))
        denominator=uu-ud*ud
        if uu<=1e-12: continue
        t=(sum(u[i]*r[i] for i in range(3))-ud*sum(d[i]*r[i] for i in range(3)))/denominator if denominator>1e-9 else .5
        if axis is not None:
            k='XYZ'.index(axis); fixed=(k,) if plane_lock else tuple(i for i in range(3) if i!=k)
            ts=[(origin_mm[i]-a[i])/u[i] for i in fixed if abs(u[i])>1e-12]
            if ts:t=ts[0]
        if exact_position_mm is not None:
            t=sum((exact_position_mm[i]-a[i])*u[i] for i in range(3))/uu
        for station,kind in ((.5,'MIDPOINT'),(max(0.0,min(1.0,t)),'AXIS')):
            if not 1e-8<station<1-1e-8:continue
            point=tuple(a[i]+station*u[i] for i in range(3))
            if not allowed_position(origin_mm,point,axis,plane_lock):continue
            if exact_position_mm is not None and math.dist(point,exact_position_mm)>JOIN_TOLERANCE_MM:continue
            screen=project_point(point)
            if screen is None:continue
            distance=math.dist(cursor_px,screen)
            if distance<=radius_px:
                result.append(SnapCandidate(kind,point,distance,None,mid,station))
    # A midpoint has priority only in its own aperture. End nodes are considered
    # first by the caller, avoiding an ambiguous endpoint/body weld.
    return tuple(sorted(result,key=lambda c:(c.distance_px,0 if c.kind=='MIDPOINT' else 1,c.member_id)))
