import importlib.util
import math
import pytest

def api():
    assert importlib.util.find_spec('aludiy_core.action_wheel') is not None, 'wheel layout and gesture API missing'
    from aludiy_core import action_wheel
    return action_wheel

@pytest.mark.parametrize('scale',[.75,1,1.5,2])
def test_wheel_clamps_to_visible_region_and_hits_every_command(scale):
    a=api();w=a.wheel_layout((9999,9999),width=1100,height=1000,scale=scale)
    assert 0<=w.rect.x and w.rect.x+w.rect.width<=1100
    assert 0<=w.rect.y and w.rect.y+w.rect.height<=1000
    assert len(w.buttons)==8
    for key,rect in w.buttons:
        assert w.hit(rect.center)==key
        assert len([x for x,r in w.buttons if r.contains(rect.center)])==1
    assert w.hit((-1,-1)) is None and w.hit(w.center) is None

def test_tiny_window_no_invisible_controls():
    assert api().wheel_layout((2,2),width=100,height=100,scale=1) is None

@pytest.mark.parametrize('duration,dx,angle,expected',[(.1,0,0,True),(.1,2,.002,True),(.7,0,0,False),(.1,100,0,False),(.1,0,.15,False)])
def test_tap_vs_native_rotation(duration,dx,angle,expected):
    assert api().is_middle_tap(duration,(0,0),(dx,0),angle,scale=1)==expected
