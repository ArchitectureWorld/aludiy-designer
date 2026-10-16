"""Slot references must resolve by semantic ID, never profile dimensions."""
from pathlib import Path
from dataclasses import replace
import copy
import math
import pytest
from aludiy_core import Project, Node, Member, ProfileCatalog
from aludiy_core.errors import AluDIYError
from aludiy_core import associations as a
from aludiy_core.profile_editing import interface_rails, edit_profiles
from aludiy_core.movement import preview_move
from aludiy_core.geometry import resize_member

CAT = ProfileCatalog.from_source_directory(Path(__file__).parents[2]/'catalog'/'profiles')
P40='generic:tslot-2040@0.1'; P20='generic:tslot-2020@0.1'; SID='FACE_PV.S1'

def api():
    assert hasattr(a,'create_slot_associations'), 'slot attachment API missing'
    return a

def base(station=.4, side=SID):
    p=Project('P-SLOT','alpha-2026.10')
    p.add_node(Node('N-1',(1000.123456789,2000.987654321,300)))
    p.add_node(Node('N-2',(1000.123456789,2000.987654321,1300)))
    p.add_member(Member('M-1','N-1','N-2',P40))
    rail=next(r for r in interface_rails(p,'M-1',CAT) if r.interface_id==side)
    point=tuple(rail.start_mm[i]+station*(rail.end_mm[i]-rail.start_mm[i]) for i in range(3))
    p.add_node(Node('N-3',point)); p.add_node(Node('N-4',(point[0]+600,point[1],point[2])))
    p.add_member(Member('M-2','N-3','N-4',P20))
    return p

def linked(station=.4):
    return api().create_slot_associations(base(station),CAT,host_member_id='M-1',interface_id=SID,member_ids=['M-2']).project

def test_create_keeps_nodes_and_member_ids_and_is_atomic():
    p=base(); before=p.to_dict()
    result=api().create_slot_associations(p,CAT,host_member_id='M-1',interface_id=SID,member_ids=['M-1','M-2','M-2'])
    q=result.project
    assert result.changed_count==1 and p.to_dict()==before
    assert q.to_dict()['nodes']==before['nodes'] and q.to_dict()['members']==before['members']
    r=next(iter(q.associations.values()))
    assert r.kind=='ON_SLOT' and r.host_member_id=='M-1' and r.follower_node_id=='N-3'
    assert r.station==pytest.approx(.4) and r.slot_reference.interface_id==SID
    assert r.slot_reference.profile_type_id==P40 and r.slot_reference.catalog_revision==CAT.get(P40).catalog_revision
    assert q.schema_version=='0.3.0'
    assert Project.from_dict(q.to_dict()).to_dict()==q.to_dict()

def test_unique_slot_match_in_multiselection_create():
    api(); p=base(); q=a.create_associations(p,member_ids=['M-1','M-2'],catalog=CAT).project
    assert {r.kind for r in q.associations.values()}=={'ON_SLOT'}

def test_idempotent_create_on_same_slot():
    p=linked(); r=api().create_slot_associations(p,CAT,host_member_id='M-1',interface_id=SID,node_ids=['N-3'])
    assert r.changed_count==0 and r.project.to_dict()==p.to_dict()

@pytest.mark.parametrize('t',[0, .4, 1])
def test_translation_and_resize_follow_station(t):
    p=linked(t); old=p.to_dict();q=preview_move(p,(75,-20,30),member_ids=['M-1']).project
    assert p.to_dict()==old
    expected=tuple(p.nodes['N-3'].position_mm[i]+(75,-20,30)[i] for i in range(3))
    assert q.nodes['N-3'].position_mm==pytest.approx(expected,abs=1e-10)
    assert q.nodes['N-4'].position_mm==p.nodes['N-4'].position_mm
    resize_member(q,'M-1',1500,anchor='START')
    assert q.nodes['N-3'].position_mm[2]==pytest.approx(330+t*1500)

@pytest.mark.parametrize('angle',[90,-90,45,180])
def test_roll_follows_slot_preserves_id_and_only_attached_end(angle):
    p=linked();old=p.to_dict();q=edit_profiles(p,['M-1'],CAT,roll_deg=angle).project
    rail=next(r for r in interface_rails(q,'M-1',CAT) if r.interface_id==SID)
    expected=tuple(rail.start_mm[i]+.4*(rail.end_mm[i]-rail.start_mm[i]) for i in range(3))
    assert q.nodes['N-3'].position_mm==pytest.approx(expected,abs=1e-9)
    assert q.nodes['N-4'].position_mm==p.nodes['N-4'].position_mm
    assert q.associations==p.associations
    assert p.to_dict()==old and q.members['M-2'].revision==p.members['M-2'].revision+1

def test_host_orientation_change_recomputes_world_offset():
    p=linked();q=preview_move(p,(100,300,0),node_ids=['N-2']).project
    rail=next(r for r in interface_rails(q,'M-1',CAT) if r.interface_id==SID)
    assert q.nodes['N-3'].position_mm==pytest.approx(tuple(rail.start_mm[i]+.4*(rail.end_mm[i]-rail.start_mm[i]) for i in range(3)))

def test_linked_host_cannot_change_type_but_noop_and_follower_change_allowed():
    p=linked();old=p.to_dict()
    with pytest.raises(AluDIYError,match='槽轨'):
        edit_profiles(p,['M-1','M-2'],CAT,profile_type_id=P20)
    assert p.to_dict()==old
    assert edit_profiles(p,['M-1'],CAT,profile_type_id=P40).project.to_dict()==old
    assert edit_profiles(p,['M-2'],CAT,profile_type_id=P40).project.members['M-2'].profile_type_id==P40

def test_unlink_keeps_geometry_and_allows_independent_edit_and_host_swap():
    p=linked();q=a.remove_associations(p,member_ids=['M-2']).project
    assert not q.associations and q.to_dict()['nodes']==p.to_dict()['nodes']
    preview_move(q,(20,0,0),member_ids=['M-2'])
    edit_profiles(q,['M-1'],CAT,profile_type_id=P20)

def test_detach_during_move_and_delete_host_clean_reference():
    p=linked(); q=preview_move(p,(30,0,0),endpoint=('M-2','START'),detach=True).project
    assert not q.associations
    p.remove_members(['M-1']); assert not p.associations and 'M-2' in p.members

def test_direct_follower_move_blocked_but_group_translation_allowed():
    p=linked();old=p.to_dict()
    with pytest.raises(AluDIYError):preview_move(p,(30,0,0),node_ids=['N-3'])
    assert p.to_dict()==old
    q=preview_move(p,(30,10,-5),member_ids=['M-1','M-2']).project
    for n in p.nodes:assert q.nodes[n].position_mm==pytest.approx(tuple(p.nodes[n].position_mm[i]+(30,10,-5)[i] for i in range(3)))

@pytest.mark.parametrize('sid',['FACE_PV.S999','END_A.CORE_0','', 'FACE_NV.S9'])
def test_missing_interface_fails_without_mutation(sid):
    p=base(); old=p.to_dict()
    with pytest.raises(AluDIYError):api().create_slot_associations(p,CAT,host_member_id='M-1',interface_id=sid,node_ids=['N-3'])
    assert p.to_dict()==old

def test_other_lane_is_not_equivalent_and_gap_is_not_teleport():
    p=base();old=p.to_dict()
    with pytest.raises(AluDIYError):api().create_slot_associations(p,CAT,host_member_id='M-1',interface_id='FACE_PV.S0',node_ids=['N-3'])
    assert p.to_dict()==old

def test_self_and_cycle_rejected():
    p=base(); api()
    with pytest.raises(AluDIYError):a.create_slot_associations(p,CAT,host_member_id='M-1',interface_id=SID,node_ids=['N-1'])
    p=linked();r=next(iter(p.associations.values()))
    # A follower's coincident group cannot contain a source node of its host.
    q=copy.deepcopy(p);q.associations['R-cycle']=a.Association('R-cycle','COINCIDENT',('N-3','N-1'))
    with pytest.raises(AluDIYError):q.validate()

def test_corrupt_snapshot_or_station_fail_closed():
    p=linked();old=p.to_dict()
    for field,value in [('interface_id',''),('center_uv_mm',[float('nan'),0]),('profile_type_id',P20)]:
        data=copy.deepcopy(old); data['associations'][0]['slot_reference'][field]=value
        with pytest.raises(AluDIYError):Project.from_dict(data)
    for t in [-.1,1.1,float('inf')]:
        data=copy.deepcopy(old);data['associations'][0]['station']=t
        with pytest.raises(AluDIYError):Project.from_dict(data)

def test_catalog_snapshot_mismatch_is_rejected():
    p=linked(); api().validate_slot_catalog(p,CAT)
    altered=ProfileCatalog({x.profile_type_id:type(x).from_dict(x.to_dict()) for x in CAT})
    altered.get(P40).section.interfaces[SID].center_uv_mm=(999,999)
    with pytest.raises(AluDIYError):a.validate_slot_catalog(p,altered)

def test_relabel_new_schema_to_old_is_rejected():
    data=linked().to_dict();data['schema_version']='0.2.0'
    with pytest.raises(AluDIYError):Project.from_dict(data)

def test_multiple_followers_and_partial_unlink():
    p=base();p.add_node(Node('N-5',p.nodes['N-3'].position_mm));p.add_node(Node('N-6',(1600,2500,700)))
    p.add_member(Member('M-3','N-5','N-6',P20));api()
    p=a.create_associations(p,member_ids=['M-1','M-2','M-3'],catalog=CAT).project
    q=a.remove_associations(p,member_ids=['M-2']).project
    t=preview_move(q,(20,0,0),member_ids=['M-1']).project
    assert t.nodes['N-3'].position_mm==q.nodes['N-3'].position_mm
    assert t.nodes['N-5'].position_mm[0]==pytest.approx(q.nodes['N-5'].position_mm[0]+20)

def test_roll_cascade_into_axis_attachment():
    p=linked();p.add_node(Node('N-5',tuple((p.nodes['N-3'].position_mm[i]+p.nodes['N-4'].position_mm[i])/2 for i in range(3))))
    p.add_node(Node('N-6',(2000,2600,900)));p.add_member(Member('M-3','N-5','N-6',P20))
    p=a.create_associations(p,member_ids=['M-2','M-3']).project
    q=edit_profiles(p,['M-1'],CAT,roll_deg=90).project
    assert q.nodes['N-5'].position_mm==pytest.approx(tuple((q.nodes['N-3'].position_mm[i]+q.nodes['N-4'].position_mm[i])/2 for i in range(3)))


def test_roll_collapse_rejected_without_half_update():
    p=base(); future=edit_profiles(p,['M-1'],CAT,roll_deg=180).project
    rail=next(r for r in interface_rails(future,'M-1',CAT) if r.interface_id==SID)
    p.nodes['N-4'].position_mm=tuple(rail.start_mm[i]+.4*(rail.end_mm[i]-rail.start_mm[i]) for i in range(3))
    p=api().create_slot_associations(p,CAT,host_member_id='M-1',interface_id=SID,node_ids=['N-3']).project
    old=p.to_dict()
    with pytest.raises(AluDIYError):edit_profiles(p,['M-1'],CAT,roll_deg=180)
    assert p.to_dict()==old


def test_ambiguous_host_slots_need_explicit_target():
    p=base();p.add_node(Node('N-5',p.nodes['N-1'].position_mm));p.add_node(Node('N-6',p.nodes['N-2'].position_mm))
    p.add_member(Member('M-3','N-5','N-6',P40));old=p.to_dict();api()
    with pytest.raises(AluDIYError,match='多个槽轨'):a.create_associations(p,catalog=CAT,member_ids=['M-1','M-2','M-3'])
    assert p.to_dict()==old
    q=a.create_slot_associations(p,CAT,host_member_id='M-1',interface_id=SID,node_ids=['N-3']).project
    assert len(q.associations)==1


def test_slot_snapshot_missing_data_does_not_fall_back_to_axis():
    data=linked().to_dict();data['associations'][0].pop('slot_reference')
    with pytest.raises(AluDIYError):Project.from_dict(data)
