from pathlib import Path
import pytest
from aludiy_core import ProfileCatalog
from aludiy_core.section_picker import section_layout
CAT=ProfileCatalog.from_source_directory(Path(__file__).parents[2]/'catalog/profiles')
@pytest.mark.parametrize('scale',[1,1.5,2])
@pytest.mark.parametrize('angle',[0,45,90])
def test_console_controls_are_distinct_visible_and_do_not_cover_slots(scale,angle):
 lay=section_layout(CAT.get('generic:tslot-2040@0.1').section,angle,region_width=1700,region_height=1200,ui_scale=scale)
 assert hasattr(lay,'create_rect'),'slot console controls missing'
 controls=[('PIN',lay.pin_rect),('CLEAR',lay.clear_rect),('CREATE',lay.create_rect),('UNLINK_SELECTED',lay.unlink_rect),('UNLINK_SLOT',lay.unlink_slot_rect)]
 for name,rect in controls:
  assert lay.hit(rect.center)==(name,'')
  assert lay.rect.contains(rect.center)
  for s in lay.slots:assert not rect.contains(s.center) and not rect.contains(s.label_rect.center)
 for s in lay.slots:assert lay.hit(s.center)==('SLOT',s.interface_id)
