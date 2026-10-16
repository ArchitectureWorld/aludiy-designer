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
    # Actual Shift clicking, not merely active-object changes.
    mouse(*pixel((0,0,250)));yield;key('LEFTMOUSE');yield
    mouse(*pixel((500,0,500)));yield
    _key('Shift_L',True);X11.XFlush(D);yield
    key('LEFTMOUSE');yield
    _key('Shift_L',False);X11.XFlush(D);yield
    with ctx():
        view_sync._sync_selection(window)
        mids,nids=g_move.selection_summary(bpy.context)
        check(mids=={'M-001','M-002'} and not nids,'Shift-click retains both selected members')
        check(sum(o.select_get() for o in window.scene.objects if o.get('aludiy_entity_id') in mids)==4,'line/solid aliases selected and counted once')
    screenshot('01-multiselection.png')
    # Draw two consecutive segments: same location, independent Node identities.
    with ctx():
        from types import SimpleNamespace
        op=SimpleNamespace(report=lambda *args: print("DRAW_REPORT",args))
        op._resolved_end=lambda: op._current_mm
        op._start_mm=(1500,0,0);op._current_mm=(1500,0,300);op._typed='';op._axis_lock=None;op._work_plane='XY';op._committed_count=0
        check(addon.operators.ALUDIY_OT_draw_member._commit(op,bpy.context),'draw first segment commits')
        op._current_mm=(1800,0,300)
        check(addon.operators.ALUDIY_OT_draw_member._commit(op,bpy.context),'draw second segment commits')
        newest=sorted(p().members)[-2:];m1,m2=[p().members[i] for i in newest]
        check(m1.end_node_id!=m2.start_node_id,'continuous drawing owns distinct coincident endpoints')
    reset();yield
    with ctx():bpy.ops.aludiy.select_endpoint(endpoint='START')
    mouse(*point('N-005'));yield;key('G');yield;key('X');yield;yield from type_text('100');key('RET');yield
    check(p().nodes['N-005'].position_mm==(100,0,1000),'independent endpoint moves without host')
    key('G');yield;key('X');yield;yield from type_text('-100');yield
    check(g_move._ACTIVE._snap is not None,'G locates coincident endpoint')
    check(not g_move.display_project(window.scene).associations,'snap preview never auto creates associations')
    key('RET');yield
    check(p().members['M-003'].start_node_id=='N-005' and len(p().nodes)==6,'confirmed snap preserves independent node IDs')
    # Float64 snap coordinates beyond float32 quantization at several metres.
    with ctx():
        q=frame();q.nodes['N-005'].position_mm=(2426.612345678,1096.789012345,-234.012345678)
        target=(2298.712312345,895.123412345,276.623412345)
        runtime.set_project(window.scene,q);scene_adapter.rebuild_scene(window.scene,q,runtime.get_catalog())
        scene_adapter.select_entity(window.scene,window.view_layer,'M-003');bpy.ops.aludiy.select_endpoint(endpoint='START')
        bpy.ops.aludiy.move_engineering(delta_json=json.dumps(exact_snap_delta(q.nodes['N-005'].position_mm,target)))
        check(math.dist(p().nodes['N-005'].position_mm,target)<1e-9,'float64 operator payload retains non-integer snap coordinates')
    reset();select(['M-001','M-002']);yield
    # Native key dispatch invokes the same create/remove commands as N panel.
    km=bpy.context.window_manager.keyconfigs.addon.keymaps.new(name='Object Mode',space_type='EMPTY')
    km.keymap_items.new('aludiy.create_associations','F6','PRESS');km.keymap_items.new('aludiy.remove_associations','F7','PRESS')
    bpy.context.window_manager.keyconfigs.update()
    mouse(left.x+220,left.y+340);yield;key('F6');yield
    check(len(p().associations)==1,'multi-selected members create one explicit body attachment')
    check(next(iter(p().associations.values())).kind=='ON_MEMBER','attachment is to uncut host axis')
    original=raw();screenshot('02-created-association.png')
    select(['M-001']);yield;key('G');yield;key('X');yield;yield from type_text('100');yield
    c=g_move.display_project(window.scene)
    check(c.nodes['N-003'].position_mm==(100,0,500),'host moves attached end in preview')
    check(c.nodes['N-004'].position_mm==(800,0,500),'unselected far endpoint remains fixed')
    check(raw()==original,'preview does not persist engineering state')
    screenshot('03-host-follow-preview.png');key('RET');yield
    check(p().nodes['N-003'].position_mm==(100,0,500),'confirm persists host attachment movement')
    key('Z',ctrl=True);yield;check(p().nodes['N-003'].position_mm==(0,0,500),'single undo restores geometry and association')
    key('Z',ctrl=True,shift=True);yield;check(p().nodes['N-003'].position_mm==(100,0,500),'redo restores host-driven geometry')
    select(['M-002']);yield;key('F7');yield
    check(not p().associations and p().nodes['N-003'].position_mm==(100,0,500),'unlink preserves position')
    key('G');yield;key('Z');yield;yield from type_text('100');key('RET');yield
    check(p().nodes['N-003'].position_mm==(100,0,600) and p().nodes['N-001'].position_mm==(100,0,0),'unlinked child moves independently')
    # Body snap along interior, no endpoint and no implicit relationship.
    reset();yield
    with ctx():bpy.ops.aludiy.select_endpoint(endpoint='START')
    mouse(*point('N-005'));yield;key('G');yield;mouse(*pixel((0,0,350)));yield
    check(g_move._ACTIVE._snap is not None and g_move._ACTIVE._snap.member_id=='M-001','mouse G snaps to interior host axis')
    check(not g_move.display_project(window.scene).associations,'body snap remains positioning only')
    screenshot('04-body-snap.png')
    _key('Control_L',True);X11.XFlush(D);yield
    check(g_move._ACTIVE._snap is None,'Ctrl temporarily disables body snapping')
    _key('Control_L',False);X11.XFlush(D);yield
    check(g_move._ACTIVE._snap is not None,'Ctrl release restores body snapping')
    original=raw();key('ESC');yield;check(raw()==original,'Esc restores body-snap preview without data change')
    select(nids=['N-002','N-005']);yield;key('F6');yield
    check(len(p().associations)==1,'multi-selected coincident nodes create an explicit relation')
    with ctx():
        scene_adapter.select_entity(window.scene,window.view_layer,'M-001');bpy.ops.aludiy.move_engineering(delta_mm=(100,0,0),delta_json='')
    check(p().nodes['N-005'].position_mm==(100,0,1000),'explicit node relation propagates position')
    # Persist associations and compare in a separate process after this exits.
    select(['M-001','M-003']);yield
    expected=raw();(OUT/'expected.aludiy.json').write_text(expected)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'manual-associations.blend'))
    screenshot('05-manual-associations.png')
    check(Project.from_dict(json.loads(expected)).to_dict()==p().to_dict(),'project JSON roundtrip preserves manual relationships')
    (OUT/'report.json').write_text(json.dumps({'status':'passed','blender':bpy.app.version_string,'checks':checks},ensure_ascii=False,indent=2))
    print('ALUDIY_MANUAL_GUI_OK',len(checks),flush=True)
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
