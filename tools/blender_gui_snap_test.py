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
        k=unicode or {'RET':'Return','ESC':'Escape','TAB':'Tab','ONE':'1','ZERO':'0'}.get(type,type.lower())
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


def frame():
    p=Project('P-RECONNECT-EXPERIENCE','alpha-2026.10')
    for nid,xyz in [('N-001',(0,0,800)),('N-002',(1200,0,800)),('N-003',(0,600,800)),
                    ('N-004',(0,0,0)),('N-007',(0,0,1000)),
                    ('N-005',(1600,0,800)),('N-006',(2000,0,800))]: p.add_node(Node(nid,xyz))
    for mid,a,b in [('M-001','N-001','N-002'),('M-002','N-001','N-003'),
                    ('M-003','N-004','N-007'),('M-004','N-005','N-006')]:
        p.add_member(Member(mid,a,b,'generic:tslot-2020@0.1'))
    return p

def source(): return runtime.get_project(window.scene).members['M-003'].end_node_id

def world_mouse(pos,area=None):
    a=area or left; reg=next(r for r in a.regions if r.type=='WINDOW')
    loc=view3d_utils.location_3d_to_region_2d(reg,a.spaces.active.region_3d,Vector(pos)*.001)
    mouse(reg.x+loc.x,reg.y+loc.y)

def control(down):
    _key('Control_L',down); X11.XFlush(D)

def run():
    global window,left,right,D
    D=X11.XOpenDisplay(None)
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
        rv.view_rotation=Euler((math.radians(65),0,math.radians(30))).to_quaternion()
        rv.view_location=(.55,.15,.5); rv.view_distance=3.8
        a.spaces.active.show_region_ui=a==right; a.spaces.active.show_gizmo=False
    reset(); yield
    ui=next(r for r in right.regions if r.type=='UI');ui.active_panel_category='AluDIY';yield
    (OUT/'reconnect-start.aludiy.json').write_text(raw())
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'reconnect-start.blend'))
    screenshot('01-reconnect-controls.png')
    mouse(*point('N-007'));yield;key('LEFTMOUSE');yield
    with ctx():check(g_move.endpoint_context(bpy.context)==('M-003','END'),'click identifies detached owned endpoint')
    original=raw();key('G');yield
    mouse(*point('N-001'));yield
    check(g_move._ACTIVE is not None and g_move._ACTIVE._snap.node_id=='N-001','plain G snaps to old shared endpoint')
    check(raw()==original,'snap preview leaves authoritative JSON untouched')
    check(g_move.display_project(window.scene).members['M-003'].end_node_id=='N-001','preview shows reconnect intention')
    screenshot('02-snap-reconnect-preview.png')
    control(True);yield
    check(g_move._ACTIVE._free and g_move._ACTIVE._snap is None,'Ctrl press disables snap without mouse movement')
    check(g_move.display_project(window.scene).members['M-003'].end_node_id=='N-007','Ctrl preview retains independent endpoint')
    screenshot('03-ctrl-free-preview.png')
    control(False);yield
    check(not g_move._ACTIVE._free and g_move._ACTIVE._snap.node_id=='N-001','Ctrl release restores target immediately')
    key('ESC');yield
    check(raw()==original,'cancel reconnect restores original topology')
    with ctx():check(g_move.endpoint_context(bpy.context)==('M-003','END'),'cancel reconnect preserves endpoint selection for the next G')
    key('G');yield;mouse(*point('N-001'));yield;key('RET');yield
    check(source()=='N-001' and 'N-007' not in runtime.get_project(window.scene).nodes,'confirm reuses target node and removes orphan source')
    screenshot('04-reconnected.png')
    key('Z',ctrl=True);yield
    check(raw()==original and source()=='N-007','one undo restores pre-reconnect project')
    key('Z',ctrl=True,shift=True);yield
    check(source()=='N-001','redo restores connection')
    # Existing keep/detach rules remain orthogonal to Ctrl freedom.
    with ctx():bpy.ops.aludiy.select_endpoint(endpoint='END')
    mouse(*point('N-001'));yield;key('G');yield;key('Z');yield;yield from hundred();key('RET');yield
    check(z()==900,'moving reconnected end moves the shared node')
    check(len(g_move.runtime.get_project(window.scene).nodes)==6,'followup move does not split shared node')
    reset();yield
    with ctx():bpy.ops.aludiy.select_endpoint(endpoint='END')
    mouse(*point('N-007'));yield;key('G');yield;key('Z');yield
    mouse(*point('N-001'));yield;control(True);yield;key('RET');yield;control(False);yield
    check(source()=='N-007','Ctrl free confirmation never joins coincident nodes')
    check(math.dist(runtime.get_project(window.scene).nodes['N-007'].position_mm,(0,0,800))<3,'free axis move reaches near the target without join')
    # Force exact independent coincidence as a deterministic already-placed setup.
    with ctx():
        p=runtime.get_project(window.scene);p.nodes['N-007'].position_mm=(0,0,800)
        runtime.set_project(window.scene,p);scene_adapter.rebuild_scene(window.scene,p,runtime.get_catalog())
        scene_adapter.select_entity(window.scene,window.view_layer,'M-003');bpy.ops.aludiy.select_endpoint(endpoint='END')
    yield
    with bpy.context.temp_override(window=window,area=right,region=ui):
        bpy.ops.aludiy.move_engineering('INVOKE_DEFAULT',connect_only=True)
    yield
    mouse(*point('N-001',right));yield
    check(g_move._ACTIVE._snap.node_id=='N-001','connect-to-target picker from N panel finds overlapping target')
    key('RET');yield
    check(source()=='N-001','connect-to-target joins without requiring a detour')
    # Exact numeric displacement can join, but near misses are never rounded.
    reset();yield
    with ctx():bpy.ops.aludiy.select_endpoint(endpoint='END')
    mouse(*point('N-007'));yield;key('G');yield;key('Z');yield
    yield from type_text('-200')
    check(abs(g_move._ACTIVE._delta.z+200)<1e-6 and g_move._ACTIVE._snap.node_id=='N-001','exact numeric endpoint coincidence enables connection')
    key('RET');yield;check(source()=='N-001','numeric snap commits topology')
    reset();yield
    with ctx():bpy.ops.aludiy.select_endpoint(endpoint='END')
    mouse(*point('N-007'));yield;key('G');yield;key('Z');yield;yield from type_text('-199')
    check(g_move._ACTIVE._snap is None and abs(g_move._ACTIVE._delta.z+199)<1e-6,'numeric near miss is not rounded to endpoint')
    key('ESC');yield
    # Shared detach reattachment to a new target, in one operation.
    with ctx():
        p=frame();p.members['M-003'].end_node_id='N-001';del p.nodes['N-007']
        runtime.set_project(window.scene,p);scene_adapter.rebuild_scene(window.scene,p,runtime.get_catalog())
        scene_adapter.select_entity(window.scene,window.view_layer,'M-003');bpy.ops.aludiy.select_endpoint(endpoint='END')
        runtime.settings(window.scene).move_connection_mode='DETACH'
    yield;mouse(*point('N-001'));yield;key('G');yield;mouse(*point('N-005'));yield;key('RET');yield
    p=runtime.get_project(window.scene)
    check(source()=='N-005' and p.members['M-001'].start_node_id=='N-001','DETACH plus snap attaches only selected rod to a new node')
    # Whole-member anchor selection is near cursor, not node-ID ordering.
    reset();yield
    with ctx():scene_adapter.select_entity(window.scene,window.view_layer,'M-004')
    mouse(*point('N-006'));yield;key('G');yield
    check(g_move._ACTIVE._anchor_id=='N-006','whole move uses cursor-nearest selected endpoint')
    mouse(*point('N-002'));yield;key('RET');yield
    p=runtime.get_project(window.scene);m=p.members['M-004']
    check(m.end_node_id=='N-002' and abs(math.dist(p.nodes[m.start_node_id].position_mm,p.nodes[m.end_node_id].position_mm)-400)<1e-4,'whole rod keeps length and reconnects chosen anchor')
    # Invalid zero-length snap is surfaced and cannot be committed.
    reset();yield
    with ctx():bpy.ops.aludiy.select_endpoint(endpoint='END')
    before=raw();mouse(*point('N-007'));yield;key('G');yield;mouse(*point('N-004'));yield
    check(g_move._ACTIVE._error and g_move._ACTIVE._candidate is None,'collapsed rod snap is rejected during preview')
    key('RET');yield;check(raw()==before and g_move._ACTIVE is not None,'invalid snap Enter does not destroy project')
    key('ESC');yield
    # Axis lock rejects off-axis targets.
    mouse(*point('N-007'));yield;key('G');yield;key('Z');yield;mouse(*point('N-005'));yield
    check(g_move._ACTIVE._snap is None or g_move._ACTIVE._snap.node_id!='N-005','axis locking rejects off-axis endpoint')
    key('ESC');yield
    # Ground is a reference only. Use a floating foot, not a top that would collapse.
    with ctx():
        p=frame();p.nodes['N-004'].position_mm=(0,0,300)
        runtime.set_project(window.scene,p);scene_adapter.rebuild_scene(window.scene,p,runtime.get_catalog())
        scene_adapter.select_entity(window.scene,window.view_layer,'M-003');bpy.ops.aludiy.select_endpoint(endpoint='START')
        runtime.settings(window.scene).ground_elevation_input='100'
    yield;before=raw();mouse(*point('N-004'));yield;key('G');yield;key('Z');yield
    world_mouse((0,0,120));yield
    check(g_move._ACTIVE._snap is not None and g_move._ACTIVE._snap.kind=='GROUND','foot snaps to custom ground elevation')
    check(raw()==before,'ground preview leaves project unchanged')
    screenshot('05-ground-preview.png');key('RET');yield
    p=runtime.get_project(window.scene)
    check(p.nodes['N-004'].position_mm==(0,0,100) and len(p.nodes)==7,'ground positions foot without merging nodes')
    # Two distinct co-located targets must remain selectable.
    reset();yield
    with ctx():
        p=frame();p.add_node(Node('N-008',(0,0,800)))
        runtime.set_project(window.scene,p);scene_adapter.rebuild_scene(window.scene,p,runtime.get_catalog())
        scene_adapter.select_entity(window.scene,window.view_layer,'M-003');bpy.ops.aludiy.select_endpoint(endpoint='END')
    yield;mouse(*point('N-007'));yield;key('G');yield;mouse(*point('N-001'));yield
    first=g_move._ACTIVE._snap.node_id;key('TAB');yield
    check(g_move._ACTIVE._snap.node_id!=first and len(g_move._ACTIVE._snap_options)==2,'Tab cycles co-located candidates without edit mode')
    key('ESC');yield
    # Final file proves connectivity survives a new Blender process.
    reset();yield
    with ctx():bpy.ops.aludiy.select_endpoint(endpoint='END')
    mouse(*point('N-007'));yield;key('G');yield;mouse(*point('N-001'));yield;key('RET');yield
    expected=raw();(OUT/'expected.aludiy.json').write_text(expected)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'endpoint-demo.blend'))
    check(source()=='N-001','saved regression model has reconnected shared endpoint')
    (OUT/'report.json').write_text(json.dumps({'status':'passed','blender':bpy.app.version_string,'checks':checks},ensure_ascii=False,indent=2))
    print('ALUDIY_GUI_SNAP_OK',len(checks),flush=True)
    addon.unregister();bpy.ops.wm.quit_blender()

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
