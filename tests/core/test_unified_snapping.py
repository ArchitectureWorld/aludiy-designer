"""Shared candidates: geometry-only, precise, same semantics for draw and G."""
import math
import pytest
from aludiy_core import Project, Member, Node
from aludiy_core import snapping

def scene():
    p=Project('P-UNIFIED','alpha-2026.10')
    for nid,xyz in [('N-001',(0,0,800)),('N-002',(1000,0,800)),('N-003',(500,400,800))]:
        p.add_node(Node(nid,xyz))
    p.add_member(Member('M-001','N-001','N-002','generic:tslot-2020@0.1'))
    return p

def query(p=None,**kw):
    assert hasattr(snapping,'engineering_candidates'), 'shared candidate service missing'
    args=dict(origin_mm=(300,400,800), cursor_px=(30,0), project_point=lambda p:(p[0]/10,p[1]/10),
              ray_origin_mm=(300,0,3000),ray_direction=(0,0,-1),radius_px=5)
    args.update(kw)
    return snapping.engineering_candidates(p or scene(),**args)

def test_perpendicular_is_exact_and_preferred_to_axis():
    cs=query()
    assert cs[0].kind=='PERPENDICULAR'
    assert cs[0].position_mm==(300,0,800) and cs[0].station==.3

def test_midpoint_wins_in_its_aperture_and_deduplicates_same_position():
    cs=query(origin_mm=(500,400,800),cursor_px=(50.2,0),ray_origin_mm=(502,0,3000))
    assert cs[0].kind=='MIDPOINT'
    same=[c for c in cs if c.member_id=='M-001' and c.position_mm==(500,0,800)]
    assert len(same)==1

def test_node_priority_and_all_candidates_are_available():
    p=scene();p.add_node(Node('N-004',(500,0,800)))
    cs=query(p,origin_mm=(500,400,800),cursor_px=(50,0),ray_origin_mm=(500,0,3000))
    assert cs[0].node_id=='N-004'
    assert any(c.kind=='MIDPOINT' for c in cs)

def test_no_perpendicular_without_reference_start():
    cs=query(perpendicular=False)
    assert [c.kind for c in cs]==['AXIS']

def test_unrelated_and_excluded_geometry_never_mutated():
    p=scene();before=p.to_dict()
    cs=query(p,excluded_member_ids={'M-001'},excluded_node_ids=set(p.nodes))
    assert cs==() and p.to_dict()==before

@pytest.mark.parametrize('axis,plane,origin', [('Z',False,(300,0,900)),('Y',False,(300,400,800)),('Y',True,(300,0,900))])
def test_axis_and_plane_candidates_remain_on_allowed_locus(axis,plane,origin):
    cs=query(axis=axis,plane_lock=plane,origin_mm=origin)
    assert cs
    assert all(snapping.allowed_position(origin,c.position_mm,axis,plane) for c in cs)

def test_axis_off_geometry_produces_no_fake_snap():
    assert query(axis='Z',origin_mm=(300,80,900))==()

def test_numeric_input_is_not_rounded_to_nearby_point():
    exact=(299.0,0.0,800.0)
    cs=query(exact_position_mm=exact, cursor_px=(29.9,0))
    assert all(math.dist(c.position_mm,exact)<1e-4 for c in cs)
    assert not any(c.kind=='PERPENDICULAR' for c in cs)

def test_perpendicular_outside_segment_is_not_clamped_and_called_a_foot():
    cs=query(origin_mm=(-100,400,800),cursor_px=(2,0),ray_origin_mm=(20,0,3000))
    assert not any(c.kind=='PERPENDICULAR' for c in cs)

def test_coincident_different_nodes_remain_separate_targets():
    p=scene();p.add_node(Node('N-004',(0,0,800)))
    cs=query(p,cursor_px=(0,0),ray_origin_mm=(0,0,3000))
    assert [c.node_id for c in cs if c.kind=='NODE']==['N-001','N-004']

def test_parallel_ray_does_not_invent_a_nearest_axis_station():
    cs=query(cursor_px=(30,0),ray_direction=(1,0,0),perpendicular=False)
    assert not any(c.kind=='AXIS' for c in cs)

def test_snap_description_shows_real_member_station_not_connection():
    assert hasattr(snapping,'describe_candidate')
    text=snapping.describe_candidate(query()[0],scene())
    assert '垂足' in text and 'M-001' in text and '300' in text and '仅定位' in text

def test_float64_drawing_length_is_not_float32_quantized():
    assert hasattr(snapping,'resolve_draw_endpoint')
    start=(2298.712345678,895.23456789,276.62345678)
    end=snapping.resolve_draw_endpoint(start,(start[0],start[1],start[2]+500),'500',axis='Z')
    assert end==(start[0],start[1],start[2]+500)
    assert abs(math.dist(start,end)-500)<1e-10

def test_typed_length_and_polar_are_resolved_and_strict():
    assert hasattr(snapping,'resolve_draw_endpoint')
    resolve=snapping.resolve_draw_endpoint
    assert resolve((1,2,3),(1,2,-97),'0.1m',axis='Z')==(1,2,-97)
    end=resolve((0,0,500),(10,0,500),'@200<90',work_plane='XZ')
    assert math.dist(end,(0,0,700))<1e-9
    with pytest.raises(Exception): resolve((0,0,0),(100,0,0),'1+')

@pytest.mark.parametrize('direction',[(0,0,0),(0,float('nan'),1),(float('inf'),0,1)])
def test_invalid_ray_is_a_domain_error_not_division_or_nan(direction):
    from aludiy_core.errors import ValidationError
    with pytest.raises(ValidationError):query(ray_direction=direction)
