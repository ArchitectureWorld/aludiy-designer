"""Transactional previews for engineering G movement; no Blender dependency.

The original project never changes. Every mouse update derives a fresh candidate
from the same start snapshot, so selection aliases and shared nodes move once.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
from typing import Iterable
from .model import Project, Node
from .errors import ValidationError
from .geometry import _apply_node_positions, _vector3

@dataclass(frozen=True, slots=True)
class MovePreview:
    project: Project
    moved_node_ids: tuple[str, ...]
    affected_member_ids: tuple[str, ...]
    detached_node_id: str | None = None


def movement_node_ids(project: Project, *, member_ids: Iterable[str] = (),
                      node_ids: Iterable[str] = (), endpoint: tuple[str, str] | None = None
                      ) -> tuple[str, ...]:
    if endpoint is not None:
        owner, side = endpoint
        if owner not in project.members or side not in {'START', 'END'}:
            raise ValidationError('Invalid endpoint owner or side')
        member = project.members[owner]
        return (member.start_node_id if side == 'START' else member.end_node_id,)
    nodes = set(node_ids)
    for mid in set(member_ids):
        if mid not in project.members:
            raise ValidationError(f'Unknown member {mid}')
        m = project.members[mid]
        nodes.update((m.start_node_id, m.end_node_id))
    if not nodes or not nodes.issubset(project.nodes):
        raise ValidationError('Select valid engineering nodes or members')
    return tuple(sorted(nodes))


def _next_node_id(project: Project) -> str:
    highest = max((int(k[2:]) for k in project.nodes if k.startswith('N-') and k[2:].isdigit()), default=0)
    candidate = f'N-{highest+1:03d}'
    while candidate in project.nodes or candidate in project.members:
        highest += 1
        candidate = f'N-{highest+1:03d}'
    return candidate


def preview_move(project: Project, delta_mm, *, member_ids: Iterable[str] = (),
                 node_ids: Iterable[str] = (), endpoint: tuple[str, str] | None = None,
                 detach: bool = False) -> MovePreview:
    """Preview displacement, optionally detach exactly one explicitly owned end.

    Zero displacement is a true no-op (including topology and revisions).
    Positional coincidence never changes connectivity.
    """
    delta = _vector3(delta_mm, 'displacement')
    targets = movement_node_ids(project, member_ids=member_ids, node_ids=node_ids, endpoint=endpoint)
    if detach and endpoint is None:
        raise ValidationError('Detach requires an explicit member endpoint')
    candidate = Project.from_dict(project.to_dict())
    if math.dist(delta, (0, 0, 0)) <= 1e-6:
        return MovePreview(candidate, (), ())
    split = None
    if detach:
        owner, side = endpoint
        old_id = targets[0]
        referenced_elsewhere = any(m.id != owner and old_id in (m.start_node_id, m.end_node_id)
                                  for m in candidate.members.values())
        if referenced_elsewhere:
            split = _next_node_id(candidate)
            candidate.add_node(Node(split, candidate.nodes[old_id].position_mm))
            m = candidate.members[owner]
            if side == 'START':
                m.start_node_id = split
            else:
                m.end_node_id = split
            targets = (split,)
    replacements = {nid: tuple(candidate.nodes[nid].position_mm[i]+delta[i] for i in range(3))
                    for nid in targets}
    change = _apply_node_positions(candidate, replacements)
    # A topology-only replacement must never create a collapsed physical member.
    candidate.validate()
    return MovePreview(candidate, change.moved_node_ids, change.affected_member_ids, split)
