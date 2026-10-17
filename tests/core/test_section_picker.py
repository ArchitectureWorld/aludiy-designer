"""The inset is drawn and picked from the same immutable region-space layout."""
from pathlib import Path
import math
import importlib
import pytest
from aludiy_core import ProfileCatalog, Project, Member, Node

CAT = ProfileCatalog.from_source_directory(Path(__file__).parents[2]/'catalog'/'profiles')
P40 = 'generic:tslot-2040@0.1'

def api():
    # Fail as a clear missing-feature assertion on the pre-implementation baseline.
    name = 'aludiy_core.section_picker'
    assert importlib.util.find_spec(name) is not None, 'shared section picking/readout API is missing'
    return importlib.import_module(name)

def layout(angle=0, **kw):
    return api().section_layout(CAT.get(P40).section, angle, **dict(region_width=1000, region_height=850, **kw))

@pytest.mark.parametrize('angle',[0,45,90,180,270,359])
def test_each_rotated_slot_and_label_hits_its_stable_id(angle):
    lay = layout(angle)
    assert len(lay.slots)==6
    for slot in lay.slots:
        assert lay.hit(slot.center)==('SLOT',slot.interface_id)
        assert lay.hit(slot.label_rect.center)==('SLOT',slot.interface_id)

def test_empty_inset_blocks_underlying_model_and_outside_passes_through():
    lay=layout()
    assert lay.hit((lay.rect.x+5,lay.rect.y+lay.rect.height-8))==('PANEL','')
    assert lay.hit((lay.rect.x-1,lay.rect.y)) is None
    assert lay.hit(lay.pin_rect.center)==('PIN','')
    assert lay.hit(lay.clear_rect.center)==('CLEAR','')

def test_closed_face_and_center_do_not_invent_slots():
    lay=api().section_layout(CAT.get('generic:tslot-3030-3open@0.1').section,0,region_width=1000,region_height=850)
    assert len(lay.slots)==3
    assert lay.hit(lay.center)==('PANEL','')

def test_near_slot_hits_without_pixel_perfect_click():
    lay=layout();s=lay.slots[0]
    assert lay.hit((s.center[0]+6,s.center[1]))==('SLOT',s.interface_id)

def test_two_parallel_slots_remain_separately_pickable():
    lay=layout()
    s0,s1=[s for s in lay.slots if s.interface_id.startswith('FACE_PV')]
    assert s0.center!=s1.center
    assert s0.hit_radius < math.dist(s0.center,s1.center)/2

@pytest.mark.parametrize('scale',[1,1.25,1.5,2])
def test_sidebar_toolbar_and_dpi_share_bounds(scale):
    lay=api().section_layout(CAT.get(P40).section,45,region_width=1600,region_height=1100,visible_right=1180,toolbar_width=60,ui_scale=scale)
    assert lay.rect.x>=60
    assert lay.rect.x+lay.rect.width<1180
    assert lay.rect.y>=0 and lay.rect.y+lay.rect.height<1100
    for s in lay.slots:assert lay.hit(s.center)==('SLOT',s.interface_id)
    assert lay.hit(lay.pin_rect.center)==('PIN','')

@pytest.mark.parametrize('w,h,edge',[(100,800,None),(1000,100,None),(1000,850,130)])
def test_too_small_view_has_no_invisible_click_target(w,h,edge):
    assert api().section_layout(CAT.get(P40).section,0,region_width=w,region_height=h,visible_right=edge) is None

def sample():
    p=Project('P-READOUT','alpha-2026.10')
    for n,pos in [('N-1',(0,0,0)),('N-2',(600,0,0)),('N-3',(0,0,300))]:p.add_node(Node(n,pos))
    p.add_member(Member('M-1','N-1','N-2',P40));p.add_member(Member('M-2','N-1','N-3',P40))
    return p

def test_readout_deduplicates_aliases_and_does_not_sum_active_length():
    r=api().selection_readout(sample(),['M-1','M-2','M-1'],[],active_member='M-2')
    assert r['member_ids']==('M-1','M-2') and r['active_member']=='M-2'
    assert r['length_mm']==300 and r['lengths']==(('M-1',600),('M-2',300))

def test_explicit_endpoint_reports_owner_length_without_selecting_owner():
    r=api().selection_readout(sample(),[],['N-2'],endpoint=('M-1','END'))
    assert r['member_ids']==() and r['node_ids']==('N-2',)
    assert r['active_member']=='M-1' and r['length_mm']==600 and r['endpoint']=='END'

def test_node_only_is_not_a_fake_member_length():
    r=api().selection_readout(sample(),[],['N-1'])
    assert r['active_member'] is None and r['length_mm'] is None
    assert r['node_coordinates']==(('N-1',(0,0,0)),)

def test_readout_uses_supplied_preview_and_never_mutates_project():
    p=sample();p.nodes['N-2'].position_mm=(800,0,0);before=p.to_dict()
    assert api().selection_readout(p,['M-1'],[])['length_mm']==800
    assert p.to_dict()==before

def test_stale_ids_and_empty_selection_are_safe():
    r=api().selection_readout(sample(),['missing'],['missing'],active_member='M-1',endpoint=('missing','END'))
    assert r['member_ids']==() and r['node_ids']==() and r['length_mm'] is None

@pytest.mark.parametrize('profile',CAT.profile_ids())
@pytest.mark.parametrize('angle',[0,45,90,180,270])
def test_slot_labels_never_overlap_inset_header_or_action_footer(profile,angle):
    lay=api().section_layout(CAT.get(profile).section,angle,region_width=1000,region_height=900)
    for slot in lay.slots:
        assert slot.label_rect.y>=lay.rect.y+94*lay.ui_scale, slot
        assert slot.label_rect.y+slot.label_rect.height<=lay.rect.y+lay.rect.height-66*lay.ui_scale,slot
