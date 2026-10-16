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
    k={'-':'minus','+':'plus','.':'period','/':'slash','*':'asterisk','(':'parenleft',')':'parenright','@':'at','<':'less'}.get(k,k)
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
        k=unicode or {'RET':'Return','ESC':'Escape','ONE':'1','ZERO':'0','F6':'F6','F7':'F7','F8':'F8','TAB':'Tab','BACK_SPACE':'BackSpace'}.get(type,type.lower())
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
        key(char.upper(),char,shift=char in '+()*@<'); yield

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

from aludiy_designer import operators as ops

def frame():
    p=Project('P-DRAWING-SNAP','alpha-2026.10')
    entries=[('N-001',(0,0,0)),('N-002',(0,0,1000)),
             ('N-003',(0,0,1000)),('N-004',(1200,0,1000)),
             ('N-005',(900,350,1000)),('N-006',(1200,350,1000)),
             ('N-007',(1200,0,1000)),('N-008',(1200,0,1400))]
    for nid,xyz in entries:p.add_node(Node(nid,xyz))
    for mid,a,b in [('M-001','N-001','N-002'),('M-002','N-003','N-004'),('M-003','N-005','N-006')]:
        p.add_member(Member(mid,a,b,'generic:tslot-2020@0.1'))
    return p

def draw():
    check(ops._ACTIVE_DRAW is not None,'drawing operator is active')
    return ops._ACTIVE_DRAW

def run():
    global window,left,right,D
    D=X11.XOpenDisplay(None)
    addon.register();window=bpy.context.window;window.workspace.name=runtime.WORKSPACE_NAME
    for o in window.scene.objects:o.hide_set(True)
    a=next(a for a in window.screen.areas if a.type=='VIEW_3D')
    with bpy.context.temp_override(window=window,area=a,region=next(r for r in a.regions if r.type=='WINDOW')):
        bpy.ops.screen.area_split(direction='VERTICAL',factor=.52)
    yield
    left,right=sorted([a for a in window.screen.areas if a.type=='VIEW_3D'],key=lambda a:a.x)
    with ctx():view_sync.configure_dual_views(bpy.context)
    for a in (left,right):
        rv=a.spaces.active.region_3d
        rv.view_rotation=Euler((math.radians(68),0,math.radians(26))).to_quaternion()
        rv.view_location=(.6,.14,.7);rv.view_distance=3.1
        a.spaces.active.show_region_ui=a==right;a.spaces.active.show_gizmo=False
    km=bpy.context.window_manager.keyconfigs.addon.keymaps.new(name='3D View',space_type='VIEW_3D')
    shortcut=km.keymap_items.new('aludiy.draw_member','F8','PRESS')
    bpy.context.window_manager.keyconfigs.update()
    reset();select();yield
    ui=next(r for r in right.regions if r.type=='UI');ui.active_panel_category='AluDIY';yield
    # Native window F8 (test-only key), real mouse midpoint pick at Z=1000,
    # though fallback workplane is Z=0. Both view overlays see the same target.
    mouse(*pixel((600,0,1000)));yield;key('F8');yield
    mouse(cursor[0]+1,cursor[1]);yield
    op=draw();check(op._snap is not None and op._snap.kind=='MIDPOINT','first point snaps to member midpoint above fallback plane')
    check(op._snap.position_mm==(600,0,1000),'midpoint is exact engineering coordinate')
    before=raw();screenshot('01-midpoint-target.png');yield
    key('LEFTMOUSE');yield
    op=ops._ACTIVE_DRAW;check(op._start_mm==(600,0,1000),'click selects midpoint as drawing start')
    key('Z');yield;mouse(*pixel((600,0,1300)));yield
    yield from type_text('300')
    check(op._resolved_end()==(600,0,1300),'Z and typed length create exact 300mm vertical member')
    check(raw()==before,'unconfirmed line preview never changes engineering JSON')
    screenshot('02-midpoint-column-preview.png');yield
    key('RET');yield
    check(len(p().members)==4,'Enter adds one segment, not an overwritten project')
    new_mid=next(mid for mid in p().members if mid not in frame().members)
    new=p().members[new_mid]
    check(new.start_node_id not in frame().nodes and new.end_node_id not in frame().nodes,'new endpoints remain independent, even at snapped locations')
    check(not p().associations,'drawing does not create implicit associations')
    key('RIGHTMOUSE');yield
    check(ops._ACTIVE_DRAW is None,'right click ends the chain and removes active tool')
    check(window.scene.objects.get('_ALUDIY_MEMBER_PREVIEW') is None,'unfinished preview cache is removed')
    key('Z',ctrl=True);yield
    check(raw()==before,'one Ctrl+Z after finishing restores the original chain baseline')
    key('Z',ctrl=True,shift=True);yield
    check(len(p().members)==4,'redo restores independent drawing result')
    # Complete the intended design story, selecting host and new upright.
    select([new_mid,'M-002']);yield
    with ctx():res=bpy.ops.aludiy.create_associations()
    check(res=={'FINISHED'} and len(p().associations)==1,'manual multiselect association attaches newly drawn midpoint end')
    attach=next(iter(p().associations.values()))
    check(attach.host_member_id=='M-002' and abs(attach.station-.5)<1e-9,'host remains uninterrupted and attachment records midpoint')
    select(['M-002']);yield
    mouse(*pixel((400,0,1000)));yield;key('G');yield;key('Y');yield
    yield from type_text('100')
    key('RET');yield
    check(p().nodes[p().members[new_mid].start_node_id].position_mm==(600,100,1000),'after explicit association host movement drives the new upright end')
    screenshot('03-draw-associate-follow.png');yield
    # Preserve this illustrative result before independent event/selection tests.
    expected=raw(); (OUT/'example.aludiy.json').write_text(expected)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'drawing-demo.blend'))
    # Candidate cycling: two independent co-located endpoint IDs are selectable.
    reset();select();yield;mouse(*pixel((1200,0,1000)));yield;key('F8');yield
    mouse(cursor[0]+1,cursor[1]);yield
    op=draw();ids=[c.node_id for c in op._snap_options if c.kind=='NODE']
    check({'N-004','N-007'}.issubset(ids),'overlapping endpoints remain distinct candidate IDs')
    initial=op._snap.key;key('TAB');yield
    check(op._snap.key!=initial and bpy.context.mode=='OBJECT','Tab cycles targets instead of entering edit mode')
    key('TAB',shift=True);yield
    check(op._snap.key==initial,'Shift+Tab reverses target cycling')
    unchanged=raw();key('ESC');yield
    check(raw()==unchanged and ops._ACTIVE_DRAW is None,'cancel before first point leaves no nodes or active tool')
    # Perpendicular reference from start, Ctrl toggles without extra mouse motion.
    mouse(*pixel((900,350,1000)));yield;key('F8');yield;mouse(cursor[0]+1,cursor[1]);yield;key('LEFTMOUSE');yield
    mouse(*pixel((900,0,1000)));yield;op=draw()
    check(op._snap.kind=='PERPENDICULAR' and op._snap.position_mm==(900,0,1000),'drawing end snaps to mathematical foot on another member')
    screenshot('04-perpendicular-preview.png');yield
    _key('Control_L',True);X11.XFlush(D);yield
    check(op._free and op._display_snap is None,'Ctrl press immediately suppresses drawing snap marker')
    _key('Control_L',False);X11.XFlush(D);yield
    check(not op._free and op._snap.kind=='PERPENDICULAR','Ctrl release restores target without another mouse move')
    # A typed length is never rounded to the perpendicular foot 350 mm away.
    yield from type_text('349')
    check(abs(math.dist(op._start_mm,op._resolved_end())-349)<1e-9,'typed drawing length remains 349 rather than 350')
    check(op._display_snap is None,'no false snap marker on an unreached numeric target')
    key('BACK_SPACE');yield;key('BACK_SPACE');yield;key('BACK_SPACE');yield
    key('Z');yield
    check(op._snap is None and op._current_mm[:2]==op._start_mm[:2],'axis lock rejects off-axis nearby targets')
    key('Z');yield # release axis
    key('Z',shift=True);yield;mouse(*pixel((1200,0,1400)));yield
    check(op._plane_lock and abs(op._current_mm[2]-1000)<1e-6,'Shift+Z keeps every candidate or fallback in the start plane')
    key('ESC');yield
    # Source G and drawing both find the same free body target.
    mouse(*pixel((310,0,1000)));yield;key('F8');yield;mouse(cursor[0]+1,cursor[1]);yield
    op=draw();check(op._snap.kind=='AXIS' and op._snap.member_id=='M-002','drawing starts at arbitrary rod-body station, not only endpoints')
    captured=op._snap.position_mm; captured_pixel=cursor;key('ESC');yield
    with ctx():
        scene_adapter.select_entity(bpy.context.scene,bpy.context.view_layer,'M-003')
        bpy.ops.aludiy.select_endpoint(endpoint='START')
    yield;mouse(*pixel((900,350,1000)));yield;key('G');yield;mouse(*captured_pixel);yield
    check(g_move._ACTIVE._snap.member_id=='M-002' and g_move._ACTIVE._snap.kind=='AXIS','G uses the same rod-body target class')
    check(math.dist(g_move._ACTIVE._snap.position_mm,captured)<1e-5,'G and draw resolve identical position at same pointer')
    key('ESC');yield
    # Invalid numeric expression cannot silently commit the last valid preview.
    select();mouse(*pixel((600,0,1000)));yield;key('F8');yield;mouse(cursor[0]+1,cursor[1]);yield;key('LEFTMOUSE');yield
    mouse(*pixel((600,0,1200)));yield;key('Z');yield
    yield from type_text('1+')
    check(ops._ACTIVE_DRAW._typed=='1+','test keyboard sends the intended invalid expression')
    before=raw();key('RET');yield
    check(raw()==before and ops._ACTIVE_DRAW is not None,'invalid numeric entry cannot add a member')
    key('ESC');yield
    # View/sidebar clicks are not additional geometry operations.
    mouse(*pixel((500,0,1000)));yield;key('F8');yield
    mouse(right.x+right.width-70,right.y+right.height-200);yield;key('LEFTMOUSE');yield
    check(ops._ACTIVE_DRAW._start_mm is None,'other viewport/sidebar clicks cannot start a line')
    key('ESC');yield
    # Restore demonstration state, then validate in a separate Blender process.
    with ctx():
        restored=Project.from_dict(json.loads(expected))
        runtime.set_project(window.scene,restored);scene_adapter.rebuild_scene(window.scene,restored,runtime.get_catalog())
    (OUT/'expected.aludiy.json').write_text(expected)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'drawing-demo.blend'))
    (OUT/'report.json').write_text(json.dumps({'status':'passed','blender':bpy.app.version_string,'checks':checks},ensure_ascii=False,indent=2))
    print('DRAWING_SNAPPING_RUNTIME_OK',len(checks),flush=True)
    km.keymap_items.remove(shortcut);addon.unregister();bpy.ops.wm.quit_blender()

sequence=run()
def tick():
    try:next(sequence);return .4
    except StopIteration:return None
    except Exception:
        text=traceback.format_exc();print(text,flush=True)
        (OUT/'report.json').write_text(json.dumps({'status':'failed','checks':checks,'error':text},ensure_ascii=False,indent=2))
        try:screenshot('failure.png')
        except Exception:pass
        sys.stdout.flush();os._exit(1)
bpy.app.timers.register(tick,first_interval=1.0)
