import importlib
import math
import pytest
from aludiy_core import Project, Node, Member
from aludiy_core.errors import ValidationError
from aludiy_core.movement import preview_move


def module():
    spec = importlib.util.find_spec('aludiy_core.snapping')
    assert spec is not None, 'Engineering snap/reconnect module missing'
    return importlib.import_module('aludiy_core.snapping')


def frame():
    p = Project('P-USER', 'alpha-2026.10')
    for nid, pos in [('N-001',(0,0,800)), ('N-002',(1200,0,800)),
                     ('N-003',(0,600,800)), ('N-004',(0,0,0)), ('N-005',(200,0,900)),
                     ('N-006',(800,0,900))]:
        p.add_node(Node(nid,pos))
    for mid,a,b in [('M-001','N-001','N-002'),('M-002','N-001','N-003'),
                    ('M-003','N-004','N-001'),('M-004','N-005','N-006')]:
        p.add_member(Member(mid,a,b,'generic:tslot-2020@0.1'))
    return p


def test_detach_return_and_reconnect_restores_shared_id_without_mutating_original():
    s=module(); original=frame()
    separated=preview_move(original,(0,0,100),endpoint=('M-003','END'),detach=True).project
    payload=separated.to_dict(); source=separated.members['M-003'].end_node_id
    result=s.preview_reconnect(separated,(0,0,-100),anchor_node_id=source,
                               target_node_id='N-001',endpoint=('M-003','END'))
    assert result.project.members['M-003'].end_node_id=='N-001'
    assert source not in result.project.nodes
    assert separated.to_dict()==payload
    assert result.reconnected_node_id=='N-001'
    moved=preview_move(result.project,(0,0,10),node_ids=['N-001'])
    assert set(moved.affected_member_ids)=={'M-001','M-002','M-003'}


def test_keep_merges_entire_moved_junction_but_target_does_not_move():
    s=module(); p=frame(); before=p.to_dict()
    r=s.preview_reconnect(p,(200,0,100),anchor_node_id='N-001',target_node_id='N-005',node_ids=['N-001'])
    assert p.to_dict()==before
    assert r.project.nodes['N-005'].position_mm==p.nodes['N-005'].position_mm
    assert 'N-001' not in r.project.nodes
    for mid in ['M-001','M-002']: assert r.project.members[mid].start_node_id=='N-005'
    assert r.project.members['M-003'].end_node_id=='N-005'
    assert r.project.members['M-004'].to_dict()==p.members['M-004'].to_dict()
    for mid in r.affected_member_ids: assert r.project.members[mid].revision==p.members[mid].revision+1


def test_detach_then_snap_to_new_target_only_changes_chosen_rod():
    s=module(); p=frame()
    r=s.preview_reconnect(p,(200,0,100),anchor_node_id='N-001',target_node_id='N-005',endpoint=('M-003','END'),detach=True)
    assert r.project.members['M-003'].end_node_id=='N-005'
    for mid in ('M-001','M-002','M-004'): assert r.project.members[mid].to_dict()==p.members[mid].to_dict()
    assert r.project.nodes['N-001'].position_mm==(0,0,800)
    assert len(r.project.nodes)==len(p.nodes)


def test_connect_overlapping_independent_endpoint_at_zero_displacement():
    s=module(); p=frame(); p.add_node(Node('N-007',(0,0,800)))
    p.members['M-003'].end_node_id='N-007'
    r=s.preview_reconnect(p,(0,0,0),anchor_node_id='N-007',target_node_id='N-001',endpoint=('M-003','END'))
    assert r.project.members['M-003'].end_node_id=='N-001'
    assert 'N-007' not in r.project.nodes
    assert r.affected_member_ids==('M-003',)
    assert r.project.members['M-003'].revision==2


def test_zero_distance_detach_then_attach_does_not_steal_other_members():
    s=module(); p=frame(); p.add_node(Node('N-007',(0,0,800)))
    r=s.preview_reconnect(p,(0,0,0),anchor_node_id='N-001',target_node_id='N-007',endpoint=('M-003','END'),detach=True)
    assert r.project.members['M-003'].end_node_id=='N-007'
    assert r.project.members['M-001'].start_node_id=='N-001'
    assert r.project.nodes['N-001'].position_mm==(0,0,800)


@pytest.mark.parametrize('delta,target,anchor,spec', [
    ((0,0,0),'N-005','N-001',dict(node_ids=['N-001'])),
    ((1200,0,0),'N-002','N-001',dict(endpoint=('M-001','START'))),
    ((0,0,0),'N-002','N-001',dict(member_ids=['M-001'])),
    ((0,0,0),'N-MISSING','N-001',dict(node_ids=['N-001'])),
    ((0,0,0),'N-001','N-004',dict(node_ids=['N-005'])),
])
def test_invalid_join_is_atomic(delta,target,anchor,spec):
    s=module(); p=frame(); before=p.to_dict()
    with pytest.raises(ValidationError):
        s.preview_reconnect(p,delta,anchor_node_id=anchor,target_node_id=target,**spec)
    assert p.to_dict()==before


def test_whole_member_translation_preserves_length_and_joins_only_anchor():
    s=module(); p=frame()
    r=s.preview_reconnect(p,(-200,0,-100),anchor_node_id='N-005',target_node_id='N-001',member_ids=['M-004'])
    assert r.project.members['M-004'].start_node_id=='N-001'
    assert r.project.nodes['N-006'].position_mm==(600,0,800)
    assert r.project.members['M-001'].to_dict()==p.members['M-001'].to_dict()


def project_xy(pos): return pos[0]/10,pos[1]/10


def test_node_candidates_pixel_radius_axis_lock_and_deduplication():
    s=module(); p=frame()
    candidates=s.node_candidates(p,origin_mm=(0,0,0),cursor_px=(.1,.1),project_point=project_xy,
             excluded_node_ids={'N-004'},radius_px=14,axis='Z')
    assert [c.node_id for c in candidates]==['N-001']
    assert candidates[0].kind=='NODE'
    candidates=s.node_candidates(p,origin_mm=(0,0,0),cursor_px=(20,0),project_point=project_xy,
             excluded_node_ids={'N-004'},radius_px=14,axis='Z')
    assert not candidates


def test_numeric_input_only_allows_exact_target_no_snap_rounding():
    s=module(); p=frame()
    kwargs=dict(origin_mm=(200,0,800),cursor_px=(20,0),project_point=project_xy,radius_px=14)
    assert [c.node_id for c in s.node_candidates(p,exact_position_mm=(200,0,900),**kwargs)]==['N-005']
    assert not s.node_candidates(p,exact_position_mm=(200,0,899),**kwargs)


def test_ground_candidate_is_placement_only_and_respects_locks():
    s=module()
    # Front elevation projection makes vertical gap measurable in screen pixels.
    front=lambda p:(p[0]/10,p[2]/10)
    c=s.ground_candidate((0,0,800),(10,20,30),ground_mm=0,project_point=front,radius_px=14)
    assert c and c.position_mm==(10,20,0) and c.node_id is None and c.kind=='GROUND'
    assert not s.ground_candidate((0,0,800),(10,20,30),ground_mm=0,project_point=front,radius_px=14,axis='X')
    assert s.ground_candidate((0,0,800),(0,0,30),ground_mm=0,project_point=front,radius_px=14,axis='Z')


def test_ground_does_not_infer_depth_from_top_projection_or_snap_far_away():
    s=module()
    assert not s.ground_candidate((0,0,800),(10,20,790),ground_mm=0,project_point=project_xy,radius_px=14)
    assert not s.ground_candidate((0,0,800),(10,20,790),ground_mm=0,project_point=lambda p:(p[0]/10,p[2]/10),radius_px=14)


def test_ground_custom_elevation_and_projection_failure():
    s=module()
    front=lambda p:(p[0]/10,p[2]/10)
    assert s.ground_candidate((0,0,800),(0,0,130),ground_mm=100,project_point=front,radius_px=14).position_mm==(0,0,100)
    assert not s.ground_candidate((0,0,800),(0,0,30),ground_mm=0,project_point=lambda p:None,radius_px=14)
