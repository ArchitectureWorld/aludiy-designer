import ast
from pathlib import Path
from types import SimpleNamespace
import pytest
import json
from aludiy_core import slot_selection as choice_model
from aludiy_core import Project, Node, Member, ProfileCatalog
from aludiy_core.associations import slot_reference
from aludiy_core.errors import ValidationError
ROOT=Path(__file__).parents[2]
CAT=ProfileCatalog.from_source_directory(ROOT/'catalog/profiles')

def api():
    tree=ast.parse((ROOT/'extension/aludiy_designer/slot_tools.py').read_text())
    state=SimpleNamespace(slot_target_member_id='M-001',slot_target_interface_id='FACE_PU.S0',slot_target_profile_id='generic:tslot-2020@0.1',slot_target_catalog_revision='alpha-2026.10',inspected_member_id='M-001',inspected_profile_id='',inspected_interface_id='',endpoint_member_id='M-001',endpoint_side='END')
    messages=[]
    runtime=SimpleNamespace(settings=lambda scene:state,get_catalog=lambda:CAT,set_status=lambda scene,msg:messages.append(msg))
    ns=dict(runtime=runtime,slot_reference=slot_reference,ValidationError=ValidationError,json=json,choice_model=choice_model)
    funcs=[n for n in tree.body if isinstance(n,ast.FunctionDef) ]
    exec(compile(ast.Module(body=funcs,type_ignores=[]),'actual-slot-tools','exec'),ns)
    assert 'snapping_target' in ns and 'sanitize_missing_target' in ns,'safe slot target resolver missing'
    return state,messages,ns

def project():
    p=Project('P','alpha-2026.10');p.add_node(Node('N-001',(0,0,0)));p.add_node(Node('N-002',(0,0,1000)))
    p.add_member(Member('M-001','N-001','N-002','generic:tslot-2020@0.1'));return p

def test_missing_host_clears_ephemeral_fields_but_not_project():
    s,log,n=api();p=project();p.remove_members(['M-001']);raw=p.to_dict()
    assert n['snapping_target'](object(),p) is None
    assert s.slot_target_member_id=='' and s.slot_target_interface_id=='' and len(log)==1
    assert p.to_dict()==raw
    assert n['snapping_target'](object(),p) is None and len(log)==1

def test_valid_host_target_unchanged():
    s,log,n=api();p=project();s.slot_target_catalog_revision=CAT.get(s.slot_target_profile_id).catalog_revision
    assert n['snapping_target'](object(),p)==('M-001','FACE_PU.S0')
    assert s.slot_target_member_id=='M-001' and not log

def test_different_catalog_or_profile_is_not_silently_accepted():
    s,log,n=api();p=project();s.slot_target_catalog_revision='obsolete'
    with pytest.raises(ValidationError):n['snapping_target'](object(),p)
    assert s.slot_target_member_id=='M-001' and not log

def test_blank_target_is_noop():
    s,log,n=api();s.slot_target_member_id=''
    assert n['snapping_target'](object(),project()) is None and not log
