from pathlib import Path
import importlib,math,json,csv
import pytest
from aludiy_core import Project,Node,Member,ProfileCatalog
from aludiy_core.geometry import derive_member_mesh,member_length_mm
from aludiy_core.movement import preview_move
from aludiy_core.profile_editing import edit_profiles
from aludiy_core.errors import ValidationError
from aludiy_core.cutlist import write_cutlist_csv
CAT=ProfileCatalog.from_source_directory(Path(__file__).parents[2]/'catalog/profiles')
P20='generic:tslot-2020@0.1';P40='generic:tslot-2040@0.1'

def api():
 assert importlib.util.find_spec('aludiy_core.joints') is not None,'joint processing API missing'
 return importlib.import_module('aludiy_core.joints')

def frame(z=500,x=0,reverse=False,branch_profile=P20):
 p=Project('P-JOINT','alpha-2026.10')
 for n,pt in [('A',(0,0,0)),('B',(0,0,1000)),('C',(x,0,z)),('D',(500,0,z))]:p.add_node(Node(n,pt))
 p.add_member(Member('H','A','B',P40))
 p.add_member(Member('F','D' if reverse else 'C','C' if reverse else 'D',branch_profile))
 return p

def joint(p=None,gap=0):return api().set_butt_joint(p or frame(),CAT,host_member_id='H',branch_member_id='F',gap_mm=gap).project

def test_T_cutback_only_changes_body_not_design_or_associations():
 p=frame();before=p.to_dict();q=joint(p);s=api().solve_cutbacks(q,CAT,strict=True)
 assert s.lengths['F'].design_length_mm==500 and s.lengths['F'].cut_length_mm==480
 assert s.lengths['F'].start_setback_mm==20 and s.lengths['H'].cut_length_mm==1000
 assert s.kinds=={'J-001':'T'} and not s.issues
 assert q.to_dict()['nodes']==before['nodes'] and q.associations==p.associations and p.to_dict()==before
 assert q.schema_version=='0.4.0'

@pytest.mark.parametrize('z,end',[(0,'START'),(1000,'END')])
@pytest.mark.parametrize('reverse',[False,True])
def test_L_extends_designated_host_and_trims_correct_branch_end(z,end,reverse):
 q=joint(frame(z=z,reverse=reverse));s=api().solve_cutbacks(q,CAT,strict=True)
 assert s.kinds=={'J-001':'L'}
 assert s.lengths['H'].cut_length_mm==1010 and s.lengths['F'].cut_length_mm==480
 assert getattr(s.lengths['H'],'start_setback_mm' if end=='START' else 'end_setback_mm')==-10
 assert getattr(s.lengths['F'],'end_setback_mm' if reverse else 'start_setback_mm')==20

def test_L_support_uses_branch_section_not_host_size():
 p=frame(z=1000,branch_profile=P40);p.members['F'].roll_deg=90
 s=api().solve_cutbacks(joint(p),CAT,strict=True)
 assert s.lengths['H'].cut_length_mm==1020

@pytest.mark.parametrize('mode',['BOX','PROFILE'])
def test_generated_mesh_uses_cut_end_and_axis_envelope_does_not(mode):
 q=joint();mesh=derive_member_mesh(q,'F',CAT,mode=mode)
 assert min(v[0] for v in mesh.vertices_mm)==pytest.approx(20)
 assert max(v[0] for v in mesh.vertices_mm)==pytest.approx(500)
 assert q.nodes['C'].position_mm==(0,0,500) and member_length_mm(q,'F')==500

def test_gap_updates_same_rule_and_noop_is_idempotent():
 q=joint(gap=2);s=api().solve_cutbacks(q,CAT,strict=True);assert s.lengths['F'].cut_length_mm==478
 r=api().set_butt_joint(q,CAT,host_member_id='H',branch_member_id='F',gap_mm=3)
 assert len(r.project.joints)==1 and r.changed_count==1
 assert api().set_butt_joint(r.project,CAT,host_member_id='H',branch_member_id='F',gap_mm=3).changed_count==0

@pytest.mark.parametrize('gap',[-1,float('nan'),float('inf'),500])
def test_bad_gap_or_nonpositive_cut_length_rejected_atomically(gap):
 p=frame();before=p.to_dict()
 with pytest.raises(ValidationError):joint(p,gap)
 assert p.to_dict()==before

@pytest.mark.parametrize('z,x',[(500,40),(-30,0),(1030,0),(5,0)])
def test_off_host_or_unsupported_near_end_rejected(z,x):
 with pytest.raises(ValidationError):joint(frame(z=z,x=x))

def test_parallel_and_oblique_do_not_fake_a_straight_cut():
 for pt in [(0,0,800),(500,0,600)]:
  p=frame();p.nodes['D'].position_mm=pt
  with pytest.raises(ValidationError):joint(p)
 p=frame();p.members['H'].roll_deg=45
 with pytest.raises(ValidationError):joint(p)

def test_host_roll_recalculates_face_distance():
 q=joint();q=edit_profiles(q,['H'],CAT,roll_deg=90).project
 assert api().solve_cutbacks(q,CAT,strict=True).lengths['F'].cut_length_mm==490

def test_slot_position_not_trimmed_twice_and_schema_not_downgraded():
 from aludiy_core.associations import create_slot_associations,create_associations
 # Catalog U=40,V=20: +U slot on vertical host has x=20,y=0.
 p=frame(x=20)
 p=create_slot_associations(p,CAT,host_member_id='H',interface_id='FACE_PU.S0',member_ids=['F']).project
 q=joint(p,gap=2)
 assert api().solve_cutbacks(q,CAT,strict=True).lengths['F'].cut_length_mm==478
 assert q.schema_version=='0.4.0'
 r=create_slot_associations(q,CAT,host_member_id='H',interface_id='FACE_PU.S0',member_ids=['F'])
 assert r.project.schema_version=='0.4.0'
 assert create_associations(q,member_ids=['H','F'],catalog=CAT).project.schema_version=='0.4.0'

def test_unlinked_endpoint_can_move_even_when_processing_becomes_invalid():
 from aludiy_core.associations import create_associations,remove_associations
 p=create_associations(frame(),member_ids=['H','F']).project;q=joint(p)
 q=remove_associations(q,member_ids=['F']).project
 moved=preview_move(q,(40,0,20),endpoint=('F','START')).project
 s=api().solve_cutbacks(moved,CAT)
 assert s.issues and s.lengths['F'].cut_length_mm is None
 # Fallback raw design body is explicit pending state, not a movement constraint.
 mesh=derive_member_mesh(moved,'F',CAT,mode='BOX');assert mesh.vertices_mm
 with pytest.raises(ValidationError):api().solve_cutbacks(moved,CAT,strict=True)

def test_roundtrip_and_deleting_host_clean_rules():
 q=joint();assert Project.from_dict(q.to_dict()).to_dict()==q.to_dict()
 q.remove_members(['H']);assert not q.joints and 'F' in q.members

def test_remove_rule_restores_uncut_body_and_preserves_positions():
 q=joint();before=q.to_dict()['nodes'];r=api().remove_joints(q,member_ids=['F'])
 assert r.changed_count==1 and not r.project.joints and r.project.to_dict()['nodes']==before
 assert min(v[0] for v in derive_member_mesh(r.project,'F',CAT,mode='BOX').vertices_mm)==0

def test_two_ends_trimmed_only_once():
 p=frame();p.add_node(Node('E',(500,0,0)));p.add_node(Node('G',(500,0,1000)))
 p.add_member(Member('H2','E','G',P40))
 q=joint(p);q=api().set_butt_joint(q,CAT,host_member_id='H2',branch_member_id='F').project
 s=api().solve_cutbacks(q,CAT,strict=True)
 assert len(q.joints)==2 and s.lengths['F'].cut_length_mm==460

def test_cutlist_with_processing_explicit_design_and_cut_lengths(tmp_path):
 q=joint();path=tmp_path/'cut.csv';write_cutlist_csv(q,path,CAT)
 with path.open(encoding='utf-8-sig') as f:rows={r['member_id']:r for r in csv.DictReader(f)}
 assert rows['F']['system_length_mm']=='500.000' and rows['F']['cut_length_mm']=='480.000'
 assert rows['F']['start_setback_mm']=='20.000'
 assert 'not_manufacturing_validated' in rows['F']['status']

def test_invalid_processing_never_overwrites_cutlist(tmp_path):
 q=joint();q.nodes['D'].position_mm=(500,0,700)
 path=tmp_path/'keep.csv';path.write_text('keep')
 with pytest.raises(ValidationError):write_cutlist_csv(q,path,CAT)
 assert path.read_text()=='keep'
 with pytest.raises(ValidationError):write_cutlist_csv(joint(),path)

@pytest.mark.parametrize('bad', ['missing-host','missing-branch','same-member','bad-end','old-schema'])
def test_malformed_import_rejected(bad):
 d=joint().to_dict();r=d['joints'][0]
 if bad=='missing-host':r['host_member_id']='missing'
 if bad=='missing-branch':r['branch_member_id']='missing'
 if bad=='same-member':r['branch_member_id']=r['host_member_id']
 if bad=='bad-end':r['branch_end']='CENTER'
 if bad=='old-schema':d['schema_version']='0.3.0'
 with pytest.raises(ValidationError):Project.from_dict(d)
