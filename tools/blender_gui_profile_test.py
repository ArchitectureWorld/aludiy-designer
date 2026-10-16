"""Real-window regression using Xvfb + XTest; use an isolated config with splash disabled."""
import os, sys, json, math, traceback, subprocess, ctypes
from pathlib import Path
import bpy
from mathutils import Vector, Euler
from bpy_extras import view3d_utils
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'extension'))
import aludiy_designer as addon
from aludiy_designer import runtime, scene_adapter, g_move, view_sync
from aludiy_designer.vendor.aludiy_core import Project,Member,Node
OUT=Path(os.environ.get('ALUDIY_EVIDENCE_DIR','/tmp/aludiy-gui')); OUT.mkdir(parents=True,exist_ok=True)
checks=[]; window=None; left=None; right=None; cursor=(300,400)

def check(value, message):
    assert value,message
    checks.append(message); print('GUI_CHECK_OK',message,flush=True)

def frame():
    p=Project('P-ENDPOINT-EXPERIENCE','alpha-2026.10')
    for nid,xyz in [('N-001',(0,0,800)),('N-002',(1200,0,800)),('N-003',(0,600,800)),('N-004',(0,0,0))]: p.add_node(Node(nid,xyz))
    for mid,a,b in [('M-001','N-001','N-002'),('M-002','N-001','N-003'),('M-003','N-004','N-001')]: p.add_member(Member(mid,a,b,'generic:tslot-2020@0.1'))
    return p

def ctx(area=None):
    a=area or left
    return bpy.context.temp_override(window=window,screen=window.screen,area=a,region=next(r for r in a.regions if r.type=='WINDOW'))

def reset():
    with ctx():
        runtime.set_project(bpy.context.scene,frame())
        scene_adapter.rebuild_scene(bpy.context.scene,frame(),runtime.get_catalog())
        bpy.context.view_layer.update(); bpy.ops.object.select_all(action='DESELECT')
        runtime.settings(bpy.context.scene).endpoint_member_id=''
        runtime.settings(bpy.context.scene).move_connection_mode='KEEP'
        view_sync._LAST_SELECTED_BY_WINDOW.clear()
        scene_adapter.select_entity(bpy.context.scene,bpy.context.view_layer,'M-003')
        bpy.ops.ed.undo_push(message='GUI regression baseline')

# Real X11 events are used instead of synthetic Blender events, so native
# keymap dispatch, selection, mouse and undo are exercised end-to-end.
X11=ctypes.CDLL('libX11.so.6'); XT=ctypes.CDLL('libXtst.so.6')
X11.XOpenDisplay.restype=ctypes.c_void_p
D=None
X11.XStringToKeysym.argtypes=[ctypes.c_char_p]; X11.XStringToKeysym.restype=ctypes.c_ulong
X11.XKeysymToKeycode.argtypes=[ctypes.c_void_p,ctypes.c_ulong]; X11.XKeysymToKeycode.restype=ctypes.c_uint
X11.XFlush.argtypes=[ctypes.c_void_p]
XT.XTestFakeKeyEvent.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_int,ctypes.c_ulong]
XT.XTestFakeButtonEvent.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_int,ctypes.c_ulong]
XT.XTestFakeMotionEvent.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_ulong]
def _key(k,down):
    k={'-':'minus','+':'plus','.':'period','/':'slash','*':'asterisk','(':'parenleft',')':'parenright'}.get(k,k)
    code=X11.XKeysymToKeycode(D,X11.XStringToKeysym(k.encode()))
    assert code, f'Unknown X11 key {k}'
    XT.XTestFakeKeyEvent(D,code,int(down),0)
def key(type,unicode='',ctrl=False,shift=False):
    if ctrl: _key('Control_L',True)
    if shift: _key('Shift_L',True)
    if type in {'LEFTMOUSE','RIGHTMOUSE'}:
        button=1 if type=='LEFTMOUSE' else 3
        XT.XTestFakeButtonEvent(D,button,1,0); XT.XTestFakeButtonEvent(D,button,0,0)
    else:
        k=unicode or {'RET':'Return','ESC':'Escape','ONE':'1','ZERO':'0','F6':'F6','F7':'F7'}.get(type,type.lower())
        _key(k,True); _key(k,False)
    if shift: _key('Shift_L',False)
    if ctrl: _key('Control_L',False)
    X11.XFlush(D)
def mouse(x,y):
    global cursor
    cursor=(int(x),int(y))
    XT.XTestFakeMotionEvent(D,0,cursor[0],1100-cursor[1],0); X11.XFlush(D)

def point(nid,area=None):
    a=area or left; reg=next(r for r in a.regions if r.type=='WINDOW')
    pos=view3d_utils.location_3d_to_region_2d(reg,a.spaces.active.region_3d,Vector(runtime.get_project(window.scene).nodes[nid].position_mm)*.001)
    assert pos is not None
    return reg.x+pos.x,reg.y+pos.y

def screenshot(name):
    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP',iterations=1)
    subprocess.run(['ffmpeg','-y','-loglevel','error','-f','x11grab','-video_size','1800x1100','-i',os.environ['DISPLAY'],'-frames:v','1',str(OUT/name)],timeout=8)

def raw(): return runtime.settings(window.scene).project_json
def z(nid='N-001'): return runtime.get_project(window.scene).nodes[nid].position_mm[2]
def type_text(text):
    for char in text:
        key(char.upper(),char); yield

def hundred():
    for typ,u in [('ONE','1'),('ZERO','0'),('ZERO','0'),('M','m'),('M','m')]:
        key(typ,u); yield


from aludiy_designer.vendor.aludiy_core.associations import exact_snap_delta

def frame():
    p=Project('P-MANUAL-EXPERIENCE','alpha-2026.10')
    for nid,xyz in [('N-001',(0,0,0)),('N-002',(0,0,1000)),('N-003',(0,0,500)),('N-004',(800,0,500)),('N-005',(0,0,1000)),('N-006',(600,0,1000))]:
        p.add_node(Node(nid,xyz))
    for mid,a,b in [('M-001','N-001','N-002'),('M-002','N-003','N-004'),('M-003','N-005','N-006')]:
        p.add_member(Member(mid,a,b,'generic:tslot-2020@0.1'))
    return p

def select(mids=(),nids=()):
    with ctx():
        bpy.ops.object.select_all(action='DESELECT')
        wanted=set(mids)|set(nids)
        for o in window.view_layer.objects:
            if o.get('aludiy_managed'):
                o.select_set(o.get('aludiy_entity_id') in wanted)
        if wanted:
            window.view_layer.objects.active=next(o for o in window.scene.objects if o.get('aludiy_entity_id')==list(wanted)[-1])
        view_sync._LAST_SELECTED_BY_WINDOW.clear()
        s=runtime.settings(window.scene);s.endpoint_member_id='';s.move_connection_mode='KEEP'

def pixel(xyz,area=None):
    a=area or left;reg=next(r for r in a.regions if r.type=='WINDOW')
    pos=view3d_utils.location_3d_to_region_2d(reg,a.spaces.active.region_3d,Vector(xyz)*.001)
    assert pos is not None
    return reg.x+pos.x,reg.y+pos.y

def p():return runtime.get_project(window.scene)

def run():
    global window,left,right,D
    D=X11.XOpenDisplay(None)
    addon.register();bpy.context.window_manager.keyconfigs.update();window=bpy.context.window
    window.workspace.name=runtime.WORKSPACE_NAME
    for o in window.scene.objects:o.hide_set(True)
    a=next(a for a in window.screen.areas if a.type=='VIEW_3D')
    with bpy.context.temp_override(window=window,area=a,region=next(r for r in a.regions if r.type=='WINDOW')):
        bpy.ops.screen.area_split(direction='VERTICAL',factor=.52)
    yield
    left,right=sorted([a for a in window.screen.areas if a.type=='VIEW_3D'],key=lambda a:a.x)[::1]
    with ctx():view_sync.configure_dual_views(bpy.context)
    for a in (left,right):
        rv=a.spaces.active.region_3d;rv.view_rotation=Euler((math.radians(72),0,math.radians(22))).to_quaternion()
        rv.view_location=(.35,0,.5);rv.view_distance=2.4
        a.spaces.active.show_region_ui=a==right;a.spaces.active.show_gizmo=False
    reset();select();yield
    ui=next(r for r in right.regions if r.type=='UI');ui.active_panel_category='AluDIY';yield
    check(hasattr(runtime.settings(window.scene), 'edit_profile_id'), 'profile panel fields registered')
    from aludiy_designer import profile_tools as pt
    from aludiy_designer.vendor.aludiy_core.profile_editing import interface_rails
    P40='generic:tslot-2040@0.1'; P3='generic:tslot-3030-3open@0.1'
    select(['M-001','M-002']);yield
    with ctx():
        bpy.ops.aludiy.create_associations()
        before=p().to_dict();active_before=runtime.entity_id_from_object(window.view_layer.objects.active)
        s=runtime.settings(window.scene);s.edit_profile_id=P40
    # Test-only hotkeys exercise the same operators that real panel buttons use.
    km=bpy.context.window_manager.keyconfigs.addon.keymaps.new(name='Object Mode',space_type='EMPTY')
    km.keymap_items.new('aludiy.edit_selected_profiles','F6','PRESS').properties.action='PROFILE'
    k=km.keymap_items.new('aludiy.edit_selected_profiles','F7','PRESS');k.properties.action='ROTATE';k.properties.angle='90'
    bpy.context.window_manager.keyconfigs.update()
    mouse(left.x+220,left.y+340);yield;key('F6');yield
    check(all(p().members[m].profile_type_id==P40 for m in ['M-001','M-002']), 'batch changes both profiles')
    check(p().members['M-003'].profile_type_id=='generic:tslot-2020@0.1', 'unselected profile unchanged')
    check(p().to_dict()['nodes']==before['nodes'], 'batch preserves every node coordinate and ID')
    check(p().to_dict()['associations']==before['associations'], 'batch preserves explicit host association')
    with ctx():
        check(g_move.selection_summary(bpy.context)[0]=={'M-001','M-002'}, 'batch retains multi-selection')
        check(runtime.entity_id_from_object(window.view_layer.objects.active)==active_before, 'batch retains active entity')
    screenshot('01-batch-profile.png');key('F7');yield
    check(all(p().members[m].roll_deg==90 for m in ['M-001','M-002']), 'rotate both selected sections about their own axes')
    check(p().to_dict()['nodes']==before['nodes'], 'roll never moves design axes')
    key('Z',ctrl=True);yield
    check(all(p().members[m].roll_deg==0 for m in ['M-001','M-002']), 'one native Undo restores both rolls')
    key('Z',ctrl=True,shift=True);yield
    check(all(p().members[m].roll_deg==90 for m in ['M-001','M-002']), 'Redo restores both rolls')
    with ctx():runtime.settings(window.scene).solid_display_mode='PROFILE'
    yield
    with ctx():check(g_move.selection_summary(bpy.context)[0]=={'M-001','M-002'}, 'LOD switch retains entire selection')
    check(all(len(o.data.vertices)>8 for o in window.scene.objects if o.get('aludiy_entity_type')=='MEMBER_SOLID'), 'detailed LOD rebuilt')
    # Ordinary scene objects and isolated node selection survive LOD rebuilds.
    with ctx():
        cube=next(o for o in window.scene.objects if not o.get('aludiy_managed') and o.type=='MESH')
        cube.hide_set(False);cube.select_set(True);cube.location=(2,2,2)
        cube_name=cube.name;saved=cube.location[:]
        runtime.settings(window.scene).solid_display_mode='BOX'
        check(window.scene.objects[cube_name].select_get() and window.scene.objects[cube_name].location[:]==saved, 'LOD preserves ordinary selected objects unchanged')
        runtime.settings(window.scene).solid_display_mode='PROFILE'
        cube.select_set(False);cube.hide_set(True)
    select(nids=['N-001','N-002']);yield
    with ctx():
        runtime.settings(window.scene).solid_display_mode='BOX'
        check(g_move.selection_summary(bpy.context)[1]=={'N-001','N-002'}, 'LOD preserves multi-node selection')
        runtime.settings(window.scene).solid_display_mode='PROFILE'
    select(['M-001']);yield
    with ctx():
        rails=interface_rails(p(),'M-001',runtime.get_catalog());sid=rails[0].interface_id
        original=raw();bpy.ops.aludiy.inspect_profile_slot(interface_id=sid)
        check(raw()==original, 'slot inspection is read-only')
        check(pt.selected_slot(window.scene,'M-001',p())==sid, 'slot selection identifies stable interface ID')
    screenshot('02-oriented-slot-inspector.png')
    with ctx():
        runtime.settings(window.scene).profile_roll_input='45+45/2'
        bpy.ops.aludiy.edit_selected_profiles(action='SET')
        check(p().members['M-001'].roll_deg==67.5, 'absolute degree expression applies')
        check(pt.selected_slot(window.scene,'M-001',p())==sid, 'rotation preserves stable slot identity')
        original=raw();runtime.settings(window.scene).profile_roll_input='100mm'
        try:result=bpy.ops.aludiy.edit_selected_profiles(action='SET')
        except RuntimeError:result={'CANCELLED'}
        check(result=={'CANCELLED'} and raw()==original, 'length suffix rejected in angle input without mutation')
        runtime.settings(window.scene).edit_profile_id=P3
        bpy.ops.aludiy.edit_selected_profiles(action='PROFILE')
        check(len(interface_rails(p(),'M-001',runtime.get_catalog()))==3, 'closed face exposes only three slots')
        check(pt.selected_slot(window.scene,'M-001',p()) is None, 'profile replacement clears slot inspection instead of guessing')
    select(['M-001','M-002']);yield
    with ctx():
        from unittest.mock import patch
        original=raw();real=scene_adapter.rebuild_scene;calls=[0]
        def fail_once(*args,**kwargs):
            calls[0]+=1
            if calls[0]==1:raise RuntimeError('injected rebuild failure')
            return real(*args,**kwargs)
        with patch.object(scene_adapter,'rebuild_scene',side_effect=fail_once):
            try:result=bpy.ops.aludiy.edit_selected_profiles(action='ROTATE',angle='90')
            except RuntimeError:result={'CANCELLED'}
        check(result=={'CANCELLED'} and raw()==original, 'failed rebuild restores authoritative data')
        check(g_move.selection_summary(bpy.context)[0]=={'M-001','M-002'}, 'failed rebuild restores multi-selection')
    # Movement still propagates the existing design-axis relationship.
    select(['M-001']);yield;mouse(left.x+220,left.y+340);yield;key('G');yield;key('X');yield;yield from type_text('100');key('RET');yield
    check(p().nodes['N-003'].position_mm==(100,0,500), 'host movement still drives attachment after changing section')
    select(['M-001']);yield
    with ctx():
        runtime.settings(window.scene).edit_profile_id=P40
        bpy.ops.aludiy.edit_selected_profiles(action='PROFILE')
        runtime.settings(window.scene).profile_roll_input='90'
        bpy.ops.aludiy.edit_selected_profiles(action='SET',angle='90')
        bpy.ops.aludiy.inspect_profile_slot(interface_id=interface_rails(p(),'M-001',runtime.get_catalog())[0].interface_id)
    yield;screenshot('03-final-slot-inspection.png')
    expected=raw();(OUT/'expected.aludiy.json').write_text(expected)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'profile-orientation.blend'))
    check(Project.from_dict(json.loads(expected)).to_dict()==p().to_dict(), 'JSON retains profiles rolls and associations')
    (OUT/'report.json').write_text(json.dumps({'status':'passed','blender':bpy.app.version_string,'checks':checks},ensure_ascii=False,indent=2))
    print('ALUDIY_PROFILE_GUI_OK',len(checks),flush=True)
    addon.unregister();bpy.ops.wm.quit_blender()

sequence=run()
def tick():
    try:next(sequence);return .27
    except StopIteration:return None
    except Exception:
        text=traceback.format_exc();print(text,flush=True)
        (OUT/'report.json').write_text(json.dumps({'status':'failed','checks':checks,'error':text},ensure_ascii=False,indent=2))
        try:screenshot('failure.png')
        except Exception:pass
        sys.stdout.flush();os._exit(1)
bpy.app.timers.register(tick,first_interval=1.0)
