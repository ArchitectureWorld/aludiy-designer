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
from aludiy_designer.vendor.aludiy_core.profile_editing import interface_rails
P40='generic:tslot-2040@0.1'; P20='generic:tslot-2020@0.1'; SID='FACE_PV.S1'

def frame():
    p=Project('P-SLOT-EXPERIENCE','alpha-2026.10')
    for nid,pos in [('N-001',(0,0,0)),('N-002',(0,0,1000)),('N-003',(280,150,420)),('N-004',(650,150,420))]:
        p.add_node(Node(nid,pos))
    p.add_member(Member('M-001','N-001','N-002',P40));p.add_member(Member('M-002','N-003','N-004',P20))
    return p

def rail_point(sid=SID,t=.5):
    rail=next(r for r in interface_rails(p(),'M-001',runtime.get_catalog()) if r.interface_id==sid)
    return tuple(rail.start_mm[i]+t*(rail.end_mm[i]-rail.start_mm[i]) for i in range(3))

def run():
    global window,left,right,D
    D=X11.XOpenDisplay(None)
    addon.register();window=bpy.context.window;window.workspace.name=runtime.WORKSPACE_NAME
    for o in window.scene.objects:o.hide_set(True)
    area=next(a for a in window.screen.areas if a.type=='VIEW_3D')
    with bpy.context.temp_override(window=window,area=area,region=next(r for r in area.regions if r.type=='WINDOW')):
        bpy.ops.screen.area_split(direction='VERTICAL',factor=.52)
    yield
    left,right=sorted([a for a in window.screen.areas if a.type=='VIEW_3D'],key=lambda a:a.x)
    with ctx():view_sync.configure_dual_views(bpy.context)
    for a in (left,right):
        rv=a.spaces.active.region_3d;rv.view_rotation=Euler((math.radians(72),0,math.radians(25))).to_quaternion()
        rv.view_location=(.25,.04,.5);rv.view_distance=2.2
        a.spaces.active.show_region_ui=a==right;a.spaces.active.show_gizmo=False
    with ctx():
        runtime.set_project(window.scene,frame());scene_adapter.rebuild_scene(window.scene,frame(),runtime.get_catalog())
        s=runtime.settings(window.scene);s.solid_display_mode='PROFILE'
        bpy.ops.ed.undo_push(message='Slot baseline')
    select(['M-001']);yield
    ui=next(r for r in right.regions if r.type=='UI');ui.active_panel_category='AluDIY';yield
    check(hasattr(runtime.settings(window.scene),'slot_target_member_id'),'slot target fields registered')
    from aludiy_designer import slot_tools
    with ctx():
        before=raw();bpy.ops.aludiy.inspect_profile_slot(interface_id=SID)
        check(bpy.ops.aludiy.set_slot_target()=={'FINISHED'},'pin inspected slot target')
        check(raw()==before,'target selection is non-geometric and creates no association')
        check(slot_tools.target_spec(window.scene,p())==('M-001',SID),'target uses member and stable slot ID')
    select(['M-002']);yield
    with ctx():g_move._select_endpoint(bpy.context,'M-002','START')
    yield
    check(slot_tools.target_spec(window.scene,p())==('M-001',SID),'target persists after choosing another member endpoint')
    mouse(*point('N-003'));yield;key('G');yield;mouse(*pixel(rail_point()));yield
    check(g_move._ACTIVE and g_move._ACTIVE._snap is not None,'G finds pinned slot candidate')
    check(g_move._ACTIVE._snap.interface_id==SID,'G does not confuse parallel lanes')
    check(math.dist(g_move._ACTIVE._candidate.project.nodes['N-003'].position_mm,rail_point())<1e-7,'slot preview lies on rail not host axis')
    screenshot('01-slot-target-preview.png');yield
    _key('Control_L',True);X11.XFlush(D);yield
    check(g_move._ACTIVE._free and g_move._ACTIVE._snap is None,'Ctrl disables slot snap without moving mouse')
    _key('Control_L',False);X11.XFlush(D);yield
    check(g_move._ACTIVE._snap.interface_id==SID,'release Ctrl restores same slot target')
    key('ESC');yield;check(raw()==before,'cancel leaves original geometry and relations intact')
    mouse(*point('N-003'));yield;key('G');yield;mouse(*pixel(rail_point()));yield;key('LEFTMOUSE');yield
    check(g_move._ACTIVE is None and math.dist(p().nodes['N-003'].position_mm,rail_point())<1e-7,'confirm commits exact slot position')
    check(not p().associations,'G snapping never creates association')
    km=bpy.context.window_manager.keyconfigs.addon.keymaps.new(name='Object Mode',space_type='EMPTY')
    km.keymap_items.new('aludiy.create_associations','F6','PRESS')
    k=km.keymap_items.new('aludiy.edit_selected_profiles','F7','PRESS');k.properties.action='ROTATE';k.properties.angle='90'
    km.keymap_items.new('aludiy.draw_member','F8','PRESS')
    bpy.context.window_manager.keyconfigs.update()
    select(['M-001','M-002']);yield;before_link=raw();mouse(left.x+200,left.y+320);yield;key('F6');yield
    check(len(p().associations)==1 and next(iter(p().associations.values())).kind=='ON_SLOT','multiselect Create Association creates explicit ON_SLOT')
    check(p().schema_version=='0.3.0','new slot relation explicitly upgrades schema')
    with ctx():check(g_move.selection_summary(bpy.context)[0]=={'M-001','M-002'},'association retains entire selected member set')
    key('Z',ctrl=True);yield;check(raw()==before_link,'one Undo restores pre-association position-only project')
    key('Z',ctrl=True,shift=True);yield;check(len(p().associations)==1,'Redo restores slot relation')
    select(['M-001']);yield;old=p().to_dict();mouse(*point('N-001'));yield;key('G');yield;key('X');yield
    yield from type_text('100');key('RET');yield
    check(p().nodes['N-003'].position_mm==tuple(old['nodes'][2]['position_mm'][i]+(100,0,0)[i] for i in range(3)),'native G host translation propagates attached end')
    check(p().nodes['N-004'].position_mm==tuple(old['nodes'][3]['position_mm']),'unattached far end remains fixed')
    key('F7');yield
    check(p().members['M-001'].roll_deg==90,'native key dispatch rotates host section')
    check(math.dist(p().nodes['N-003'].position_mm,rail_point())<1e-7,'roll recomputes attached endpoint from stable interface')
    screenshot('02-slot-attachment-follow.png');yield
    key('Z',ctrl=True);yield;check(p().members['M-001'].roll_deg==0 and math.dist(p().nodes['N-003'].position_mm,rail_point())<1e-7,'Undo roll restores endpoint and section as one transaction')
    key('Z',ctrl=True,shift=True);yield
    with ctx():
        original=raw();s=runtime.settings(window.scene);s.edit_profile_id=P20
        result=bpy.ops.aludiy.edit_selected_profiles(action='PROFILE')
        check(result=={'CANCELLED'} and raw()==original,'changing attached host profile is blocked atomically')
        from unittest.mock import patch
        real=scene_adapter.rebuild_scene;calls=[0]
        def fail_once(*args,**kw):
            calls[0]+=1
            if calls[0]==1:raise RuntimeError('injected slot rebuild failure')
            return real(*args,**kw)
        with patch.object(scene_adapter,'rebuild_scene',side_effect=fail_once):
            result=bpy.ops.aludiy.edit_selected_profiles(action='ROTATE',angle='90')
        check(result=={'CANCELLED'} and raw()==original,'failed propagation cache build rolls back all geometry and links')
        bpy.ops.aludiy.clear_slot_target()
        check(raw()==original and slot_tools.target_spec(window.scene,p()) is None,'clearing target does not remove engineering relations')
    select(['M-002']);yield
    with ctx():
        before_unlink=p().to_dict();bpy.ops.aludiy.remove_associations()
        check(not p().associations and p().to_dict()['nodes']==before_unlink['nodes'],'manual unlink preserves exact geometry')
    mouse(*point('N-003'));yield;key('G');yield;key('Y');yield;yield from type_text('100');key('RET');yield
    check(p().nodes['N-003'].position_mm[1]==before_unlink['nodes'][2]['position_mm'][1]+100,'unlinked member moves freely')
    select(['M-001']);yield
    with ctx():
        bpy.ops.aludiy.inspect_profile_slot(interface_id='FACE_PV.S0');bpy.ops.aludiy.set_slot_target()
        check(slot_tools.target_spec(window.scene,p())==('M-001','FACE_PV.S0'),'pin other lane as an independent target')
    # Directly draw on an elevated, rolled slot; G and drawing use same pipeline.
    start=rail_point('FACE_PV.S0');mouse(*pixel(start));yield;key('F8');yield;mouse(cursor[0]+1,cursor[1]);yield
    check(ops._ACTIVE_DRAW and ops._ACTIVE_DRAW._snap and ops._ACTIVE_DRAW._snap.interface_id=='FACE_PV.S0','drawing uses selected slot not center axis')
    key('LEFTMOUSE');yield;key('X');yield;mouse(*pixel((start[0]+300,start[1],start[2])));yield
    yield from type_text('300');key('RET');yield;key('RIGHTMOUSE');yield
    new=next(m for m in p().members.values() if m.id not in frame().members)
    check(math.dist(p().nodes[new.start_node_id].position_mm,start)<1e-7,'drawn member starts at exact elevated slot position')
    check(abs(math.dist(p().nodes[new.start_node_id].position_mm,p().nodes[new.end_node_id].position_mm)-300)<1e-7,'numeric drawing length and axis lock preserved')
    check(not p().associations,'slot drawing does not bind automatically')
    select(['M-001',new.id]);yield;mouse(left.x+200,left.y+320);yield;key('F6');yield
    check(any(r.slot_reference and r.slot_reference.interface_id=='FACE_PV.S0' for r in p().associations.values()),'draw then explicitly associate to chosen lane')
    select([new.id]);yield
    with ctx():
        runtime.settings(window.scene).solid_display_mode='BOX'
        check(g_move.selection_summary(bpy.context)[0]=={new.id},'BOX rebuild retains selection with slot relation')
        runtime.settings(window.scene).solid_display_mode='PROFILE'
    expected=raw();(OUT/'expected.aludiy.json').write_text(expected)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'slot-attachment.blend'))
    check(Project.from_dict(json.loads(expected)).to_dict()==p().to_dict(),'JSON roundtrip preserves slot reference identity and coordinates')
    screenshot('03-final-slot-assembly.png');yield
    (OUT/'report.json').write_text(json.dumps({'status':'passed','blender':bpy.app.version_string,'checks':checks},ensure_ascii=False,indent=2))
    print('SLOT_ATTACHMENT_GUI_OK',len(checks),flush=True)
    addon.unregister();bpy.ops.wm.quit_blender()

sequence=run()
def tick():
    try:next(sequence);return .28
    except StopIteration:return None
    except Exception:
        text=traceback.format_exc();print(text,flush=True)
        (OUT/'report.json').write_text(json.dumps({'status':'failed','checks':checks,'error':text},ensure_ascii=False,indent=2))
        try:screenshot('failure.png')
        except Exception:pass
        sys.stdout.flush();os._exit(1)
bpy.app.timers.register(tick,first_interval=1.0)
