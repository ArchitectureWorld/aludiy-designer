import importlib
import math
import pytest
from aludiy_core import Project, Member, Node
from aludiy_core.errors import ValidationError

PROFILE = 'generic:tslot-2020@0.1'

def frame():
    p=Project('P-MOVE','alpha-2026.10')
    for key, xyz in [('N-001',(0,0,800)),('N-002',(1200,0,800)),('N-003',(0,600,800)),('N-004',(0,0,0))]:
        p.add_node(Node(key, xyz))
    for key,a,b in [('M-001','N-001','N-002'),('M-002','N-001','N-003'),('M-003','N-004','N-001')]:
        p.add_member(Member(key,a,b,PROFILE))
    return p

def preview(p, delta, **kwargs):
    # Fails on the absent feature (not on test collection/import).
    import aludiy_core
    assert hasattr(aludiy_core, 'preview_move'), 'preview_move is not implemented'
    return aludiy_core.preview_move(p, delta, **kwargs)

def test_endpoint_keep_moves_shared_node_and_all_incident_members():
    p=frame(); before=p.to_dict()
    r=preview(p,(0,0,100),endpoint=('M-003','END'))
    assert p.to_dict()==before
    assert r.project.nodes['N-001'].position_mm==(0,0,900)
    assert r.project.nodes['N-004'].position_mm==(0,0,0)
    assert r.affected_member_ids==('M-001','M-002','M-003')
    assert len(r.project.nodes)==4 and r.detached_node_id is None

def test_detach_splits_only_owned_endpoint_and_does_not_move_others():
    p=frame()
    r=preview(p,(0,0,100),endpoint=('M-003','END'),detach=True)
    new=r.project.members['M-003'].end_node_id
    assert new != 'N-001' and new == r.detached_node_id
    assert r.project.nodes[new].position_mm==(0,0,900)
    assert r.project.nodes['N-001'].position_mm==(0,0,800)
    assert r.project.members['M-001'].to_dict()==p.members['M-001'].to_dict()
    assert r.affected_member_ids==('M-003',)
    assert len(r.project.nodes)==5

def test_zero_displacement_never_creates_a_split_or_revision():
    p=frame(); r=preview(p,(0,0,0),endpoint=('M-003','END'),detach=True)
    assert r.project.to_dict()==p.to_dict()
    assert r.affected_member_ids==() and r.detached_node_id is None

def test_whole_member_and_duplicate_selection_move_each_node_only_once():
    p=frame()
    r=preview(p,(100,0,200),member_ids=['M-001','M-001','M-002'],node_ids=['N-001'])
    for nid in ['N-001','N-002','N-003']:
        assert r.project.nodes[nid].position_mm==tuple(a+b for a,b in zip(p.nodes[nid].position_mm,(100,0,200)))
    assert r.project.nodes['N-004'].position_mm==p.nodes['N-004'].position_mm
    assert all(r.project.members[mid].revision==p.members[mid].revision+1 for mid in p.members)

def test_preview_repeated_from_original_never_accumulates_delta_or_new_ids():
    p=frame()
    r1=preview(p,(0,0,100),endpoint=('M-003','END'),detach=True)
    r2=preview(p,(0,0,200),endpoint=('M-003','END'),detach=True)
    assert r1.detached_node_id==r2.detached_node_id
    assert len(r2.project.nodes)==5
    assert r2.project.nodes[r2.detached_node_id].position_mm==(0,0,1000)

def test_detaching_an_unshared_end_does_not_allocate_a_node():
    p=frame(); r=preview(p,(0,0,-100),endpoint=('M-003','START'),detach=True)
    assert len(r.project.nodes)==4 and r.detached_node_id is None
    assert r.project.members['M-003'].start_node_id=='N-004'

def test_coincident_nodes_are_not_implicitly_connected_or_welded():
    p=frame(); p.add_node(Node('N-005',(0,0,800)))
    r=preview(p,(0,0,100),node_ids=['N-005'])
    assert r.project.nodes['N-001'].position_mm==(0,0,800)
    assert r.affected_member_ids==()

def test_detach_requires_unambiguous_owner():
    p=frame()
    with pytest.raises(ValidationError,match='endpoint'):
        preview(p,(0,0,100),node_ids=['N-001'],detach=True)

@pytest.mark.parametrize('delta',[(0,0,-800),(math.nan,0,0),(0,0,math.inf),(0,0)])
def test_invalid_candidate_leaves_original_unchanged(delta):
    p=frame(); before=p.to_dict()
    with pytest.raises(ValidationError):
        preview(p,delta,endpoint=('M-003','END'))
    assert p.to_dict()==before

def test_unknown_selection_rejected_before_modification():
    p=frame()
    with pytest.raises(ValidationError):
        preview(p,(1,0,0),member_ids=['M-MISSING'])

def test_detach_roundtrip_preserves_topology():
    p=frame(); r=preview(p,(0,0,100),endpoint=('M-003','END'),detach=True)
    assert Project.from_dict(r.project.to_dict()).to_dict()==r.project.to_dict()
