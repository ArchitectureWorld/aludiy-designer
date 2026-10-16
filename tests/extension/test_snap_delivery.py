from pathlib import Path
import ast
ROOT=Path(__file__).parents[2]

def test_snap_delivery_explains_true_current_scope():
    for path in ('docs/acceptance/v0.1.9-alpha.md','docs/progress/v0.1.9-alpha.html'):
        text=(ROOT/path).read_text()
        for term in ('Ctrl','重新连接','仅定位','待','Preview'):
            assert term in text
    assert (ROOT/'tools/blender_gui_snap_test.py').is_file()
    assert (ROOT/'tools/blender_reopen_snap_test.py').is_file()

def test_g_key_does_not_retain_explicit_picker_mode():
    text=(ROOT/'extension/aludiy_designer/g_move.py').read_text()
    assert 'move_key.properties.connect_only=False' in text
    assert "default=False, options={'HIDDEN','SKIP_SAVE'}" in text
    tree=ast.parse(text)
    constants=[n.value for n in ast.walk(tree) if isinstance(n,ast.Constant)]
    assert 'LEFT_CTRL' in constants and 'RIGHT_CTRL' in constants and 'TAB' in constants
