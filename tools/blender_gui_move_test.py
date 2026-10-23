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
        k=unicode or {'RET':'Return','ESC':'Escape','ONE':'1','ZERO':'0'}.get(type,type.lower())
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

def run():
    global window,left,right,D
    D=X11.XOpenDisplay(None)
    bpy.app.debug_events=False
    addon.register(); bpy.context.window_manager.keyconfigs.update()
    window=bpy.context.window; window.workspace.name=runtime.WORKSPACE_NAME
    for o in window.scene.objects: o.hide_set(True)
    a=next(a for a in window.screen.areas if a.type=='VIEW_3D')
    with bpy.context.temp_override(window=window,area=a,region=next(r for r in a.regions if r.type=='WINDOW')):
        bpy.ops.screen.area_split(direction='VERTICAL',factor=.53)
    yield
    areas=sorted([a for a in window.screen.areas if a.type=='VIEW_3D'],key=lambda a:a.x)
    left,right=areas[0],areas[-1]
    with ctx(): view_sync.configure_dual_views(bpy.context)
    for a in [left,right]:
        rv=a.spaces.active.region_3d
        rv.view_rotation=Euler((math.radians(65),0,math.radians(35))).to_quaternion()
        rv.view_location=(.45,.2,.5); rv.view_distance=2.6
        a.spaces.active.show_region_ui = a==right; a.spaces.active.show_gizmo=False
    reset(); yield
    ui=next(r for r in right.regions if r.type=='UI')
    ui.active_panel_category='AluDIY'
    yield
    (OUT/'endpoint-start.aludiy.json').write_text(raw())
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'endpoint-start.blend'))
    screenshot('01-controls.png')
    mouse(*point('N-001')); yield
    key('LEFTMOUSE'); yield
    with ctx(): check(g_move.endpoint_context(bpy.context)==('M-003','END'),'pixel click picks owned endpoint in LINE view')
    original=raw(); key('G'); yield
    check(g_move._ACTIVE is not None,'G starts engineering modal')
    key('Z'); yield
    yield from hundred()
    check(g_move._ACTIVE is not None and abs(g_move._ACTIVE._delta.z-100)<1e-4,'G Z 100mm exact relative displacement')
    check(raw()==original,'preview does not write persisted JSON')
    check(g_move.display_project(window.scene).nodes['N-001'].position_mm[2]==900,'shared endpoint preview reaches 900')
    screenshot('02-keep-preview.png')
    key('RET'); yield
    check(g_move._ACTIVE is None and z()==900,'Enter commits KEEP')
    check(len(runtime.get_project(window.scene).nodes)==4,'KEEP does not split nodes')
    screenshot('03-keep-result.png')
    key('Z',ctrl=True); yield
    check(z()==800,'one Ctrl+Z undoes endpoint move')
    key('Z',ctrl=True,shift=True); yield
    check(z()==900,'Ctrl+Shift+Z redoes endpoint move')
    reset(); yield
    with ctx(): bpy.ops.aludiy.select_endpoint(endpoint='END')
    runtime.settings(window.scene).move_connection_mode='DETACH'
    mouse(*point('N-001')); yield
    original=raw(); key('G'); yield
    key('Z'); yield
    yield from hundred()
    check(len(g_move.display_project(window.scene).nodes)==5,'DETACH split remains candidate-only')
    key('ESC'); yield
    check(raw()==original and len(runtime.get_project(window.scene).nodes)==4,'Esc restores DETACH without orphan nodes')
    # This legacy movement test targets model pixels, not the section console.
    # Keep them unobstructed; dedicated section suites verify click blocking.
    runtime.settings(window.scene).show_section_inspector=False
    reset(); yield
    mouse(*point('N-001',right)); yield
    key('LEFTMOUSE'); yield
    with ctx(right): check(g_move.endpoint_context(bpy.context)==('M-003','END'),'pixel click picks owned endpoint in SOLID view')
    runtime.settings(window.scene).move_connection_mode='DETACH'
    key('G'); yield
    key('Z'); yield
    yield from hundred()
    check(raw()==original,'DETACH remains uncommitted during drag')
    screenshot('04-detach-preview.png')
    key('RET'); yield
    p=runtime.get_project(window.scene); new=p.members['M-003'].end_node_id
    check(new!='N-001' and p.nodes['N-001'].position_mm[2]==800 and p.nodes[new].position_mm[2]==900,'DETACH moves only selected rod end')
    screenshot('05-detach-result.png')
    key('Z',ctrl=True); yield
    check(len(runtime.get_project(window.scene).nodes)==4,'Undo restores detached topology')
    reset(); yield
    mouse(*point('N-001')); yield
    key('G'); yield
    mouse(cursor[0]+50,cursor[1]+35); yield
    check(g_move._ACTIVE is not None and g_move._ACTIVE._delta.length>1,'mouse-only G gives preview without coordinates')
    key('RIGHTMOUSE'); yield
    check(g_move._ACTIVE is None and z()==800,'right-click cancels mouse move')
    reset(); yield
    with ctx(): bpy.ops.aludiy.select_endpoint(endpoint='END')
    mouse(*point('N-001')); yield
    key('G'); yield
    yield from type_text('100')
    key('X'); yield
    check(abs(g_move._ACTIVE._delta.x-100)<1e-4 and abs(g_move._ACTIVE._delta.z)<1e-4,'number then axis uses millimetres')
    key('ESC'); yield
    key('G'); yield
    key('Z'); yield
    yield from type_text('-100')
    key('RET'); yield
    check(z()==700,'negative bare numeric distance moves down in millimetres')
    reset(); yield
    with ctx(): bpy.ops.aludiy.select_endpoint(endpoint='END')
    mouse(*point('N-001')); yield
    before=raw(); key('G'); yield
    key('Z'); yield
    yield from type_text('-800')
    key('RET'); yield
    check(g_move._ACTIVE is not None and bool(g_move._ACTIVE._error) and raw()==before,'collapsed rod cannot be committed')
    key('ESC'); yield
    check(raw()==before,'invalid preview cancels without data changes')
    key('G'); yield
    key('Z',shift=True); yield
    mouse(cursor[0]+70,cursor[1]+30); yield
    check(g_move._ACTIVE is not None and abs(g_move._ACTIVE._delta.z)<1e-4 and g_move._ACTIVE._delta.length>1,'Shift Z locks the XY displacement plane')
    key('ESC'); yield
    reset(); yield
    with ctx():
        runtime.settings(window.scene).solid_display_mode='PROFILE'
        scene_adapter.select_entity(window.scene,bpy.context.view_layer,'M-003')
        bpy.ops.aludiy.select_endpoint(endpoint='END')
    mouse(*point('N-001')); yield
    key('G'); yield
    key('Z'); yield
    yield from hundred()
    key('RET'); yield
    check(z()==900 and any(len(o.data.vertices)>8 for o in window.scene.objects if o.get('aludiy_entity_type')=='MEMBER_SOLID'),'detailed slot geometry follows engineering G')
    runtime.settings(window.scene).solid_display_mode='BOX'
    reset(); yield
    with ctx():
        scene_adapter.select_entity(window.scene,bpy.context.view_layer,'M-001')
        for o in window.scene.objects:
            if o.get('aludiy_entity_id')=='M-002': o.select_set(True)
    yield
    mouse(*point('N-001')); yield
    key('G'); yield
    key('Z'); yield
    yield from hundred()
    key('RET'); yield
    p=runtime.get_project(window.scene)
    check(all(p.nodes[n].position_mm[2]==900 for n in ['N-001','N-002','N-003']),'multi-member G deduplicates shared nodes')
    with ctx():
        bpy.ops.object.select_all(action='DESELECT')
        left.spaces.active.use_local_collections=False
        cube=bpy.data.objects['Cube']; cube.hide_set(False); cube.select_set(True)
        bpy.context.view_layer.objects.active=cube; native_z=cube.location.z
    yield
    original=raw(); mouse(left.x+200,left.y+250); yield
    key('G'); yield
    check(g_move._ACTIVE is None,'ordinary Cube retains native G')
    key('Z'); yield
    key('ONE','1'); yield
    key('RET'); yield
    check(abs(bpy.data.objects['Cube'].location.z-native_z-1)<1e-4,'native Cube translation works')
    check(raw()==original,'native G does not alter engineering data')
    reset(); yield
    with ctx():
        bpy.ops.aludiy.select_endpoint(endpoint='END')
        bpy.ops.aludiy.move_engineering(delta_mm=(0,0,100),detach=True)
    expected=raw(); (OUT/'expected.aludiy.json').write_text(expected)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'endpoint-demo.blend'))
    check(expected==raw(),'save preserves topology')
    (OUT/'report.json').write_text(json.dumps({'status':'passed','blender':bpy.app.version_string,'checks':checks},ensure_ascii=False,indent=2))
    print('ALUDIY_GUI_MOVE_OK',len(checks),flush=True)
    addon.unregister(); bpy.ops.wm.quit_blender()

sequence=run()
def tick():
    try:
        next(sequence); return .23
    except StopIteration: return None
    except Exception:
        text=traceback.format_exc(); print(text,flush=True)
        (OUT/'report.json').write_text(json.dumps({'status':'failed','checks':checks,'error':text},ensure_ascii=False,indent=2))
        try: screenshot('failure.png')
        except Exception: pass
        sys.stdout.flush(); os._exit(1)
bpy.app.timers.register(tick,first_interval=1.0)
