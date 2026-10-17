from pathlib import Path
import pytest
from aludiy_core import Project,Node,Member,ProfileCatalog
from aludiy_core import associations as a
from aludiy_core.profile_editing import interface_rails
from aludiy_core.movement import preview_move
from aludiy_core.errors import ValidationError
CAT=ProfileCatalog.from_source_directory(Path(__file__).parents[2]/'catalog/profiles')

def linked():
 p=Project('UNLINK','alpha-2026.10')
 p.add_node(Node('A',(0,0,0)));p.add_node(Node('B',(0,0,1000)))
 p.add_member(Member('H','A','B','generic:tslot-2040@0.1'))
 rails=interface_rails(p,'H',CAT)
 for i,rail in enumerate(rails[:2]):
  pt=tuple((x+y)*.5 for x,y in zip(rail.start_mm,rail.end_mm))
  p.add_node(Node(f'C{i}',pt));p.add_node(Node(f'D{i}',(500,100*i,500)))
  p.add_member(Member(f'F{i}',f'C{i}',f'D{i}','generic:tslot-2020@0.1'))
  p=a.create_slot_associations(p,CAT,host_member_id='H',interface_id=rail.interface_id,member_ids=[f'F{i}']).project
 return p,rails

def api():
 assert hasattr(a,'remove_slot_associations'),'exact slot unlink missing'
 return a.remove_slot_associations

def test_remove_exact_slot_preserves_other_slot_and_positions():
 p,rails=linked();before=p.to_dict()
 r=api()(p,host_member_id='H',interface_id=rails[0].interface_id)
 assert r.changed_count==1 and len(r.project.associations)==1
 assert p.to_dict()==before and r.project.to_dict()['nodes']==before['nodes']
 assert r.project.to_dict()['members']==before['members']
 assert next(iter(r.project.associations.values())).slot_reference.interface_id==rails[1].interface_id

def test_removed_follower_moves_immediately_and_after_roundtrip():
 p,rails=linked();q=api()(p,host_member_id='H',interface_id=rails[0].interface_id).project
 for project in (q,Project.from_dict(q.to_dict())):
  moved=preview_move(project,(30,0,0),endpoint=('F0','START')).project
  assert moved.nodes['C0'].position_mm[0]==pytest.approx(q.nodes['C0'].position_mm[0]+30)
  with pytest.raises(ValidationError):preview_move(project,(30,0,0),endpoint=('F1','START'))

def test_repeated_unlink_no_change_and_unknown_host_rejected():
 p,rails=linked();f=api();q=f(p,host_member_id='H',interface_id=rails[0].interface_id).project
 assert f(q,host_member_id='H',interface_id=rails[0].interface_id).changed_count==0
 with pytest.raises(ValidationError):f(q,host_member_id='missing',interface_id=rails[0].interface_id)

def test_all_followers_of_same_slot_removed_not_just_active():
 p,rails=linked();pt=p.nodes['C0'].position_mm
 p.add_node(Node('E',pt));p.add_node(Node('F',(500,500,500)));p.add_member(Member('F2','E','F','generic:tslot-2020@0.1'))
 p=a.create_slot_associations(p,CAT,host_member_id='H',interface_id=rails[0].interface_id,member_ids=['F2']).project
 result=api()(p,host_member_id='H',interface_id=rails[0].interface_id)
 assert result.changed_count==2
 preview_move(result.project,(10,0,0),node_ids=['C0','E'])
