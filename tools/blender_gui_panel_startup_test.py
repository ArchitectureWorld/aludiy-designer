"""Exercise the real RNA read-only Panel.draw path, without precreating a project."""
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path
from types import SimpleNamespace
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'extension'))
import aludiy_designer as addon
from aludiy_designer import panels, runtime
OUT = Path(os.environ.get('ALUDIY_EVIDENCE_DIR', '/tmp/aludiy-panel-startup'))
OUT.mkdir(parents=True, exist_ok=True)
errors, completed, checks = [], [], []

class RecordingLayout:
    """Forward to native UILayout, recording which controls actually render."""
    def __init__(self, native, calls):
        object.__setattr__(self, '_native', native)
        object.__setattr__(self, '_calls', calls)
    def __setattr__(self, name, value):
        setattr(self._native, name, value)
    def __getattr__(self, name):
        attr = getattr(self._native, name)
        if not callable(attr):
            return attr
        def call(*args, **kwargs):
            self._calls.append((name, args, kwargs))
            result = attr(*args, **kwargs)
            return RecordingLayout(result, self._calls) if isinstance(result, bpy.types.UILayout) else result
        return call

def check(value, message):
    assert value, message
    checks.append(message)
    print('PANEL_CHECK_OK', message, flush=True)
original_draw = panels.ALUDIY_PT_main.draw

def observed_draw(self, context):
    try:
        calls = []
        original_draw(SimpleNamespace(layout=RecordingLayout(self.layout, calls)), context)
        completed.append((runtime.settings(context.scene).project_json, calls))
    except Exception:
        text = traceback.format_exc()
        if text not in errors:
            errors.append(text)
            print('ACTUAL_PANEL_DRAW_ERROR\n' + text, flush=True)

panels.ALUDIY_PT_main.draw = observed_draw
original_child_draw = panels.ALUDIY_PT_selection.draw
panels.ALUDIY_PT_selection.bl_options = set()
def observed_child_draw(self, context):
    try:
        original_child_draw(self, context)
    except Exception:
        text = traceback.format_exc()
        if text not in errors:
            errors.append(text)
            print('ACTUAL_CHILD_PANEL_ERROR\n' + text, flush=True)
panels.ALUDIY_PT_selection.draw = observed_child_draw

def run():
    addon.register()
    bpy.context.preferences.view.show_splash = False
    bpy.context.preferences.view.ui_scale = float(os.environ.get('ALUDIY_TEST_UI_SCALE', '1'))
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    area.spaces.active.show_region_ui = True
    yield
    next(r for r in area.regions if r.type == 'UI').active_panel_category = 'AluDIY'
    assert runtime.settings(bpy.context.scene).project_json == ''
    area.tag_redraw()
    for _ in range(5):
        yield
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'x11grab',
                    '-video_size', '1440x1000', '-i', os.environ['DISPLAY'],
                    '-frames:v', '1', str(OUT / 'cold-start-panel.png')], timeout=10, check=True)
    check(not errors, 'native cold-start Panel.draw has no exception')
    check(bool(completed), 'native panel really rendered')
    check(runtime.settings(bpy.context.scene).project_json == '', 'cold reads do not create project data')
    check(any(c[0]=='operator' and c[1][0]=='aludiy.setup_workspace' for c in completed[-1][1]), 'workspace button remains visible')
    check(any(c[0]=='operator' and c[1][0]=='aludiy.import_project' for c in completed[-1][1]), 'import controls render below all sections')
    for name, payload in [('whitespace', ' \n\t'), ('malformed', '{broken-json'),
                           ('unsupported', '{"schema_version":"999.0.0"}')]:
        runtime.settings(bpy.context.scene).project_json = payload
        errors.clear(); completed.clear(); area.tag_redraw()
        for _ in range(3): yield
        check(not errors and bool(completed), name+' panel remains usable')
        check(runtime.settings(bpy.context.scene).project_json == payload, name+' original data retained verbatim')
        actions = {c[1][0] for c in completed[-1][1] if c[0]=='operator'}
        check('aludiy.setup_workspace' in actions and 'aludiy.import_project' in actions, name+' setup and import available')
        if name != 'whitespace':
            check('wm.save_as_mainfile' in actions, name+' save-copy recovery available')
    runtime.settings(bpy.context.scene).project_json = ''
    errors.clear(); completed.clear(); area.tag_redraw()
    for _ in range(3): yield
    check(not errors and bool(completed), 'clearing test corruption restores normal panel')
    # First explicit edit, instead of a getter, is responsible for persistence.
    with bpy.context.temp_override(window=bpy.context.window, area=area,
            region=next(r for r in area.regions if r.type=='WINDOW')):
        result = bpy.ops.aludiy.create_sample_frame()
    check(result == {'FINISHED'}, 'first explicit edit initializes the project')
    before = runtime.settings(bpy.context.scene).project_json
    check(bool(before) and len(runtime.get_project(bpy.context.scene).members)==4,
          'sample creation persists four members')
    errors.clear(); completed.clear(); area.tag_redraw()
    for _ in range(3): yield
    check(not errors and bool(completed), 'populated project native panel renders')
    check(runtime.settings(bpy.context.scene).project_json==before, 'reading populated panel never rewrites data')
    original_scene = bpy.context.scene
    empty_scene = bpy.data.scenes.new('Empty panel regression')
    bpy.context.window.scene = empty_scene
    errors.clear(); completed.clear(); area.tag_redraw()
    for _ in range(3): yield
    check(not errors and bool(completed), 'new additional scene panel renders without prior initialization')
    check(runtime.settings(empty_scene).project_json=='', 'new scene remains uninitialized by display')
    addon.unregister(); addon.register()
    errors.clear(); completed.clear(); area.tag_redraw()
    for _ in range(3): yield
    check(not errors and bool(completed), 'disable-enable on empty scene keeps native panel usable')
    check(runtime.settings(empty_scene).project_json=='', 'disable-enable does not initialize empty data')
    check(runtime.settings(original_scene).project_json==before, 'other scene engineering data preserved')
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'empty-panel.blend'))
    check(runtime.settings(empty_scene).project_json=='', 'saving empty scene does not initialize project')
    (OUT / 'report.json').write_text(json.dumps({'status':'passed','checks':checks,
        'blender':bpy.app.version_string,'completed_draws':len(completed),
        'ui_scale':bpy.context.preferences.view.ui_scale}, ensure_ascii=False, indent=2))
    print('PANEL_STARTUP_OK', flush=True)
    addon.unregister()
    bpy.ops.wm.quit_blender()

sequence = run()
def tick():
    try:
        next(sequence)
        return .5
    except StopIteration:
        return None
    except Exception:
        print(traceback.format_exc(), flush=True)
        sys.stdout.flush()
        os._exit(1)
bpy.app.timers.register(tick, first_interval=1.5)
