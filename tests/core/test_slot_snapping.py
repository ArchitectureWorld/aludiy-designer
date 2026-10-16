from pathlib import Path
import math
import pytest
from aludiy_core import Project, Node, Member, ProfileCatalog
from aludiy_core.profile_editing import interface_rails, edit_profiles
from aludiy_core import snapping as sn
from aludiy_core.errors import AluDIYError
CAT=ProfileCatalog.from_source_directory(Path(__file__).parents[2]/'catalog'/'profiles')

def api():
    assert hasattr(sn,'slot_candidates'), 'slot candidate pipeline missing'
    return sn

def setup():
    p=Project('P-SNAP-SLOT','alpha-2026.10')
    p.add_node(Node('N-1',(0,0,0)));p.add_node(Node('N-2',(0,0,1000)))
    p.add_member(Member('M-1','N-1','N-2','generic:tslot-2040@0.1'))
    return p

def project_point(p): return (p[0]*10+p[1]*2,p[2])

def options(p=None,sid='FACE_PV.S1',t=.31,**kw):
    p=p or setup();rail=next(r for r in interface_rails(p,'M-1',CAT) if r.interface_id==sid)
    target=tuple(rail.start_mm[i]+t*(rail.end_mm[i]-rail.start_mm[i]) for i in range(3))
    defaults=dict(origin_mm=(500,500,300),cursor_px=project_point(target),project_point=project_point,
                  ray_origin_mm=(target[0]+200,target[1]-1000,target[2]),ray_direction=(-.2,1,0),
                  radius_px=12,perpendicular=False)
    defaults.update(kw)
    result=api().engineering_candidates(p,catalog=CAT,slot_target=('M-1',sid),**defaults)
    return result,target

def test_slot_target_exact_world_position_and_identity():
    result,target=options()
    assert result and all(c.kind=='SLOT' and c.interface_id=='FACE_PV.S1' for c in result)
    assert result[0].position_mm==pytest.approx(target,abs=1e-10)
    assert result[0].member_id=='M-1' and result[0].station==pytest.approx(.31)
    assert 'FACE_PV.S1' in result[0].key
    label=api().describe_candidate(result[0],setup())
    assert 'FACE_PV.S1' in label and '310.0' in label and '仅定位' in label

def test_two_lanes_never_deduplicated_as_one_interface():
    a,_=options(sid='FACE_PV.S0');b,_=options(sid='FACE_PV.S1')
    assert a[0].key!=b[0].key and a[0].position_mm!=b[0].position_mm

@pytest.mark.parametrize('t',[0,.5,1])
def test_finite_rail_semantic_points(t):
    result,target=options(t=t)
    assert result and result[0].station==pytest.approx(t)
    assert result[0].point_kind in {'START','MIDPOINT','END'}

def test_exact_numeric_distance_wins_over_magnet():
    _,target=options(); bad=(target[0]+.001,target[1],target[2])
    result,_=options(exact_position_mm=bad)
    assert not result
    result,_=options(exact_position_mm=target)
    assert result[0].position_mm==pytest.approx(target,abs=1e-10)

def test_axis_and_plane_locks_cannot_be_overridden():
    _,target=options()
    r,_=options(axis='Z',origin_mm=(target[0],target[1],0))
    assert r
    r,_=options(axis='Z',origin_mm=(target[0]+10,target[1],0))
    assert not r
    r,_=options(axis='Z',plane_lock=True,origin_mm=(0,0,310))
    assert r and r[0].position_mm[2]==pytest.approx(310)

def test_perpendicular_and_target_rotation():
    p=edit_profiles(setup(),['M-1'],CAT,roll_deg=90).project
    result,target=options(p,perpendicular=True,origin_mm=(100,200,310))
    assert result[0].point_kind=='PERPENDICULAR'
    assert result[0].position_mm==pytest.approx(target,abs=1e-10)

def test_target_host_in_selected_group_is_excluded():
    result,_=options(excluded_member_ids=['M-1']);assert not result

def test_invalid_target_or_closed_face_rejected():
    p=setup();api()
    for target in [('M-1','missing'),('missing','FACE_PV.S0')]:
        with pytest.raises(AluDIYError):sn.slot_candidates(p,CAT,target,origin_mm=(0,0,0),cursor_px=(0,0),project_point=project_point,ray_origin_mm=(1,1,1),ray_direction=(0,1,0))

def test_parallel_view_only_exposes_real_semantic_points():
    r,_=options(ray_origin_mm=(100,100,2000),ray_direction=(0,0,-1))
    assert not r

def test_bad_ray_fails_closed():
    with pytest.raises(AluDIYError):options(ray_direction=(0,0,0))

def test_unprojectable_or_distant_slot_does_not_snap():
    r,_=options(project_point=lambda p:None);assert not r
    r,_=options(cursor_px=(-10000,-10000));assert not r

def test_bare_axis_mode_still_works_when_no_slot_target():
    api();p=setup()
    r=sn.engineering_candidates(p,origin_mm=(100,0,200),cursor_px=(0,310),project_point=project_point,
        ray_origin_mm=(0,-1000,310),ray_direction=(0,1,0),catalog=CAT)
    assert r and all(c.kind!='SLOT' for c in r)
