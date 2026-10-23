"""Mixed snap families and exact-pair batch relations: approved v0.1.19."""
from pathlib import Path
from dataclasses import replace
import pytest
from aludiy_core import Project, Member, Node, ProfileCatalog
from aludiy_core import snapping as sn, associations as a
from aludiy_core.errors import AluDIYError
from aludiy_core.profile_editing import interface_rails
from aludiy_core.movement import preview_move
CAT=ProfileCatalog.from_source_directory(Path(__file__).parents[2]/'catalog/profiles')
P40='generic:tslot-2040@0.1'; P20='generic:tslot-2020@0.1'; SID='FACE_PU.S0'

def model():
    p=Project('P-MULTI','alpha-2026.10')
    for i,x in enumerate((0,1000)):
        p.add_node(Node(f'A{i}',(x,0,0)));p.add_node(Node(f'B{i}',(x,0,1000)))
        p.add_member(Member(f'H{i}',f'A{i}',f'B{i}',P40))
        rail=next(r for r in interface_rails(p,f'H{i}',CAT) if r.interface_id==SID)
        pt=tuple((aa+bb)/2 for aa,bb in zip(rail.start_mm,rail.end_mm))
        p.add_node(Node(f'F{i}',pt));p.add_node(Node(f'E{i}',(x+400,0,500)))
        p.add_member(Member(f'M{i}',f'F{i}',f'E{i}',P20))
    return p

def candidates(p,point,**kw):
    opts=dict(origin_mm=(300,0,200),cursor_px=(point[0],point[2]),
        project_point=lambda v:(v[0],v[2]),ray_origin_mm=(point[0],-1000,point[2]),
        ray_direction=(0,1,0),catalog=CAT,radius_px=8)
    opts.update(kw)
    return sn.engineering_candidates(p,**opts)

def many_api():
    assert hasattr(a,'create_slot_associations_many'),'multi-slot association API missing'
    return a

def test_legacy_pin_default_does_not_hide_distant_ordinary_endpoint():
    p=model();r=candidates(p,(1400,0,500),slot_target=('H0',SID))
    assert any(c.kind=='NODE' and c.node_id=='E1' for c in r)

def test_two_rails_and_ordinary_candidates_coexist_and_do_not_mutate():
    p=model();before=p.to_dict()
    for host,x in [('H0',20),('H1',1020)]:
        result=candidates(p,(x,0,500),slot_targets=[('H0',SID),('H1',SID)])
        assert any(c.kind=='SLOT' and c.member_id==host for c in result)
        assert any(c.kind=='NODE' for c in result)
    assert p.to_dict()==before

def test_explicit_restricted_mode_excludes_ordinary_only_when_targets_exist():
    p=model()
    assert not candidates(p,(1400,0,500),slot_targets=[('H0',SID)],slot_only=True)
    assert any(c.kind=='NODE' for c in candidates(p,(1400,0,500),slot_targets=[],slot_only=True))

@pytest.mark.parametrize('point,kind',[((1000,0,500),'MIDPOINT'),((1000,0,250),'AXIS'),((1000,0,200),'PERPENDICULAR'),((1000,0,0),'NODE')])
def test_normal_families_remain_reachable_with_distant_pin(point,kind):
    assert any(c.kind==kind for c in candidates(model(),point,slot_targets=[('H0',SID)]))

def test_overlapping_different_rails_are_not_deduplicated_or_randomly_chosen():
    p=model()
    for n in ['A1','B1']:p.nodes[n].position_mm=p.nodes[n.replace('1','0')].position_mm
    r=candidates(p,(20,0,500),slot_targets=[('H1',SID),('H0',SID),('H1',SID)],slot_only=True)
    assert {c.member_id for c in r}=={'H0','H1'}
    assert len([c for c in r if c.point_kind=='MIDPOINT'])==2
    assert [c.key for c in r]==[c.key for c in candidates(p,(20,0,500),slot_targets=[('H0',SID),('H1',SID)],slot_only=True)]

def test_numeric_axis_and_moving_member_exclusions_apply_to_every_rail():
    p=model();targets=[('H0',SID),('H1',SID)]
    assert not candidates(p,(20,0,500),slot_targets=targets,slot_only=True,excluded_member_ids=['H0'])
    assert not candidates(p,(20,0,500),slot_targets=targets,slot_only=True,origin_mm=(0,0,500),axis='Z')
    assert not candidates(p,(20,0,500),slot_targets=targets,slot_only=True,exact_position_mm=(21,0,500))
    assert any(c.kind=='SLOT' for c in candidates(p,(20,0,500),slot_targets=targets,slot_only=True,exact_position_mm=(20,0,500)))

def test_ground_fallback_and_nodes_only_preserved():
    p=model();r=candidates(p,(5000,0,5),slot_targets=[('H0',SID)],ground_mm=0,raw_position_mm=(5000,0,5))
    assert [c.kind for c in r]==['GROUND']
    r=candidates(p,(1400,0,500),slot_targets=[('H0',SID)],slot_only=True,nodes_only=True)
    assert any(c.node_id=='E1' for c in r)

def test_batch_connect_exact_pairs_internal_identity_and_idempotency():
    p=model();before=p.to_dict();api=many_api()
    targets=[('H0',SID),('H1',SID)]
    out=api.create_slot_associations_many(p,CAT,slot_targets=targets,member_ids=['M0','M1'])
    assert out.changed_count==2 and p.to_dict()==before
    assert out.project.to_dict()['nodes']==before['nodes']
    assert {(r.host_member_id,r.follower_node_id) for r in out.project.associations.values()}=={('H0','F0'),('H1','F1')}
    assert api.create_slot_associations_many(out.project,CAT,slot_targets=targets,node_ids=['F0','F1']).changed_count==0

def test_batch_connect_not_cartesian_host_interface_product():
    p=model();api=many_api()
    out=api.create_slot_associations_many(p,CAT,slot_targets=[('H0',SID),('H1','FACE_NU.S0')],member_ids=['M0','M1'])
    assert out.changed_count==1
    assert next(iter(out.project.associations.values())).follower_node_id=='F0'

def test_one_ambiguous_endpoint_rejects_entire_batch():
    p=model();api=many_api()
    p.add_node(Node('A2',p.nodes['A0'].position_mm));p.add_node(Node('B2',p.nodes['B0'].position_mm))
    p.add_member(Member('H2','A2','B2',P40));before=p.to_dict()
    with pytest.raises(AluDIYError,match='多个槽轨'):
        api.create_slot_associations_many(p,CAT,slot_targets=[('H0',SID),('H1',SID),('H2',SID)],node_ids=['F1','F0'])
    assert p.to_dict()==before and not p.associations

@pytest.mark.parametrize('target',[('gone',SID),('H1','gone')])
def test_invalid_target_rejects_atomic_create(target):
    p=model();api=many_api();before=p.to_dict()
    with pytest.raises(AluDIYError):api.create_slot_associations_many(p,CAT,slot_targets=[('H0',SID),target],node_ids=['F0'])
    assert p.to_dict()==before

def test_batch_remove_exact_scopes_and_immediate_move():
    api=many_api();p=model()
    q=api.create_slot_associations_many(p,CAT,slot_targets=[('H0',SID),('H1',SID)],node_ids=['F0','F1']).project
    before=q.to_dict();r=api.remove_slot_associations_many(q,slot_targets=[('H0',SID)])
    assert r.changed_count==1 and q.to_dict()==before
    assert r.project.to_dict()['nodes']==before['nodes']
    assert {a.host_member_id for a in r.project.associations.values()}=={'H1'}
    preview_move(r.project,(100,0,0),node_ids=['F0'])
    with pytest.raises(AluDIYError):preview_move(r.project,(100,0,0),node_ids=['F1'])
    assert api.remove_slot_associations_many(q,slot_targets=[('H0',SID),('H1',SID),('H0',SID)]).changed_count==2

def test_batch_schema_preserved_and_noop_remove_idempotent():
    api=many_api();p=model();p.schema_version='0.4.0'
    q=api.create_slot_associations_many(p,CAT,slot_targets=[('H0',SID)],node_ids=['F0']).project
    assert q.schema_version=='0.4.0'
    assert api.remove_slot_associations_many(q,slot_targets=[('H1',SID)]).project.to_dict()==q.to_dict()
