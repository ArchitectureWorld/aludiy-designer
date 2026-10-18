from pathlib import Path
from dataclasses import replace
import pytest
from aludiy_core import Project, Node, Member, ProfileCatalog
from aludiy_core import movement
from aludiy_core.associations import Association, create_slot_associations
from aludiy_core.joints import ButtJoint
from aludiy_core.errors import ValidationError
P20='generic:tslot-2020@0.1'; P40='generic:tslot-2040@0.1'
CAT=ProfileCatalog.from_source_directory(Path(__file__).parents[2]/'catalog/profiles')

def copy(p,ids):
    assert hasattr(movement,'duplicate_members'), 'engineering copy API missing'
    return movement.duplicate_members(p,ids)

def base(shared=False):
    q=Project('P-COPY','alpha-2026.10')
    for n,xyz in [('N-001',(0,0,0)),('N-002',(0,0,1000)),('N-003',(0,0,1000)),('N-004',(600,0,1000))]:q.add_node(Node(n,xyz))
    q.add_member(Member('M-001','N-001','N-002',P20,roll_deg=90,revision=7))
    q.add_member(Member('M-002','N-002' if shared else 'N-003','N-004',P20))
    return q

def linked(kind='COINCIDENT'):
    q=base();q.schema_version='0.4.0'
    q.associations['A-001']=Association('A-001','COINCIDENT',('N-002','N-003'))
    q.joints['J-001']=ButtJoint('J-001','M-001','M-002','START',2)
    q.validate();return q

def test_single_fresh_identity_original_unchanged():
    p=linked();raw=p.to_dict();r=copy(p,['M-002']);q=r.project
    assert p.to_dict()==raw and len(q.members)==3
    assert set(r.member_map)=={'M-002'} and not set(r.member_map.values()) & set(p.members)
    m=q.members[r.member_map['M-002']]
    assert m.start_node_id not in p.nodes and m.end_node_id not in p.nodes
    assert len(q.associations)==1 and len(q.joints)==1 and r.dropped_external_count==2
    assert m.profile_type_id==P20 and m.revision==1

def test_group_copies_only_internal_graph_and_preserves_properties():
    p=linked();r=copy(p,['M-002','M-001','M-001']);q=r.project
    assert len(q.members)==4 and len(q.nodes)==8
    a=q.associations[r.association_ids[0]];j=q.joints[r.joint_ids[0]]
    assert set(a.node_ids)=={r.node_map['N-002'],r.node_map['N-003']}
    assert j.host_member_id==r.member_map['M-001'] and j.branch_member_id==r.member_map['M-002'] and j.gap_mm==2
    assert q.members[r.member_map['M-001']].roll_deg==90 and r.dropped_external_count==0
    assert q.schema_version=='0.4.0'
    moved=movement.preview_move(q,(200.123456789,0,0),member_ids=r.member_map.values()).project
    for nid in p.nodes:assert moved.nodes[nid].position_mm==p.nodes[nid].position_mm
    assert Project.from_dict(moved.to_dict()).to_dict()==moved.to_dict()

def test_internal_shared_nodes_copied_once_never_shared_with_original():
    p=base(True);r=copy(p,p.members);q=r.project
    a,b=(q.members[r.member_map[x]] for x in ['M-001','M-002'])
    assert a.end_node_id==b.start_node_id and a.end_node_id!='N-002'
    assert len(r.node_map)==3

def test_partial_coincident_group_keeps_internal_pair_only():
    p=linked();p.add_node(Node('N-005',(0,0,1000)))
    p.associations['A-001']=Association('A-001','COINCIDENT',('N-002','N-003','N-005'))
    r=copy(p,p.members);new=r.project.associations[r.association_ids[0]]
    assert len(new.node_ids)==2 and 'N-005' not in new.node_ids and r.dropped_external_count==1

@pytest.mark.parametrize('ids',[[],['bad'],['M-001','bad']])
def test_invalid_selection_atomic(ids):
    p=base();raw=p.to_dict()
    with pytest.raises(ValidationError):copy(p,ids)
    assert p.to_dict()==raw

def test_generators_and_repeated_copy_never_reuse_existing_ids():
    p=base();a=copy(p,(m for m in p.members));b=copy(a.project,a.member_map.values())
    assert len(b.project.members)==6 and not set(b.member_map.values()) & set(a.project.members)
    assert copy(p,['M-002','M-001']).project.to_dict()==copy(p,['M-001','M-002']).project.to_dict()

def test_slot_attachment_internal_reference_remapped_not_uv_modified():
    p=base();p.nodes['N-003'].position_mm=(10,0,500);p.nodes['N-004'].position_mm=(600,0,500)
    p=create_slot_associations(p,CAT,host_member_id='M-001',interface_id='FACE_NV.S0',member_ids=['M-002']).project
    r=copy(p,p.members);assert len(r.association_ids)==1
    original=next(iter(p.associations.values()));a=r.project.associations[r.association_ids[0]]
    assert a.host_member_id==r.member_map['M-001'] and a.follower_node_id==r.node_map['N-003']
    assert a.slot_reference==original.slot_reference and a.station==original.station
    movement.preview_move(r.project,(20,40,100),member_ids=r.member_map.values())

def test_external_slot_host_dropped_follower_is_free():
    p=base();p.nodes['N-003'].position_mm=(0,0,500)
    p.schema_version='0.2.0';p.associations['A-1']=Association('A-1','ON_MEMBER',host_member_id='M-001',follower_node_id='N-003',station=.5)
    r=copy(p,['M-002']);assert not r.association_ids and r.dropped_external_count==1
    movement.preview_move(r.project,(123,456,0),member_ids=r.member_map.values())

def test_internal_host_follower_chain_remapped():
    p=base();p.nodes['N-003'].position_mm=(0,0,500);p.nodes['N-004'].position_mm=(600,0,500)
    p.schema_version='0.2.0';p.associations['A-1']=Association('A-1','ON_MEMBER',host_member_id='M-001',follower_node_id='N-003',station=.5)
    r=copy(p,p.members);assert len(r.association_ids)==1
    q=movement.preview_move(r.project,(250,0,0),member_ids=[r.member_map['M-001']]).project
    assert q.nodes[r.node_map['N-003']].position_mm==(250,0,500)
    assert q.nodes['N-003'].position_mm==(0,0,500)

def test_legacy_shared_node_outside_selection_is_reported_as_dependency():
    p=base(shared=True)
    r=copy(p,['M-001'])
    assert r.dropped_external_count==1
    assert r.project.members[r.member_map['M-001']].end_node_id!=p.members['M-002'].start_node_id
