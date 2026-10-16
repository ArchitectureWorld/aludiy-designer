"""Explicit, undoable engineering associations, independent of Blender meshes.

COINCIDENT links keep independent stable Node IDs. ON_MEMBER is a one-way
attachment to a normalized station along an uncut host design axis. This is not
an assembly-joint, slot-fitting or structural-analysis solver.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
import math
from .errors import ValidationError
from .model import Project, Node, _finite_tuple, _non_empty

TOLERANCE_MM = 0.001

@dataclass(frozen=True, slots=True)
class SlotReference:
    """Revision-bound snapshot; profile definitions remain in the catalog.

    Identity is Member + ProfileType/revision + Interface ID. UV is an immutable
    document reference snapshot so pure/offline geometry needs no global catalog.
    Blender boundaries additionally compare the snapshot with that catalog.
    """
    profile_type_id: str
    catalog_revision: str
    interface_id: str
    center_uv_mm: tuple[float, float]
    interface_standard_id: str

    def __post_init__(self):
        for field in ('profile_type_id', 'catalog_revision', 'interface_id', 'interface_standard_id'):
            object.__setattr__(self, field, _non_empty(getattr(self, field), field))
        object.__setattr__(self, 'center_uv_mm', _finite_tuple(self.center_uv_mm, 2, 'slot UV'))

    def to_dict(self):
        return dict(profile_type_id=self.profile_type_id, catalog_revision=self.catalog_revision,
                    interface_id=self.interface_id, center_uv_mm=list(self.center_uv_mm),
                    interface_standard_id=self.interface_standard_id)

    @classmethod
    def from_dict(cls, d):
        try:
            return cls(d['profile_type_id'], d['catalog_revision'], d['interface_id'],
                       tuple(d['center_uv_mm']), d['interface_standard_id'])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError('槽轨引用数据不完整或无效') from exc


@dataclass(frozen=True, slots=True)
class Association:
    id: str
    kind: str
    node_ids: tuple[str, ...] = ()
    host_member_id: str = ''
    follower_node_id: str = ''
    station: float = 0.0
    slot_reference: SlotReference | None = None

    def to_dict(self):
        result = dict(id=self.id,kind=self.kind,node_ids=list(self.node_ids),
                      host_member_id=self.host_member_id,follower_node_id=self.follower_node_id,
                      station=self.station)
        if self.slot_reference is not None:
            result['slot_reference'] = self.slot_reference.to_dict()
        return result

    @classmethod
    def from_dict(cls,d):
        return cls(str(d['id']),str(d['kind']),tuple(d.get('node_ids',())),
                   str(d.get('host_member_id','')),str(d.get('follower_node_id','')),
                   float(d.get('station',0)),
                   SlotReference.from_dict(d['slot_reference']) if d.get('slot_reference') is not None else None)

@dataclass(frozen=True, slots=True)
class AssociationChange:
    project: Project
    changed_count: int


def exact_snap_delta(origin, target):
    """Never round authoritative target coordinates through a float32 Vector."""
    return tuple(float(target[i])-float(origin[i]) for i in range(3))


def project_to_member(project, member_id, point):
    m=project.members[member_id]
    a=project.nodes[m.start_node_id].position_mm; b=project.nodes[m.end_node_id].position_mm
    ab=tuple(b[i]-a[i] for i in range(3)); length2=sum(v*v for v in ab)
    if length2<=1e-12: raise ValidationError('主杆长度为零')
    t=sum((point[i]-a[i])*ab[i] for i in range(3))/length2
    p=tuple(a[i]+t*ab[i] for i in range(3))
    return t,p,math.dist(p,point)


def _groups_graph(project):
    parent={n:n for n in project.nodes}
    def root(n):
        while parent[n]!=n:
            parent[n]=parent[parent[n]]; n=parent[n]
        return n
    for r in project.associations.values():
        if r.kind=='COINCIDENT':
            for n in r.node_ids[1:]:
                a,b=root(r.node_ids[0]),root(n)
                if a!=b: parent[max(a,b)]=min(a,b)
    groups={}
    for n in parent: groups.setdefault(root(n),[]).append(n)
    followers={}; children={g:set() for g in groups}; degree={g:0 for g in groups}
    for r in project.associations.values():
        if r.kind not in {'ON_MEMBER','ON_SLOT'}: continue
        dest=root(r.follower_node_id); host=project.members[r.host_member_id]
        if dest in followers:
            previous=followers[dest]
            if (previous.kind==r.kind and previous.slot_reference==r.slot_reference and
                    previous.host_member_id==r.host_member_id and abs(previous.station-r.station)<1e-10):
                continue
            raise ValidationError('同一关联点有多个主杆，请减少选择或先解除关联')
        followers[dest]=r
        for source in {root(host.start_node_id),root(host.end_node_id)}:
            if source==dest: raise ValidationError('关联形成自依赖，请先解除冲突关系')
            if dest not in children[source]: children[source].add(dest); degree[dest]+=1
    ready=sorted(g for g,d in degree.items() if not d); ordered=[]
    while ready:
        g=ready.pop(0); ordered.append(g)
        for child in sorted(children[g]):
            degree[child]-=1
            if not degree[child]: ready.append(child)
    if len(ordered)!=len(groups): raise ValidationError('关联形成循环依赖，操作未提交')
    return root,groups,followers,ordered


def validate_associations(project):
    for key,r in project.associations.items():
        if not r.id or key!=r.id: raise ValidationError('关联 ID 无效')
        if r.kind=='COINCIDENT':
            if len(r.node_ids)<2 or len(set(r.node_ids))!=len(r.node_ids): raise ValidationError('端点关联至少需要两个不同节点')
            if not set(r.node_ids)<=set(project.nodes): raise ValidationError('关联引用了不存在的节点')
            p=project.nodes[r.node_ids[0]].position_mm
            if any(math.dist(p,project.nodes[n].position_mm)>TOLERANCE_MM for n in r.node_ids):
                raise ValidationError('端点关联位置不一致；请先吸附定位')
        elif r.kind in {'ON_MEMBER','ON_SLOT'}:
            if r.host_member_id not in project.members or r.follower_node_id not in project.nodes: raise ValidationError('杆身关联引用无效')
            valid_station = 0 <= r.station <= 1 if r.kind=='ON_SLOT' else 0 < r.station < 1
            if not math.isfinite(r.station) or not valid_station: raise ValidationError('杆身/槽轨关联位置无效')
            m=project.members[r.host_member_id]
            if r.follower_node_id in (m.start_node_id,m.end_node_id): raise ValidationError('不能附着于自身主杆端点')
            a=project.nodes[m.start_node_id].position_mm; b=project.nodes[m.end_node_id].position_mm
            expected=attachment_position(project,r)
            if math.dist(expected,project.nodes[r.follower_node_id].position_mm)>TOLERANCE_MM:
                raise ValidationError('杆身关联位置不一致')
        else: raise ValidationError('未知关联类型')
    _groups_graph(project)


def propagate_positions(project, replacements, *, changed_member_ids=()):
    if not project.associations: return dict(replacements)
    root,groups,followers,ordered=_groups_graph(project)
    pos={n:project.nodes[n].position_mm for n in project.nodes}
    touched=set(); changed_members=set(changed_member_ids)
    for group in ordered:
        nodes=groups[group]; direct=[replacements[n] for n in nodes if n in replacements]
        if direct and any(math.dist(direct[0],p)>TOLERANCE_MM for p in direct):
            raise ValidationError('同一关联点收到不同位移，操作未提交')
        desired=direct[0] if direct else None
        if group in followers:
            r=followers[group]; h=project.members[r.host_member_id]
            a,b=pos[h.start_node_id],pos[h.end_node_id]
            expected=attachment_position(project,r,pos)
            if desired is not None and math.dist(desired,expected)>TOLERANCE_MM:
                raise ValidationError('所选端点受主杆关联约束；请先解除关联，或同时移动主杆')
            if desired is not None or h.id in changed_members or root(h.start_node_id) in touched or root(h.end_node_id) in touched:
                desired=expected
        if desired is not None:
            touched.add(group)
            for n in nodes: pos[n]=tuple(desired)
    return {n:p for n,p in pos.items() if p!=project.nodes[n].position_mm}


def _selection(project,member_ids=(),node_ids=(),endpoint=None):
    mids=set(member_ids); nids=set(node_ids)
    if not mids<=set(project.members) or not nids<=set(project.nodes): raise ValidationError('所选对象已失效')
    if endpoint:
        mid,side=endpoint
        if mid not in project.members or side not in {'START','END'}: raise ValidationError('请先选择有效杆端')
        m=project.members[mid]; nids.add(m.start_node_id if side=='START' else m.end_node_id)
    for mid in mids:
        m=project.members[mid]; nids.update((m.start_node_id,m.end_node_id))
    return mids,nids


def _signature(r):
    return (r.kind,tuple(sorted(r.node_ids)),r.host_member_id,r.follower_node_id,r.slot_reference)


def create_associations(project, *, member_ids=(), node_ids=(), catalog=None):
    mids,nids=_selection(project,member_ids,node_ids)
    if len(nids)<2: raise ValidationError('请多选相接的杆件或重合节点')
    q=Project.from_dict(project.to_dict()); proposals=[]
    # Only coincident selected ends can form a joint. No automatic movement.
    pending=set(nids)
    while pending:
        n=min(pending); p=q.nodes[n].position_mm
        group=tuple(sorted(k for k in pending if math.dist(q.nodes[k].position_mm,p)<=TOLERANCE_MM))
        pending.difference_update(group)
        if len(group)>1: proposals.append(Association('', 'COINCIDENT',group))
    for nid in sorted(nids):
        hosts=[]
        for mid in sorted(mids):
            m=q.members[mid]
            if nid in (m.start_node_id,m.end_node_id): continue
            t,p,d=project_to_member(q,mid,q.nodes[nid].position_mm)
            if 1e-7<t<1-1e-7 and d<=TOLERANCE_MM: hosts.append((mid,t))
        if len(hosts)>1: raise ValidationError(f'{nid} 命中多个主杆，请缩小选择范围')
        if hosts:
            mid,t=hosts[0]; proposals.append(Association('','ON_MEMBER',(),mid,nid,t))
    if catalog is not None:
        validate_slot_catalog(q,catalog)
        proposals.extend(_slot_proposals(q,catalog,mids,nids))
    signatures={_signature(r) for r in q.associations.values()}
    count=0
    for r in proposals:
        if _signature(r) in signatures: continue
        number=1
        while f'R-{number:03d}' in q.associations: number+=1
        rid=f'R-{number:03d}'
        q.associations[rid]=replace(r,id=rid)
        signatures.add(_signature(r));count+=1
    if not proposals: raise ValidationError('选中对象没有有效接合处；先吸附到端点或杆身轴线，再创建关联')
    if count and q.schema_version=='0.1.0': q.schema_version='0.2.0'
    if any(r.kind=='ON_SLOT' for r in q.associations.values()): q.schema_version='0.3.0'
    q.validate()
    return AssociationChange(q,count)


def remove_associations(project, *, member_ids=(), node_ids=(),endpoint=None):
    mids,nids=_selection(project,member_ids,node_ids,endpoint)
    if not mids and not nids: raise ValidationError('请先选择需要解除关联的杆件或节点')
    q=Project.from_dict(project.to_dict()); removed=[]
    for rid,r in q.associations.items():
        if (r.kind=='COINCIDENT' and bool(set(r.node_ids)&nids)) or (r.kind in {'ON_MEMBER','ON_SLOT'} and (r.host_member_id in mids or r.follower_node_id in nids)):
            removed.append(rid)
    for rid in removed:
        r=q.associations[rid]
        remaining=tuple(n for n in r.node_ids if n not in nids)
        if r.kind=='COINCIDENT' and len(remaining)>=2:
            q.associations[rid]=Association(rid,'COINCIDENT',remaining)
        else: del q.associations[rid]
    # Legacy shared nodes are split only after an explicit unlink command.
    from .movement import _next_node_id
    split_count=0
    for nid in sorted(nids):
        refs=[(m.id,side) for m in q.members.values() for side in ('START','END')
              if (m.start_node_id if side=='START' else m.end_node_id)==nid]
        if len(refs)<2: continue
        chosen=[r for r in refs if (endpoint and r==tuple(endpoint)) or r[0] in mids or (not mids and not endpoint)]
        # Leave one reference on the original Node; detach other chosen owners.
        if len(chosen)==len(refs): chosen=chosen[1:]
        for mid,side in chosen:
            new=_next_node_id(q);q.add_node(Node(new,q.nodes[nid].position_mm))
            m=q.members[mid]
            if side=='START': m.start_node_id=new
            else:m.end_node_id=new
            m.revision+=1;split_count+=1
    q.validate()
    return AssociationChange(q,len(removed)+split_count)


def append_independent_member(project, start_mm, end_mm, profile_type_id):
    """Add one member with two owned nodes even when their positions coincide."""
    from .model import Member
    from .movement import _next_node_id
    q=Project.from_dict(project.to_dict())
    start=_next_node_id(q);q.add_node(Node(start,tuple(start_mm)))
    end=_next_node_id(q);q.add_node(Node(end,tuple(end_mm)))
    i=max((int(k[2:]) for k in q.members if k.startswith('M-') and k[2:].isdigit()),default=0)+1
    while f'M-{i:03d}' in q.members or f'M-{i:03d}' in q.nodes:i+=1
    mid=f'M-{i:03d}'
    q.add_member(Member(mid,start,end,profile_type_id))
    return q,mid


def attachment_position(project, relation, positions=None):
    """Resolve one-way host station from current nodes AND section roll."""
    h = project.members[relation.host_member_id]
    pos = positions or {n: item.position_mm for n, item in project.nodes.items()}
    a, b = pos[h.start_node_id], pos[h.end_node_id]
    point = tuple(a[i]+relation.station*(b[i]-a[i]) for i in range(3))
    if relation.kind != 'ON_SLOT':
        if relation.slot_reference is not None:
            raise ValidationError('只有槽轨关联可携带槽引用')
        return point
    ref = relation.slot_reference
    if project.schema_version != '0.3.0' or ref is None:
        raise ValidationError('槽轨关联需要 0.3.0 数据格式和完整接口引用')
    if h.profile_type_id != ref.profile_type_id or h.anchor_ref != 'PROFILE_ORIGIN':
        raise ValidationError('主杆已换型或截面基准不匹配，请先解除槽轨关联并重新指定')
    from .geometry import _section_frame, _normalize, _sub
    u, v = _section_frame(_normalize(_sub(b,a)), h.roll_deg)
    return tuple(point[i]+u[i]*ref.center_uv_mm[0]+v[i]*ref.center_uv_mm[1] for i in range(3))


def slot_reference(project, host_member_id, interface_id, catalog):
    if host_member_id not in project.members:
        raise ValidationError('目标槽轨的主杆不存在')
    host = project.members[host_member_id]
    if host.anchor_ref != 'PROFILE_ORIGIN':
        raise ValidationError('目标主杆使用尚未支持的截面定位基准')
    profile = catalog.get(host.profile_type_id)
    slot = profile.section.interfaces.get(interface_id)
    if slot is None or slot.kind != 'T_SLOT_RAIL':
        raise ValidationError('目标型材不存在该有效槽轨，请重新指定')
    return SlotReference(profile.profile_type_id, profile.catalog_revision, slot.id,
                         slot.center_uv_mm, slot.interface_standard_id)


def validate_slot_catalog(project, catalog):
    for r in project.associations.values():
        if r.kind == 'ON_SLOT':
            expected=slot_reference(project,r.host_member_id,r.slot_reference.interface_id,catalog)
            if expected != r.slot_reference:
                raise ValidationError(f'{r.id} 槽轨引用与目录版本或几何不一致，禁止静默适配')


def _slot_proposals(project, catalog, host_ids, node_ids, *, interface_id=None):
    from .profile_editing import interface_rails
    rails = [(mid, rail) for mid in sorted(host_ids) for rail in interface_rails(project,mid,catalog)
             if interface_id is None or rail.interface_id==interface_id]
    proposals=[]
    for nid in sorted(node_ids):
        point=project.nodes[nid].position_mm; matches=[]
        for mid,rail in rails:
            m=project.members[mid]
            if nid in (m.start_node_id,m.end_node_id): continue
            a,b=rail.start_mm,rail.end_mm; d=tuple(b[i]-a[i] for i in range(3))
            length2=sum(x*x for x in d)
            if length2<=1e-12: raise ValidationError('目标主杆为零长度')
            t=sum((point[i]-a[i])*d[i] for i in range(3))/length2
            # Clamp numerical noise at finite rail endpoints, never snap to extension.
            if t < -1e-12 or t > 1+1e-12: continue
            t=max(0.,min(1.,t))
            target=tuple(a[i]+t*d[i] for i in range(3))
            if math.dist(point,target)<=TOLERANCE_MM:
                ref=slot_reference(project,mid,rail.interface_id,catalog)
                matches.append(Association('', 'ON_SLOT', (), mid, nid, t, ref))
        if len(matches)>1:
            raise ValidationError(f'{nid} 命中多个槽轨，请指定一个槽轨目标或缩小选择范围')
        proposals.extend(matches)
    return proposals


def create_slot_associations(project, catalog, *, host_member_id, interface_id,
                             member_ids=(), node_ids=(), endpoint=None):
    """Create only requested slot links; no movement, graph guessing or welding."""
    slot_reference(project,host_member_id,interface_id,catalog)
    validate_slot_catalog(project,catalog)
    _, nids = _selection(project,member_ids,node_ids,endpoint)
    q=Project.from_dict(project.to_dict())
    proposals=_slot_proposals(q,catalog,{host_member_id},nids,interface_id=interface_id)
    if not proposals:
        raise ValidationError('选中端点尚未位于目标槽轨；先用 G 或画线吸附定位，再创建关联')
    signatures={_signature(r) for r in q.associations.values()}; count=0
    for r in proposals:
        if _signature(r) in signatures: continue
        i=1
        while f'R-{i:03d}' in q.associations:i+=1
        q.associations[f'R-{i:03d}']=replace(r,id=f'R-{i:03d}')
        signatures.add(_signature(r));count+=1
    q.schema_version='0.3.0'
    q.validate()
    return AssociationChange(q,count)
