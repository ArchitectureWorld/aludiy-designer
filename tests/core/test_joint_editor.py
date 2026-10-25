import importlib.util
from pathlib import Path
import math
import pytest
from aludiy_core import Project, Node, Member, ProfileCatalog
from aludiy_core.errors import ValidationError
from aludiy_core.joints import ButtJoint, set_butt_joint, solve_cutbacks
from aludiy_core.geometry import derive_member_mesh
CAT = ProfileCatalog.from_source_directory(Path(__file__).parents[2]/'catalog/profiles')
P20='generic:tslot-2020@0.1'; P30='generic:tslot-3030@0.1'; P40='generic:tslot-2040@0.1'

def api():
    assert importlib.util.find_spec('aludiy_core.joint_editor'), 'joint option API missing'
    return importlib.import_module('aludiy_core.joint_editor')

def corner(reverse=False, profiles=None, sign=1):
    p=Project('P-EDITOR', 'alpha-2026.10')
    common=(0.,0.,500.)
    for i,(mid,far) in enumerate([('A',(500.*sign,0.,500.)),('B',(0.,500.*sign,500.)),('C',(0.,0.,0.))]):
        a,b=f'N{i}a',f'N{i}b'
        p.add_node(Node(a, common));p.add_node(Node(b,far))
        p.add_member(Member(mid,b if reverse else a,a if reverse else b,(profiles or {}).get(mid,P20)))
    return p

def T():
    p=corner();p.remove_members(['B']);p.nodes['N0a'].position_mm=(0,0,250);p.nodes['N0b'].position_mm=(500,0,250)
    return p

@pytest.mark.parametrize('reverse',[False,True])
@pytest.mark.parametrize('sign',[1,-1])
def test_three_options_are_atomic_and_leave_original_axes_relations_untouched(reverse,sign):
    p=corner(reverse,sign=sign);before=p.to_dict()
    choices=api().joint_choices(p,CAT,member_ids=['C','B','A'],gap_mm=2)
    assert [c.host_member_id for c in choices]==['A','B','C']
    for c in choices:
        assert c.valid,c.message
        assert c.kind=='CORNER3' and len(c.project.joints)==2
        assert c.solution.lengths[c.host_member_id].cut_length_mm==pytest.approx(510)
        for mid in set(p.members)-{c.host_member_id}:assert c.solution.lengths[mid].cut_length_mm==pytest.approx(488)
        assert c.project.to_dict()['nodes']==before['nodes'] and c.project.associations==p.associations
    assert p.to_dict()==before

@pytest.mark.parametrize('host',['A','C'])
def test_L_switch_removes_previous_local_recipe_without_repeated_deductions(host):
    p=corner();p.remove_members(['B'])
    a=api().apply_joint_choice(p,CAT,member_ids=['A','C'],host_member_id=host,gap_mm=1)
    other=next(x for x in p.members if x!=host)
    b=api().apply_joint_choice(a.project,CAT,member_ids=['A','C'],host_member_id=other,gap_mm=1)
    assert len(b.project.joints)==1 and next(iter(b.project.joints.values())).host_member_id==other
    assert b.project.nodes==p.nodes
    assert api().apply_joint_choice(b.project,CAT,member_ids=['C','A'],host_member_id=other,gap_mm=1).changed_count==0

def test_T_has_one_enabled_choice_with_explanation_for_other():
    cs=api().joint_choices(T(),CAT,member_ids=['A','C'])
    assert [c.host_member_id for c in cs if c.valid]==['C']
    assert [c.kind for c in cs if c.valid]==['T']
    assert all(c.message for c in cs if not c.valid)

def test_gap_updates_same_recipe_ids_and_never_moves_nodes():
    p=corner();r=api().apply_joint_choice(p,CAT,member_ids=p.members,host_member_id='C',gap_mm=0)
    q=api().apply_joint_choice(r.project,CAT,member_ids=p.members,host_member_id='C',gap_mm=3).project
    assert q.joints.keys()==r.project.joints.keys() and len(q.joints)==2
    assert q.nodes==p.nodes and solve_cutbacks(q,CAT,strict=True).lengths['A'].cut_length_mm==487

@pytest.mark.parametrize('members',[[],['A'],['A','B','C','D'],['A','missing']])
def test_invalid_selection_rejected_without_mutation(members):
    p=corner();before=p.to_dict()
    with pytest.raises(ValidationError):api().joint_choices(p,CAT,member_ids=members)
    assert p.to_dict()==before

@pytest.mark.parametrize('gap',[-1,float('nan'),float('inf')])
def test_invalid_gap_rejected(gap):
    with pytest.raises(ValidationError):api().joint_choices(corner(),CAT,member_ids=['A','B','C'],gap_mm=gap)

def test_too_large_gap_disables_all_options():
    choices=api().joint_choices(corner(),CAT,member_ids=['A','B','C'],gap_mm=1000)
    assert all(not c.valid and c.message for c in choices)

def test_unequal_sections_cannot_hide_branch_branch_intersection():
    p=corner(profiles={'A':P30,'B':P30})
    cs=api().joint_choices(p,CAT,member_ids=p.members)
    assert not next(c for c in cs if c.host_member_id=='C').valid
    assert '相交' in next(c for c in cs if c.host_member_id=='C').message
    assert any(c.valid for c in cs)

def test_existing_pair_rules_now_flag_connected_envelope_collisions():
    p=corner(profiles={'A':P30,'B':P30});p.schema_version='0.4.0'
    p.joints={'J1':ButtJoint('J1','C','A','START'), 'J2':ButtJoint('J2','C','B','START')}
    result=solve_cutbacks(p,CAT)
    assert result.issues,'branch overlap must not produce an apparently valid cut-list'
    assert any('相交' in x for x in result.issues)
    with pytest.raises(ValidationError):solve_cutbacks(p,CAT,strict=True)

def test_unconnected_overlapping_model_is_not_falsely_claimed_as_checked():
    p=corner();r=api().apply_joint_choice(p,CAT,member_ids=['A','C'],host_member_id='C')
    assert not solve_cutbacks(r.project,CAT,strict=True).issues  # B is not in the processing component

def test_three_way_requires_one_common_orthogonal_corner():
    p=corner();p.nodes['N1a'].position_mm=(0,0,250);p.nodes['N1b'].position_mm=(0,500,250)
    with pytest.raises(ValidationError,match='同一|端点'):api().joint_choices(p,CAT,member_ids=p.members)
    p=corner();p.nodes['N1b'].position_mm=(200,500,500)
    with pytest.raises(ValidationError,match='正交|垂直'):api().joint_choices(p,CAT,member_ids=p.members)

def test_unselected_far_end_rule_survives_host_switch():
    p=corner();p.remove_members(['B']);p.add_node(Node('E',(500,0,0)));p.add_node(Node('F',(500,0,1000)))
    p.add_member(Member('D','E','F',P20))
    p=set_butt_joint(p,CAT,host_member_id='D',branch_member_id='A',branch_end='END').project
    kept=next(iter(p.joints.values()))
    for h in ('C','A'):
        q=api().apply_joint_choice(p,CAT,member_ids=['A','C'],host_member_id=h).project
        assert q.joints[kept.id]==kept

def test_other_host_same_endpoint_is_not_silently_overwritten():
    p=corner();p.add_node(Node('E',(0,0,0)));p.add_node(Node('F',(0,0,1000)));p.add_member(Member('D','E','F',P20))
    p=set_butt_joint(p,CAT,host_member_id='D',branch_member_id='A',branch_end='START').project
    before=p.to_dict()
    cs=api().joint_choices(p,CAT,member_ids=['A','C'])
    assert not next(c for c in cs if c.host_member_id=='C').valid
    assert p.to_dict()==before

def test_scope_removal_keeps_external_rules_and_associations():
    from aludiy_core.associations import create_associations
    p=create_associations(corner(),member_ids=['A','B','C'],catalog=CAT).project
    r=api().apply_joint_choice(p,CAT,member_ids=p.members,host_member_id='B')
    assert r.project.associations==p.associations
    d=r.project.to_dict();q=Project.from_dict(d)
    assert q.to_dict()==d
    assert all(c.valid for c in api().joint_choices(q,CAT,member_ids=q.members))

def test_world_bounds_show_extension_not_a_false_outer_size_lock():
    p=corner();p.remove_members(['B']);cs=api().joint_choices(p,CAT,member_ids=p.members)
    c=next(c for c in cs if c.host_member_id=='C')
    assert len(c.before_bounds)==2 and len(c.after_bounds)==2
    # All outer geometry in this centered equal-section L already occupied the top
    # by branch thickness. Bounding dimensions can stay equal despite host extension.
    for bounds,q in [(c.before_bounds,p),(c.after_bounds,c.project)]:
        vs=[v for mid in p.members for v in derive_member_mesh(q,mid,CAT,mode='BOX').vertices_mm]
        assert bounds[0]==pytest.approx(tuple(min(v[i] for v in vs) for i in range(3)))
        assert bounds[1]==pytest.approx(tuple(max(v[i] for v in vs) for i in range(3)))

def test_arbitrary_global_orientation_and_roll_are_evaluated():
    p=corner()
    for n in p.nodes.values():
        x,y,z=n.position_mm;n.position_mm=(-y,x,z)
    for m in p.members.values():m.roll_deg=90
    assert all(c.valid for c in api().joint_choices(p,CAT,member_ids=p.members))

def test_input_order_is_not_host_assignment():
    p=corner()
    a=api().joint_choices(p,CAT,member_ids=['A','B','C'])
    b=api().joint_choices(p,CAT,member_ids=['C','A','B'])
    assert [(c.host_member_id,c.project.to_dict()) for c in a]==[(c.host_member_id,c.project.to_dict()) for c in b]


def desk_frame():
    p=Project('P-DESK','alpha-2026.10')
    def rod(mid,a,b):
        p.add_node(Node(mid+'a',a));p.add_node(Node(mid+'b',b))
        p.add_member(Member(mid,mid+'a',mid+'b',P20))
    for mid,(x,y) in zip(('L1','L2','L3','L4'),((0,0),(1200,0),(1200,600),(0,600))):
        rod(mid,(x,y,0),(x,y,750))
    rod('X1',(0,0,750),(1200,0,750));rod('X2',(0,600,750),(1200,600,750))
    rod('Y1',(0,0,750),(0,600,750));rod('Y2',(1200,0,750),(1200,600,750))
    return p


def test_complete_desk_four_corners_and_reedit_preserve_other_ends():
    p=desk_frame();before=p.to_dict()
    for ids in [('L1','X1','Y1'),('L2','X1','Y2'),('L3','X2','Y2'),('L4','X2','Y1')]:
        p=api().apply_joint_choice(p,CAT,member_ids=ids,host_member_id=ids[0]).project
    s=solve_cutbacks(p,CAT,strict=True)
    assert len(p.joints)==8 and all(s.lengths[m].cut_length_mm==760 for m in ('L1','L2','L3','L4'))
    assert s.lengths['X1'].cut_length_mm==1180 and s.lengths['Y2'].cut_length_mm==580
    external={k:v for k,v in p.joints.items() if v.host_member_id!='L1'}
    q=api().apply_joint_choice(p,CAT,member_ids=['L1','X1','Y1'],host_member_id='X1',gap_mm=1).project
    assert all(q.joints[k]==v for k,v in external.items())
    assert not solve_cutbacks(q,CAT,strict=True).issues
    assert q.to_dict()['nodes']==before['nodes']


def test_large_world_coordinates_preserve_double_precision_and_local_contact():
    p=corner()
    for n in p.nodes.values():n.position_mm=tuple(x+1234567.89123 for x in n.position_mm)
    assert all(c.valid for c in api().joint_choices(p,CAT,member_ids=p.members,gap_mm=.001))
