import math
from pathlib import Path
import pytest
from aludiy_core import ProfileCatalog, Project, Member, Node
from aludiy_core.errors import AluDIYError
from aludiy_core.associations import create_associations
from aludiy_core.geometry import derive_member_envelope, derive_member_mesh
import aludiy_core.profile_editing as pe

CAT=ProfileCatalog.from_source_directory(Path(__file__).parents[2]/'catalog'/'profiles')
P20='generic:tslot-2020@0.1'
P40='generic:tslot-2040@0.1'

def sample():
    p=Project('P-PROFILE','alpha-2026.10')
    for nid,pos in [('N-1',(0,0,0)),('N-2',(0,0,1000)),('N-3',(0,0,500)),('N-4',(700,0,500))]:
        p.add_node(Node(nid,pos))
    p.add_member(Member('M-1','N-1','N-2',P20))
    p.add_member(Member('M-2','N-3','N-4',P20,roll_deg=25))
    return create_associations(p,member_ids=['M-1','M-2']).project

def test_batch_deduplicates_preserves_topology_coordinates_angles_and_source():
    p=sample();before=p.to_dict()
    result=pe.edit_profiles(p,['M-1','M-2','M-1'],CAT,profile_type_id=P40)
    assert p.to_dict()==before
    assert result.changed_member_ids==('M-1','M-2')
    q=result.project.to_dict()
    for key in ('nodes','associations','schema_version','project_id','catalog_revision'):
        assert q[key]==before[key]
    for mid in p.members:
        assert result.project.members[mid].profile_type_id==P40
        assert result.project.members[mid].revision==p.members[mid].revision+1
        assert result.project.members[mid].roll_deg==p.members[mid].roll_deg

@pytest.mark.parametrize('kwargs',[{'profile_type_id':'missing'}, {'roll_deg':float('nan')},{'roll_deg':float('inf')}, {'roll_deg':1e15}])
def test_invalid_batch_is_atomic(kwargs):
    p=sample();before=p.to_dict()
    with pytest.raises(AluDIYError): pe.edit_profiles(p,['M-1','M-2'],CAT,**kwargs)
    assert p.to_dict()==before

@pytest.mark.parametrize('ids',[[],['M-1','M-MISSING']])
def test_bad_selection_rejected(ids):
    with pytest.raises(AluDIYError):pe.edit_profiles(sample(),ids,CAT,roll_deg=90)

def test_relative_roll_keeps_per_member_difference_and_normalizes():
    p=sample()
    q=pe.edit_profiles(p,['M-1','M-2'],CAT,roll_deg=-90,relative=True).project
    assert q.members['M-1'].roll_deg==270
    assert q.members['M-2'].roll_deg==295
    assert q.to_dict()['nodes']==p.to_dict()['nodes']

def test_absolute_roll_and_noop_do_not_increment_unnecessarily():
    p=sample()
    assert pe.edit_profiles(p,['M-1'],CAT,roll_deg=360,relative=True).changed_member_ids==()
    assert pe.edit_profiles(p,['M-1'],CAT,profile_type_id=P20).project.to_dict()==p.to_dict()
    q=pe.edit_profiles(p,['M-1','M-2'],CAT,roll_deg=45).project
    assert [m.roll_deg for m in q.members.values()]==[45,45]

def test_rectangular_roll_changes_mesh_but_not_axis_or_length():
    p=pe.edit_profiles(sample(),['M-1'],CAT,profile_type_id=P40).project
    before=derive_member_envelope(p,'M-1',CAT)
    q=pe.edit_profiles(p,['M-1'],CAT,roll_deg=90).project
    after=derive_member_envelope(q,'M-1',CAT)
    assert before.start_mm==after.start_mm and before.end_mm==after.end_mm
    assert before.length_mm==after.length_mm
    assert before.world_half_extents_mm[0]==pytest.approx(after.world_half_extents_mm[1])
    assert derive_member_mesh(p,'M-1',CAT,mode='PROFILE').vertices_mm!=derive_member_mesh(q,'M-1',CAT,mode='PROFILE').vertices_mm

@pytest.mark.parametrize('angle',[0,90,45,-90,450])
def test_world_slot_track_correct_for_oblique_member(angle):
    p=sample();p.associations.clear();p.nodes['N-2'].position_mm=(100,200,1000)
    p=pe.edit_profiles(p,['M-1'],CAT,profile_type_id=P40,roll_deg=angle).project
    e=derive_member_envelope(p,'M-1',CAT);profile=CAT.get(P40)
    rails=pe.interface_rails(p,'M-1',CAT)
    assert len(rails)==6
    for rail in rails:
        slot=profile.section.interfaces[rail.interface_id]
        expect=tuple(e.start_mm[i]+e.u_axis[i]*slot.center_uv_mm[0]+e.v_axis[i]*slot.center_uv_mm[1] for i in range(3))
        assert rail.start_mm==pytest.approx(expect)
        assert tuple(rail.end_mm[i]-rail.start_mm[i] for i in range(3))==pytest.approx(tuple(e.end_mm[i]-e.start_mm[i] for i in range(3)))
        assert math.dist(rail.normal,(0,0,0))==pytest.approx(1)

def test_closed_face_and_unknown_slot_not_invented():
    p=pe.edit_profiles(sample(),['M-1'],CAT,profile_type_id='generic:tslot-3030-3open@0.1').project
    rails=pe.interface_rails(p,'M-1',CAT)
    assert len(rails)==3
    assert all(r.face_id!='FACE_NV' for r in rails)

@pytest.mark.parametrize('text,expected',[('90',90),('45+45',90),('-90°',-90),('450deg',450),('30 度',30)])
def test_angle_input(text,expected): assert pe.parse_angle_deg(text)==expected

@pytest.mark.parametrize('text',['100mm','1m','nan','inf','__import__("os")','1/0','', '360rad'])
def test_angle_rejects_length_and_invalid_input(text):
    with pytest.raises(AluDIYError):pe.parse_angle_deg(text)
