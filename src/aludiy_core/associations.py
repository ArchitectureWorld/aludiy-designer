"""Explicit, undoable engineering associations, independent of Blender meshes.

COINCIDENT links keep independent stable Node IDs. ON_MEMBER is a one-way
attachment to a normalized station along an uncut host design axis. This is not
an assembly-joint, slot-fitting or structural-analysis solver.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
from .errors import ValidationError
from .model import Project, Node

TOLERANCE_MM = 0.001

@dataclass(frozen=True, slots=True)
class Association:
    id: str
    kind: str
    node_ids: tuple[str, ...] = ()
    host_member_id: str = ''
    follower_node_id: str = ''
    station: float = 0.0

    def to_dict(self):
        return dict(id=self.id,kind=self.kind,node_ids=list(self.node_ids),
                    host_member_id=self.host_member_id,follower_node_id=self.follower_node_id,
                    station=self.station)

    @classmethod
    def from_dict(cls,d):
        return cls(str(d['id']),str(d['kind']),tuple(d.get('node_ids',())),
                   str(d.get('host_member_id','')),str(d.get('follower_node_id','')),
                   float(d.get('station',0)))

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
        if r.kind!='ON_MEMBER': continue
        dest=root(r.follower_node_id); host=project.members[r.host_member_id]
        if dest in followers:
            previous=followers[dest]
            if previous.host_member_id==r.host_member_id and abs(previous.station-r.station)<1e-10:
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
        elif r.kind=='ON_MEMBER':
            if r.host_member_id not in project.members or r.follower_node_id not in project.nodes: raise ValidationError('杆身关联引用无效')
            if not math.isfinite(r.station) or not 0<r.station<1: raise ValidationError('杆身关联位置无效')
            m=project.members[r.host_member_id]
            if r.follower_node_id in (m.start_node_id,m.end_node_id): raise ValidationError('不能附着于自身主杆端点')
            a=project.nodes[m.start_node_id].position_mm; b=project.nodes[m.end_node_id].position_mm
            expected=tuple(a[i]+r.station*(b[i]-a[i]) for i in range(3))
            if math.dist(expected,project.nodes[r.follower_node_id].position_mm)>TOLERANCE_MM:
                raise ValidationError('杆身关联位置不一致')
        else: raise ValidationError('未知关联类型')
    _groups_graph(project)


def propagate_positions(project, replacements):
    if not project.associations: return dict(replacements)
    root,groups,followers,ordered=_groups_graph(project)
    pos={n:project.nodes[n].position_mm for n in project.nodes}
    touched=set()
    for group in ordered:
        nodes=groups[group]; direct=[replacements[n] for n in nodes if n in replacements]
        if direct and any(math.dist(direct[0],p)>TOLERANCE_MM for p in direct):
            raise ValidationError('同一关联点收到不同位移，操作未提交')
        desired=direct[0] if direct else None
        if group in followers:
            r=followers[group]; h=project.members[r.host_member_id]
            a,b=pos[h.start_node_id],pos[h.end_node_id]
            expected=tuple(a[i]+r.station*(b[i]-a[i]) for i in range(3))
            if desired is not None and math.dist(desired,expected)>TOLERANCE_MM:
                raise ValidationError('所选端点受主杆关联约束；请先解除关联，或同时移动主杆')
            if desired is not None or root(h.start_node_id) in touched or root(h.end_node_id) in touched:
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
    return (r.kind,tuple(sorted(r.node_ids)),r.host_member_id,r.follower_node_id)


def create_associations(project, *, member_ids=(), node_ids=()):
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
    signatures={_signature(r) for r in q.associations.values()}
    count=0
    for r in proposals:
        if _signature(r) in signatures: continue
        number=1
        while f'R-{number:03d}' in q.associations: number+=1
        rid=f'R-{number:03d}'
        q.associations[rid]=Association(rid,r.kind,r.node_ids,r.host_member_id,r.follower_node_id,r.station)
        signatures.add(_signature(r));count+=1
    if not proposals: raise ValidationError('选中对象没有有效接合处；先吸附到端点或杆身轴线，再创建关联')
    if count: q.schema_version='0.2.0'
    q.validate()
    return AssociationChange(q,count)


def remove_associations(project, *, member_ids=(), node_ids=(),endpoint=None):
    mids,nids=_selection(project,member_ids,node_ids,endpoint)
    if not mids and not nids: raise ValidationError('请先选择需要解除关联的杆件或节点')
    q=Project.from_dict(project.to_dict()); removed=[]
    for rid,r in q.associations.items():
        if (r.kind=='COINCIDENT' and bool(set(r.node_ids)&nids)) or (r.kind=='ON_MEMBER' and (r.host_member_id in mids or r.follower_node_id in nids)):
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
