from pathlib import Path
import ast
ROOT=Path(__file__).parents[2];E=ROOT/'extension/aludiy_designer'

def test_draw_and_g_use_the_same_candidate_pipeline():
    for path in ('operators.py','g_move.py'):
        source=(E/path).read_text()
        assert 'engineering_candidates(' in source, f'{path} still has a separate picker'
    tree=ast.parse((E/'operators.py').read_text())
    func=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_point_from_event')
    text=ast.unparse(func)
    assert '_nearest_node(' not in text and '_nearest_node_in_view(' not in text

def test_draw_resolved_endpoint_does_not_quantize_through_blender_vector():
    tree=ast.parse((E/'operators.py').read_text())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='ALUDIY_OT_draw_member')
    func=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_resolved_end')
    assert 'resolve_draw_endpoint' in ast.unparse(func)
    assert 'Vector(' not in ast.unparse(func)

def test_draw_ctrl_tab_and_plane_lock_are_explicit_and_do_not_rebind_global_keys():
    source=(E/'operators.py').read_text()
    draw=source[source.index('class ALUDIY_OT_draw_member'):source.index('class ALUDIY_OT_export_project')]
    for token in ('LEFT_CTRL','RIGHT_CTRL','TAB','_plane_lock','_snap_options','_free','_navigating'):
        assert token in draw

def test_draw_overlay_shows_resolved_not_stale_pointer_and_reference_kind():
    source=(E/'viewport_overlay.py').read_text()
    assert '_display_point' in source and '_display_snap' in source and 'describe_candidate' in source

def test_draw_and_move_share_double_precision_unit_conversion_at_viewport_boundary():
    for path in ('operators.py','g_move.py'):
        source=(E/path).read_text()
        assert 'world_ray_mm' in source and 'project_point_mm' in source
