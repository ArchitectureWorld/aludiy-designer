import importlib.util
import pytest

def module():
    assert importlib.util.find_spec('aludiy_core.overlay_layout') is not None,'safe label layout missing'
    from aludiy_core import overlay_layout
    return overlay_layout

def test_wrapping_preserves_chinese_identifiers_without_shrinking():
    text='垂足 M-001 · 距起端 300.0 / 1000.0 mm · 仅定位'
    rows=module().wrap_lines([text],lambda s:len(s)*10,100)
    assert ''.join(rows)==text and all(len(row)*10<=100 for row in rows)

def test_label_box_stays_inside_visible_bounds_at_both_edges():
    bounds=(60,10,360,600)
    for anchor in [(350,590),(61,11),(700,800)]:
        x,y=module().place_box(anchor,(280,160),bounds)
        assert 60<=x and x+280<=360 and 10<=y and y+160<=600

def test_empty_and_short_lines_are_not_lost():
    assert module().wrap_lines(['','短句'],len,100)==['','短句']
