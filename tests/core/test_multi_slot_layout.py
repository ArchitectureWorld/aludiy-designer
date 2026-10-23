from pathlib import Path
import pytest
from aludiy_core import ProfileCatalog
from aludiy_core.section_picker import section_layout
CAT=ProfileCatalog.from_source_directory(Path(__file__).parents[2]/'catalog/profiles')
@pytest.mark.parametrize('scale',[1,1.5,2])
@pytest.mark.parametrize('roll',[0,45,90])
def test_multi_slot_controls_have_nonoverlapping_hit_areas(scale,roll):
    lay=section_layout(CAT.get('generic:tslot-2040@0.1').section,roll,
        region_width=1700,region_height=1200,ui_scale=scale)
    assert hasattr(lay,'mode_rect'),'mixed/restricted snap selector missing'
    controls=[('PIN',lay.pin_rect),('CLEAR',lay.clear_rect),('CREATE',lay.create_rect),
        ('UNLINK_SELECTED',lay.unlink_rect),('UNLINK_SLOT',lay.unlink_slot_rect),
        ('MODE',lay.mode_rect),('REMOVE_SLOT',lay.remove_rect),('CLEAR_SELECTION',lay.clear_selection_rect)]
    for name,rect in controls:
        assert lay.hit(rect.center)==(name,'')
        assert lay.rect.contains(rect.center)
        for other,area in controls:
            if other!=name: assert not area.contains(rect.center)
        for slot in lay.slots: assert not rect.contains(slot.center) and not rect.contains(slot.label_rect.center)
