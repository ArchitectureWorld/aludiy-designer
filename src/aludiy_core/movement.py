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
        from .associations import remove_associations
        candidate = remove_associations(candidate, endpoint=endpoint).project
        owner,side=endpoint
        m=candidate.members[owner]
        new=m.start_node_id if side=='START' else m.end_node_id
        if new!=targets[0]: split=new; targets=(new,)
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


@dataclass(frozen=True, slots=True)
class DuplicatePreview:
    project: Project
    member_map: dict[str, str]
    node_map: dict[str, str]
    association_ids: tuple[str, ...]
    joint_ids: tuple[str, ...]
    dropped_external_count: int


def duplicate_members(project: Project, member_ids: Iterable[str]) -> DuplicatePreview:
    """Copy the selected induced engineering graph, never Blender cache identities.

    Originals stay unchanged. Shared nodes within the selection are copied once;
    explicit links and processing rules are retained only inside the copied set.
    The result is a candidate, suitable for cancelable placement before commit.
    """
    from dataclasses import replace
    ids = tuple(sorted(set(member_ids)))
    if not ids or not set(ids).issubset(project.members):
        raise ValidationError('请选择有效的完整型材进行工程复制')
    q = Project.from_dict(project.to_dict())
    used = set(q.nodes) | set(q.members) | set(q.associations) | set(q.joints)
    counters = {}
    def fresh(prefix):
        number = counters.get(prefix, max((int(k[len(prefix)+1:]) for k in used
            if k.startswith(prefix+'-') and k[len(prefix)+1:].isdigit()), default=0))
        while True:
            number += 1
            value = f'{prefix}-{number:03d}'
            if value not in used:
                used.add(value); counters[prefix] = number
                return value
    source_nodes = sorted({n for mid in ids for n in
        (project.members[mid].start_node_id, project.members[mid].end_node_id)})
    nmap = {n: fresh('N') for n in source_nodes}
    mmap = {m: fresh('M') for m in ids}
    for old, new in nmap.items():
        q.add_node(Node(new, project.nodes[old].position_mm))
    for old, new in mmap.items():
        member = project.members[old]
        q.add_member(replace(member, id=new, start_node_id=nmap[member.start_node_id],
                             end_node_id=nmap[member.end_node_id], revision=1))
    copied_links, copied_joints = [], []
    # A legacy shared node is an external dependency even without an explicit
    # Association record. Report each boundary node once, not every incident rod.
    outside_nodes = {n for mid,m in project.members.items() if mid not in mmap
                     for n in (m.start_node_id,m.end_node_id)}
    dropped = len(outside_nodes.intersection(nmap))
    for old in sorted(project.associations):
        r = project.associations[old]
        if r.kind == 'COINCIDENT':
            internal = tuple(nmap[n] for n in r.node_ids if n in nmap)
            if internal and len(internal) != len(r.node_ids):
                dropped += 1
            if len(internal) < 2:
                continue
            new = replace(r, id=fresh('A'), node_ids=internal)
        else:
            host_in = r.host_member_id in mmap
            follower_in = r.follower_node_id in nmap
            if not (host_in and follower_in):
                dropped += int(host_in or follower_in)
                continue
            new = replace(r, id=fresh('A'), host_member_id=mmap[r.host_member_id],
                          follower_node_id=nmap[r.follower_node_id])
        q.associations[new.id] = new
        copied_links.append(new.id)
    for old in sorted(project.joints):
        j = project.joints[old]
        host_in, branch_in = j.host_member_id in mmap, j.branch_member_id in mmap
        if not (host_in and branch_in):
            dropped += int(host_in or branch_in)
            continue
        new = replace(j, id=fresh('J'), host_member_id=mmap[j.host_member_id],
                      branch_member_id=mmap[j.branch_member_id])
        q.joints[new.id] = new
        copied_joints.append(new.id)
    q.validate()
    return DuplicatePreview(q, mmap, nmap, tuple(copied_links), tuple(copied_joints), dropped)
