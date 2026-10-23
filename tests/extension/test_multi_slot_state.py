"""Execute actual non-bpy state helpers with guarded scene settings."""
import ast
from pathlib import Path
from types import SimpleNamespace
import json
import pytest
from aludiy_core import Project,Node,Member,ProfileCatalog
from aludiy_core import slot_selection as choice_model
from aludiy_core.associations import slot_reference
from aludiy_core.errors import ValidationError
ROOT=Path(__file__).parents[2]
CAT=ProfileCatalog.from_source_directory(ROOT/'catalog/profiles')

def api():
    tree=ast.parse((ROOT/'extension/aludiy_designer/slot_tools.py').read_text())
    state=SimpleNamespace(slot_selection_json='',slot_targets_json='',slot_only=False,
        slot_target_member_id='',slot_target_interface_id='',slot_target_profile_id='',slot_target_catalog_revision='',
        inspected_member_id='',inspected_profile_id='',inspected_interface_id='',endpoint_member_id='',endpoint_side='')
    log=[];runtime=SimpleNamespace(settings=lambda _:state,get_catalog=lambda:CAT,set_status=lambda _,msg:log.append(msg))
    ns=dict(runtime=runtime,choice_model=choice_model,json=json,slot_reference=slot_reference,ValidationError=ValidationError)
    exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef)],type_ignores=[]),'real-slot-helpers','exec'),ns)
    assert 'target_specs' in ns and 'select_inset_slot' in ns,'multi-slot scene helpers missing'
    return state,log,ns

def project():
    p=Project('P','alpha-2026.10')
    for i in range(2):
        p.add_node(Node(f'A{i}',(i*1000,0,0)));p.add_node(Node(f'B{i}',(i*1000,0,1000)))
        p.add_member(Member(f'H{i}',f'A{i}',f'B{i}','generic:tslot-2040@0.1'))
    return p

def choose(n,p,host='H0',sid='FACE_PU.S0',extend=False):n['select_inset_slot'](None,p,host,sid,extend=extend)
def activate(n,p):n['activate_selection'](None,p)

def test_choose_many_does_not_change_active_targets_or_engineering_data():
    s,log,n=api();p=project();before=p.to_dict()
    choose(n,p);activate(n,p);choose(n,p,'H1',extend=True)
    assert len(n['selected_records'](None))==2
    assert n['target_specs'](None,p)==(('H0','FACE_PU.S0'),)
    activate(n,p)
    assert n['target_specs'](None,p)==(('H0','FACE_PU.S0'),('H1','FACE_PU.S0'))
    assert p.to_dict()==before

def test_plain_select_replaces_choice_not_previous_applied_set():
    s,_,n=api();p=project();choose(n,p);activate(n,p);choose(n,p,'H1')
    assert [r.member_id for r in n['selected_records'](None)]==['H1']
    assert n['target_spec'](None,p)[0]=='H0'

def test_stop_only_clears_active_but_keeps_choices_and_relations():
    s,_,n=api();p=project();choose(n,p);activate(n,p);before=p.to_dict();n['clear_target'](None)
    assert n['target_specs'](None,p)==() and len(n['selected_records'](None))==1
    assert p.to_dict()==before

def test_remove_current_from_both_collections_keeps_other_target():
    s,_,n=api();p=project();choose(n,p);choose(n,p,'H1',extend=True);activate(n,p)
    n['remove_chosen_slot'](None,'H0','FACE_PU.S0')
    assert n['target_specs'](None,p)==(('H1','FACE_PU.S0'),)
    assert [r.member_id for r in n['selected_records'](None)]==['H1']

def test_clear_selection_clears_targets_without_writing_project():
    s,_,n=api();p=project();choose(n,p);activate(n,p);before=p.to_dict()
    n['clear_selection'](None)
    assert not n['target_specs'](None,p) and not n['selected_records'](None)
    assert p.to_dict()==before

def test_delete_one_host_prunes_only_its_entries_and_warns_once():
    s,log,n=api();p=project();choose(n,p);choose(n,p,'H1',extend=True);activate(n,p)
    p.remove_members(['H0']);before=p.to_dict()
    assert n['snapping_targets'](None,p)==(('H1','FACE_PU.S0'),)
    assert len(log)==1 and s.slot_target_member_id=='H1'
    n['snapping_targets'](None,p);assert len(log)==1 and p.to_dict()==before

def test_invalid_revision_stays_strict_and_no_read_mutation():
    s,_,n=api();p=project();choose(n,p);activate(n,p)
    records=json.loads(s.slot_targets_json);records[0]['catalog_revision']='old';s.slot_targets_json=json.dumps(records)
    before=vars(s).copy()
    with pytest.raises(ValidationError):n['target_specs'](None,p)
    assert vars(s)==before

def test_selection_reads_never_initialize_empty_scene_state():
    s,_,n=api();before=vars(s).copy()
    assert not n['selected_records'](None) and not n['target_specs'](None,project())
    assert vars(s)==before

def test_migrate_single_legacy_pin_lazily_and_preserve_strict_validation():
    s,_,n=api();p=project()
    s.slot_target_member_id='H0';s.slot_target_interface_id='FACE_PU.S0'
    s.slot_target_profile_id='generic:tslot-2040@0.1';s.slot_target_catalog_revision=CAT.get(s.slot_target_profile_id).catalog_revision
    before=vars(s).copy()
    assert n['target_specs'](None,p)==(('H0','FACE_PU.S0'),) and vars(s)==before
    choose(n,p,'H1',extend=True);activate(n,p)
    assert len(n['target_specs'](None,p))==2

def test_legacy_missing_host_without_snapshot_is_still_cleared():
    s,log,n=api();p=project();s.slot_target_member_id='missing';s.slot_target_interface_id='foo'
    assert not n['snapping_targets'](None,p) and not s.slot_target_member_id
    assert len(log)==1

def test_partial_deleted_target_status_does_not_claim_ordinary_snapping_in_restricted_mode():
    s,log,n=api();p=project();choose(n,p);choose(n,p,'H1',extend=True);activate(n,p)
    s.slot_only=True;p.remove_members(['H0']);n['snapping_targets'](None,p)
    assert '仅所选槽轨' in log[-1] and '普通吸附可用' not in log[-1]

def test_g_label_does_not_claim_activated_rails_after_stop():
    tree=ast.parse((ROOT/'extension/aludiy_designer/g_move.py').read_text())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='ALUDIY_OT_move_engineering')
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_snap_label')
    state=SimpleNamespace(slot_only=False,slot_target_member_id='')
    ns=dict(runtime=SimpleNamespace(settings=lambda _:state),describe_candidate=lambda *_:'普通吸附')
    exec(compile(ast.Module(body=[method],type_ignores=[]),'real-g-label','exec'),ns)
    op=SimpleNamespace(_free=False,_typed='',_snap=None,_scene=None,_original=None)
    label=ns['_snap_label'](op)
    assert '已启用槽轨' not in label and '普通吸附' in label
