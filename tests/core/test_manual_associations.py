import math
import pytest
from aludiy_core import Project, Node, Member
from aludiy_core.movement import preview_move
from aludiy_core.errors import ValidationError

def api():
    import aludiy_core
    assert hasattr(aludiy_core,'associations'), 'manual-association module missing'
    return aludiy_core.associations

def project():
    p=Project('P-MANUAL','alpha-2026.10')
    for nid,point in [('N-1',(0,0,0)),('N-2',(0,0,1000)),('N-3',(0,0,500)),('N-4',(800,0,500)),('N-5',(0,0,1000)),('N-6',(600,0,1000))]:
        p.add_node(Node(nid,point))
    for mid,a,b in [('M-1','N-1','N-2'),('M-2','N-3','N-4'),('M-3','N-5','N-6')]:
        p.add_member(Member(mid,a,b,'generic:tslot-2020@0.1'))
    return p

def test_create_host_and_end_links_preserves_ids_positions_and_input():
    a=api(); p=project(); before=p.to_dict()
    q=a.create_associations(p,member_ids=['M-1','M-2','M-3']).project
    assert p.to_dict()==before
    assert {r.kind for r in q.associations.values()}=={'COINCIDENT','ON_MEMBER'}
    assert set(q.nodes)==set(p.nodes) and set(q.members)==set(p.members)
    assert all(q.nodes[n].position_mm==p.nodes[n].position_mm for n in p.nodes)
    assert Project.from_dict(q.to_dict()).to_dict()==q.to_dict()

def test_host_translation_propagates_only_attached_ends():
    a=api(); p=a.create_associations(project(),member_ids=['M-1','M-2','M-3']).project
    q=preview_move(p,(100,0,0),member_ids=['M-1']).project
    assert q.nodes['N-3'].position_mm==(100,0,500)
    assert q.nodes['N-4'].position_mm==(800,0,500)
    assert q.nodes['N-5'].position_mm==(100,0,1000)
    assert len(q.members)==3

def test_unassociated_coincident_nodes_do_not_follow():
    api(); p=project(); q=preview_move(p,(100,0,0),member_ids=['M-1']).project
    assert q.nodes['N-5'].position_mm==(0,0,1000)

def test_remove_preserves_geometry_then_allows_independent_move():
    a=api(); p=a.create_associations(project(),member_ids=['M-1','M-2']).project
    q=a.remove_associations(p,member_ids=['M-2']).project
    assert not q.associations
    assert [n.to_dict() for n in q.nodes.values()]==[n.to_dict() for n in p.nodes.values()]
    r=preview_move(q,(100,0,0),member_ids=['M-2']).project
    assert r.nodes['N-1'].position_mm==(0,0,0)

def test_conflicting_child_move_is_rejected_and_original_unchanged():
    a=api(); p=a.create_associations(project(),member_ids=['M-1','M-2']).project; old=p.to_dict()
    with pytest.raises(ValidationError): preview_move(p,(50,0,0),member_ids=['M-2'])
    assert p.to_dict()==old

def test_group_move_deduplicates_and_preserves_all_lengths():
    a=api(); p=a.create_associations(project(),member_ids=['M-1','M-2','M-3']).project
    q=preview_move(p,(100,20,5),member_ids=list(p.members)).project
    for nid in p.nodes: assert q.nodes[nid].position_mm==tuple(v+d for v,d in zip(p.nodes[nid].position_mm,(100,20,5)))

def test_create_selected_nodes_only_and_idempotence():
    a=api(); p=project(); q=a.create_associations(p,node_ids=['N-2','N-5']).project
    assert len(q.associations)==1
    r=a.create_associations(q,node_ids=['N-5','N-2']).project
    assert q.to_dict()==r.to_dict()

def test_no_match_does_not_teleport():
    a=api(); p=project()
    with pytest.raises(ValidationError): a.create_associations(p,node_ids=['N-1','N-6'])
    assert p.nodes['N-6'].position_mm==(600,0,1000)

def test_old_shared_nodes_preserved_and_explicit_remove_splits_selected_member():
    a=api(); p=project(); p.members['M-3'].start_node_id='N-2'; del p.nodes['N-5']; old=p.to_dict()
    assert Project.from_dict(old).to_dict()==old
    q=a.remove_associations(p,member_ids=['M-3']).project
    assert q.members['M-3'].start_node_id!='N-2'
    assert q.nodes[q.members['M-3'].start_node_id].position_mm==(0,0,1000)
    assert p.to_dict()==old

def test_delete_host_cleans_relations_but_keeps_child():
    a=api(); p=a.create_associations(project(),member_ids=['M-1','M-2']).project
    p.remove_members(['M-1']); assert not p.associations
    assert 'M-2' in p.members; Project.from_dict(p.to_dict())

def test_resize_host_follows_normalized_station():
    a=api(); from aludiy_core.geometry import resize_member
    p=a.create_associations(project(),member_ids=['M-1','M-2']).project
    resize_member(p,'M-1',1200,anchor='START')
    assert p.nodes['N-3'].position_mm==(0,0,600)

def test_ambiguous_hosts_are_rejected():
    a=api(); p=project()
    p.add_node(Node('N-7',(0,0,200)));p.add_node(Node('N-8',(0,0,800)))
    p.add_member(Member('M-4','N-7','N-8','generic:tslot-2020@0.1'))
    with pytest.raises(ValidationError): a.create_associations(p,member_ids=['M-1','M-2','M-4'])

def test_detach_existing_explicit_endpoint_relation():
    a=api(); p=a.create_associations(project(),member_ids=['M-1','M-2']).project
    q=preview_move(p,(100,0,0),endpoint=('M-2','START'),detach=True).project
    assert not q.associations and q.nodes['N-3'].position_mm==(100,0,500)

def test_snap_target_delta_uses_float64_and_does_not_join():
    a=api(); p=project()
    p.nodes['N-3'].position_mm=(2426.612345678,1096.789012345,-234.012345678)
    target=(2298.712312345,895.123412345,276.623412345)
    delta=a.exact_snap_delta(p.nodes['N-3'].position_mm,target)
    q=preview_move(p,delta,endpoint=('M-2','START')).project
    assert math.dist(q.nodes['N-3'].position_mm,target)<1e-9 and not q.associations

def test_partial_unlink_keeps_unselected_pair_related():
    a=api();p=project();p.add_node(Node('N-7',(0,0,1000)))
    p=a.create_associations(p,node_ids=['N-2','N-5','N-7']).project
    q=a.remove_associations(p,node_ids=['N-5']).project
    assert len(q.associations)==1
    assert set(next(iter(q.associations.values())).node_ids)=={'N-2','N-7'}

def test_independent_sample_endpoints_do_not_link_unless_requested():
    api();from aludiy_core.io import append_sample_frame
    p=project();q=append_sample_frame(p,1200,600,'generic:tslot-2020@0.1').project
    new=[m for m in q.members.values() if m.id not in p.members]
    ids=[nid for m in new for nid in (m.start_node_id,m.end_node_id)]
    assert len(set(ids))==8

def test_two_followers_can_attach_at_same_station_on_one_host():
    a=api();p=project();p.add_node(Node('N-7',(0,0,500)));p.add_node(Node('N-8',(0,600,500)))
    p.add_member(Member('M-4','N-7','N-8','generic:tslot-2020@0.1'))
    q=a.create_associations(p,member_ids=['M-1','M-2','M-4']).project
    r=preview_move(q,(100,0,0),member_ids=['M-1']).project
    assert r.nodes['N-3'].position_mm==r.nodes['N-7'].position_mm==(100,0,500)
    r=a.remove_associations(r,member_ids=['M-2']).project
    t=preview_move(r,(100,0,0),member_ids=['M-1']).project
    assert t.nodes['N-7'].position_mm==(200,0,500) and t.nodes['N-3'].position_mm==(100,0,500)
