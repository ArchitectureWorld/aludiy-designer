import importlib
import json
from dataclasses import replace
from pathlib import Path
import pytest
from aludiy_core import ProfileCatalog, Project, Node, Member
from aludiy_core.errors import AluDIYError
from aludiy_core import slot_selection as s
CAT=ProfileCatalog.from_source_directory(Path(__file__).parents[2]/'catalog/profiles')

def api():
    assert hasattr(s,'SlotTarget'),'revision-bound slot selection records missing'
    return s

def project():
    p=Project('p','alpha-2026.10')
    for i in range(2):
        p.add_node(Node(f'a{i}',(i*1000,0,0)));p.add_node(Node(f'b{i}',(i*1000,0,1000)))
        p.add_member(Member(f'm{i}',f'a{i}',f'b{i}','generic:tslot-2040@0.1'))
    return p

def target(i=0,sid='FACE_PV.S0'):
    return api().make_target(project(),CAT,f'm{i}',sid)

def test_shift_toggle_cross_member_and_plain_replace():
    a,b=target(),target(1);n=api()
    choices=n.select_target((),a);choices=n.select_target(choices,b,extend=True)
    assert len(choices)==2
    assert n.select_target(choices,a,extend=True)==(b,)
    assert n.select_target(choices,a)==(a,)

def test_two_lanes_same_face_keep_two_stable_ids():
    n=api();a,b=target(),target(sid='FACE_PV.S1')
    assert len(n.select_target((a,),b,extend=True))==2

def test_selection_json_roundtrip_deterministic_dedup_and_empty():
    n=api();a,b=target(),target(1)
    assert n.encode_targets((b,a,a))==n.encode_targets((a,b))
    assert n.decode_targets(n.encode_targets((a,b)))==(a,b)
    assert n.decode_targets('')==() and n.decode_targets('[]')==()

@pytest.mark.parametrize('raw',['{','{}','null','[1]','[{}]','[true]'])
def test_malformed_selection_never_silently_cleared(raw):
    n=api()
    with pytest.raises(AluDIYError):n.decode_targets(raw)

def test_conflicting_same_identity_snapshots_rejected():
    n=api();a=target();b=replace(a,catalog_revision='different')
    with pytest.raises(AluDIYError):n.encode_targets((a,b))

def test_validate_all_exact_pairs_and_catalog_mismatch():
    n=api();a,b=target(),target(1)
    assert n.validated_pairs(project(),CAT,(a,b))==(a.key,b.key)
    with pytest.raises(AluDIYError):n.validated_pairs(project(),CAT,(a,replace(b,catalog_revision='old')))

def test_prune_only_deleted_hosts_preserve_other_records():
    n=api();a,b=target(),target(1);p=project();p.remove_members(['m0'])
    assert n.without_missing_hosts(p,(a,b))==(b,)
    assert n.without_missing_hosts(project(),(replace(a,catalog_revision='old'),))==(replace(a,catalog_revision='old'),)

@pytest.mark.parametrize('pairs',[[('a','')],[('a',)],['a'],[(1,'b')]])
def test_pairs_fail_closed_on_invalid_shape(pairs):
    with pytest.raises(AluDIYError):s.normalize_pairs(pairs)
