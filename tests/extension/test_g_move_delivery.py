from pathlib import Path
import tomllib

ROOT = Path(__file__).parents[2]

def test_g_move_dashboard_and_acceptance_do_not_overclaim_scope():
    path = ROOT / 'docs/progress/v0.1.7-alpha.html'
    assert path.is_file(), 'G move dashboard missing'
    text = path.read_text()
    for phrase in ('G 移动', '保持连接', '断开此杆端', 'Windows', '待开发', '自动退让', 'Preview'):
        assert phrase in text
    assert '完成度约' not in text
    assert (ROOT / 'docs/acceptance/v0.1.7-alpha.md').is_file()

def test_g_move_delivery_contains_real_runtime_tests_and_unchanged_extension_id():
    manifest = tomllib.loads((ROOT/'extension/aludiy_designer/blender_manifest.toml').read_text())
    assert manifest['id'] == 'aludiy_designer'
    assert tuple(map(int, manifest['version'].split('.'))) >= (0, 1, 7)
    assert (ROOT/'tools/blender_movement_test.py').is_file()
    assert 'XTestFakeKeyEvent' in (ROOT/'tools/blender_gui_move_test.py').read_text()
