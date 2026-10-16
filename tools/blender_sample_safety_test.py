"""Real Blender/X11 regression of sample insertion, reset confirmation and undo."""
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

import bpy
from mathutils import Euler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'extension'))
import aludiy_designer as addon
from aludiy_designer import runtime, scene_adapter, view_sync
from aludiy_designer.vendor.aludiy_core import Project, Node, Member

OUT = Path(os.environ['ALUDIY_EVIDENCE_DIR'])
OUT.mkdir(parents=True, exist_ok=True)
checks = []
X = ctypes.CDLL('libX11.so.6')
T = ctypes.CDLL('libXtst.so.6')
X.XOpenDisplay.restype = ctypes.c_void_p
X.XStringToKeysym.argtypes = [ctypes.c_char_p]
X.XStringToKeysym.restype = ctypes.c_ulong
X.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
X.XKeysymToKeycode.restype = ctypes.c_uint
X.XFlush.argtypes = [ctypes.c_void_p]
T.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
T.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
D = X.XOpenDisplay(None)


def key(name, ctrl=False, shift=False):
    def edge(k, down):
        code = X.XKeysymToKeycode(D, X.XStringToKeysym(k.encode()))
        assert code
        T.XTestFakeKeyEvent(D, code, int(down), 0)
    if ctrl: edge('Control_L', True)
    if shift: edge('Shift_L', True)
    edge(name, True); edge(name, False)
    if shift: edge('Shift_L', False)
    if ctrl: edge('Control_L', False)
    X.XFlush(D)


def check(value, label):
    assert value, label
    checks.append(label)
    print('SAMPLE_GUI_CHECK_OK', label, flush=True)


def data():
    return runtime.get_project(bpy.context.scene).to_dict()


def screenshot():
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'x11grab', '-video_size', '1800x1100', '-i', os.environ['DISPLAY'], '-frames:v', '1', str(OUT / 'sample-preserved.png')], check=True, timeout=15)


def run():
    addon.register()
    window = bpy.context.window
    area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=window, area=area, region=region):
        view_sync.setup_workspace(bpy.context)
    yield
    areas = sorted([a for a in window.screen.areas if a.type == 'VIEW_3D'], key=lambda a: a.x)
    left, right = areas[0], areas[-1]
    for a in areas:
        rv = a.spaces.active.region_3d
        rv.view_rotation = Euler((1.05, 0, 0.55)).to_quaternion()
        rv.view_location = (1.2, 0.2, 0.3)
        rv.view_distance = 5.5
        a.spaces.active.show_region_ui = a == right
    scene = window.scene
    p = Project('P-USER-SAMPLE-SAFETY', 'alpha-2026.10')
    p.add_node(Node('N-001', (0, 0, 0)))
    p.add_node(Node('N-002', (0, 0, 800)))
    p.add_member(Member('M-001', 'N-001', 'N-002', 'generic:tslot-2020@0.1', roll_deg=90, revision=7))
    runtime.set_project(scene, p)
    scene_adapter.rebuild_scene(scene, p, runtime.get_catalog())
    scene.cursor.location = (1.5, 0, 0)
    settings = runtime.settings(scene)
    settings.sample_width_input = '1200'
    settings.sample_depth_input = '600'
    before = data()
    cube_name = next(o.name for o in scene.objects if o.type == 'MESH' and not o.get('aludiy_managed'))
    native_matrix = tuple(v for row in scene.objects[cube_name].matrix_world for v in row)
    km = window.window_manager.keyconfigs.addon if hasattr(window, 'window_manager') else bpy.context.window_manager.keyconfigs.addon
    keymap = km.keymaps.new(name='3D View', space_type='VIEW_3D')
    bindings = [keymap.keymap_items.new('aludiy.create_sample_frame', 'F6', 'PRESS'), keymap.keymap_items.new('aludiy.new_project', 'F7', 'PRESS')]
    bpy.context.window_manager.keyconfigs.update()
    with bpy.context.temp_override(window=window, area=left, region=next(r for r in left.regions if r.type == 'WINDOW')):
        bpy.ops.ed.undo_push(message='sample safety baseline')
    T.XTestFakeMotionEvent(D, 0, left.x + 180, 400, 0); X.XFlush(D)
    yield
    key('F6'); yield
    after = data()
    check(after['project_id'] == before['project_id'], 'insertion preserves project identity')
    check(len(after['members']) == 5 and len(after['nodes']) == 10, 'one sample appends four members and eight independent nodes')
    check(all(m in after['members'] for m in before['members']) and all(n in after['nodes'] for n in before['nodes']), 'old coordinates parameters and topology unchanged')
    check(any(n['position_mm'] == [1500.0, 0.0, 0.0] for n in after['nodes']), 'sample begins at the 3D cursor')
    for kind in ['MEMBER_AXIS', 'MEMBER_SOLID']:
        ids = {o.get('aludiy_entity_id') for o in scene.objects if o.get('aludiy_entity_type') == kind}
        check(ids == {m['id'] for m in after['members']}, kind + ' matches preserved project')
    key('z', ctrl=True); yield
    check(data() == before, 'one Ctrl+Z removes only the inserted sample')
    key('z', ctrl=True, shift=True); yield
    check(data() == after, 'redo restores the sample and original design')
    key('F7'); yield
    check(data() == after, 'new project opens confirmation without clearing anything')
    key('Escape'); yield
    check(data() == after, 'cancel reset preserves the complete project')
    key('F6'); yield
    repeated = data()
    check(len(repeated['members']) == 9 and len(repeated['nodes']) == 18, 'repeated insertion appends rather than replaces')
    check(all(m in repeated['members'] for m in after['members']), 'second insertion preserves every previous member')
    check(tuple(v for row in bpy.context.scene.objects[cube_name].matrix_world for v in row) == native_matrix, 'ordinary Blender object untouched')
    key('F7'); yield
    key('Return'); yield
    check(len(data()['members']) == 0, 'confirmed reset clears engineering data')
    key('z', ctrl=True); yield
    check(data() == repeated, 'undo reset restores old design plus both samples')
    (OUT / 'expected.aludiy.json').write_text(json.dumps(data(), ensure_ascii=False), encoding='utf-8')
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'sample-safety.blend'))
    check(data() == repeated, 'save does not alter project topology')
    yield
    screenshot()
    for binding in bindings:
        keymap.keymap_items.remove(binding)
    (OUT / 'report.json').write_text(json.dumps({'status': 'passed', 'checks': checks, 'blender': bpy.app.version_string}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('ALUDIY_SAMPLE_SAFETY_GUI_OK', len(checks), flush=True)
    addon.unregister()
    bpy.ops.wm.quit_blender()


sequence = run()
def tick():
    try:
        next(sequence)
        return 0.7
    except StopIteration:
        return None
    except Exception:
        text = traceback.format_exc()
        print(text, flush=True)
        (OUT / 'report.json').write_text(json.dumps({'status': 'failed', 'checks': checks, 'error': text}), encoding='utf-8')
        sys.stdout.flush()
        os._exit(1)
bpy.app.timers.register(tick, first_interval=1.5)
