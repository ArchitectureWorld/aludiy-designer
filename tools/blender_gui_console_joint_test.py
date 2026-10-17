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

from aludiy_designer import profile_tools as pt,slot_tools,joint_tools,panels
from aludiy_designer.vendor.aludiy_core.associations import create_slot_associations
from aludiy_designer.vendor.aludiy_core.joints import solve_cutbacks
from aludiy_designer.vendor.aludiy_core.movement import preview_move

def model(slot=True, other=False, corner=False):
    q=Project('P-CONSOLE-JOINT','alpha-2026.10')
    for n,xyz in [('N-001',(0,0,0)),('N-002',(0,0,1000)),
                  ('N-003',(20 if slot else 0,0,500)),('N-004',(500,0,500))]:q.add_node(Node(n,xyz))
    q.add_member(Member('M-001','N-001','N-002',P40));q.add_member(Member('M-002','N-003','N-004',P20))
    if other:
        q.add_node(Node('N-005',(-20,0,300)));q.add_node(Node('N-006',(-500,0,300)))
        q.add_member(Member('M-003','N-005','N-006',P20))
        q=create_slot_associations(q,runtime.get_catalog(),host_member_id='M-001',interface_id='FACE_NU.S0',member_ids=['M-003']).project
    if corner:
        q.add_node(Node('N-007',(0,0,1000)));q.add_node(Node('N-008',(500,0,1000)))
        q.add_member(Member('M-004','N-007','N-008',P20))
    return q

def install(q):
    with ctx():
        runtime.set_project(window.scene,q);scene_adapter.rebuild_scene(window.scene,q,runtime.get_catalog())
        window.view_layer.update();slot_tools.clear_target(window.scene);pt.clear_slot(window.scene)
        select(['M-001']);bpy.ops.ed.undo_push(message='Case baseline')

def active(mid):
    window.view_layer.objects.active=next(o for o in window.scene.objects if o.get('aludiy_entity_id')==mid and o.get('aludiy_entity_type')=='MEMBER_AXIS')

def view(a):
    with ctx(a):return pt.inspector_layout(bpy.context)

def at(a,xy):
    reg=next(r for r in a.regions if r.type=='WINDOW');mouse(reg.x+xy[0],reg.y+xy[1])

def action(name,a=None):
    area=a or left;at(area,getattr(view(area).layout,name).center)

def safe_mouse():mouse(left.x+140,left.y+200)

def run():
    global D,window,left,right
    D=X11.XOpenDisplay(None);addon.register();bpy.context.window_manager.keyconfigs.update();window=bpy.context.window
    factor=float(os.environ.get('ALUDIY_TEST_UI_SCALE','1'))
    bpy.context.preferences.view.ui_scale=factor;yield;yield
    window.workspace.name=runtime.WORKSPACE_NAME
    for o in window.scene.objects:o.select_set(False);o.hide_set(True)
    a=next(a for a in window.screen.areas if a.type=='VIEW_3D')
    with bpy.context.temp_override(window=window,area=a,region=next(r for r in a.regions if r.type=='WINDOW')):
        bpy.ops.screen.area_split(direction='VERTICAL',factor=.52)
    yield
    left,right=sorted([a for a in window.screen.areas if a.type=='VIEW_3D'],key=lambda a:a.x)
    with ctx():view_sync.configure_dual_views(bpy.context)
    for a in (left,right):
        a.spaces.active.region_3d.view_rotation=Euler((math.radians(72),0,math.radians(22))).to_quaternion()
        a.spaces.active.region_3d.view_location=(.25,0,.5);a.spaces.active.region_3d.view_distance=3.8
        a.spaces.active.show_region_ui=a==right;a.spaces.active.show_gizmo=False
    install(model(other=True));yield
    next(r for r in right.regions if r.type=='UI').active_panel_category='AluDIY';yield
    # Pin, create and stop using real inset clicks; no automatic data association.
    slot=next(s for s in view(left).layout.slots if s.interface_id=='FACE_PU.S0')
    at(left,slot.center);yield
    key('LEFTMOUSE');yield;yield
    check(runtime.settings(window.scene).inspected_interface_id=='FACE_PU.S0','console slot picked by real mouse')
    # Review regressions: callbacks cannot bypass selection or service lifetime.
    with ctx():
        ordinary=bpy.data.objects.new('Ordinary-selection-guard',None)
        window.scene.collection.objects.link(ordinary);ordinary.select_set(True)
        active('M-001')
        snapshot={o.name for o in bpy.context.selected_objects};before_guard=raw()
        from types import SimpleNamespace
        reg=next(r for r in left.regions if r.type=='WINDOW')
        xy=view(left).layout.create_rect.center
        event=SimpleNamespace(mouse_x=reg.x+xy[0],mouse_y=reg.y+xy[1])
        check(pt.handle_inspector_click(bpy.context,event),'mixed ordinary-object click is consumed without escaping an exception')
        check({o.name for o in bpy.context.selected_objects}==snapshot and raw()==before_guard,'rejected inset data action preserves ordinary objects and graph')
        check(not pt._PENDING_ACTIONS,'invalid mixed selection queues no mutation')
        ordinary.select_set(False);bpy.data.objects.remove(ordinary,do_unlink=True)
        select(['M-001']);active('M-001')
        pt.queue_data_action(bpy.context,'CREATE',view(left))
        select(['M-002'])
    yield
    check(raw()==before_guard and not pt._PENDING_ACTIONS,'changed selection cancels deferred action rather than acting on stale input')
    with ctx():
        select(['M-001']);active('M-001')
        pt.queue_data_action(bpy.context,'CREATE',view(left))
        callbacks=tuple(pt._PENDING_ACTIONS.values());pt._clear_pointer_on_load(None)
        check(not pt._PENDING_ACTIONS and not any(bpy.app.timers.is_registered(f) for f in callbacks),'file-load reset removes pending data callbacks')
        pt.queue_data_action(bpy.context,'CREATE',view(left))
        callbacks=tuple(pt._PENDING_ACTIONS.values());pt.unregister_services()
        check(not pt._PENDING_ACTIONS and not any(bpy.app.timers.is_registered(f) for f in callbacks),'service disable removes pending mutation callbacks')
        pt.register_services()
    if os.environ.get('ALUDIY_CONSOLE_ONLY_SAFETY'):
        (OUT/'report.json').write_text(json.dumps({'status':'passed','checks':checks,'blender':bpy.app.version_string,'ui_scale':factor},ensure_ascii=False,indent=2))
        print('CONSOLE_SAFETY_OK',len(checks),flush=True);addon.unregister();bpy.ops.wm.quit_blender();return
    yield
    action('pin_rect');yield;key('LEFTMOUSE');yield
    check(slot_tools.target_spec(window.scene,p())==('M-001','FACE_PU.S0'),'console pins target')
    select(['M-002']);yield;before_nodes=p().to_dict()['nodes'];action('create_rect');yield;key('LEFTMOUSE');yield
    check(len(p().associations)==2,'console Create makes actual ON_SLOT while keeping other slot')
    check(p().to_dict()['nodes']==before_nodes,'association creation does not teleport or change coordinates')
    safe_mouse();yield;key('Z',ctrl=True);yield
    check(len(p().associations)==1,'one Undo reverses console Create and preserves other slot')
    key('Z',ctrl=True,shift=True);yield
    check(len(p().associations)==2,'one Redo restores console Create')
    before=raw();action('clear_rect');yield;key('LEFTMOUSE');yield
    check(not runtime.settings(window.scene).slot_target_member_id and raw()==before,'Stop positioning preserves associations by explicit contract')
    check('仍有 1 处' in runtime.settings(window.scene).status_message,'stop action tells user actual remaining link count')
    select(['M-001']);yield;at(left,next(s.center for s in view(left).layout.slots if s.interface_id=='FACE_PU.S0'));yield;key('LEFTMOUSE');yield
    check(len(slot_tools.slot_links(p(),'M-001','FACE_PU.S0'))==1,'existing slot association remains inspectable without pinned target')
    action('unlink_slot_rect');yield;key('LEFTMOUSE');yield;key('ESC');yield
    check(raw()==before,'cancel exact-slot unlink confirmation changes no engineering data')
    action('unlink_slot_rect');yield;key('LEFTMOUSE');yield;key('RET');yield;yield
    check(len(p().associations)==1 and not slot_tools.slot_links(p(),'M-001','FACE_PU.S0'),'exact-slot unlink removes authoritative edge, not just overlay')
    check(len(slot_tools.slot_links(p(),'M-001','FACE_NU.S0'))==1,'other slot remains constrained')
    check(p().to_dict()['nodes']==before_nodes,'exact-slot unlink preserves all node positions')
    safe_mouse();yield;key('Z',ctrl=True);yield
    check(len(p().associations)==2,'one native Undo restores removed slot edge')
    key('Z',ctrl=True,shift=True);yield
    check(len(p().associations)==1,'one native Redo removes the edge again')
    select(['M-002']);yield
    with ctx():bpy.ops.aludiy.select_endpoint(owner_id='M-002',endpoint='START')
    yield;safe_mouse();yield;key('G');yield;key('X');yield;yield from type_text('100')
    check(g_move._ACTIVE is not None and g_move._ACTIVE._candidate is not None,'unlinked endpoint G now has a valid candidate')
    check(not g_move._ACTIVE._error,'no residual host constraint warning after true unlink')
    key('RET');yield
    check(abs(p().nodes['N-003'].position_mm[0]-120)<1e-6,'real G X 100 moves released endpoint immediately')
    key('Z',ctrl=True);yield
    check(p().nodes['N-003'].position_mm[0]==20 and len(p().associations)==1,'Undo movement preserves unlink and other-slot relation')
    (OUT/'released.aludiy.json').write_text(raw())
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'released.blend'))
    # Selected-end unlink is also in the console and does not require selecting host.
    select(['M-003']);yield
    with ctx():bpy.ops.aludiy.select_endpoint(owner_id='M-003',endpoint='START')
    yield;action('unlink_rect');yield;key('LEFTMOUSE');yield
    check(not p().associations,'console Unlink selected operates on owned follower endpoint')
    with ctx():check(g_move.endpoint_context(bpy.context)==('M-003','START'),'unlink retains owned-end selection')
    safe_mouse();yield;key('G');yield;key('X');yield;yield from type_text('-30');key('RET');yield
    check(abs(p().nodes['N-005'].position_mm[0]+50)<1e-6,'second released follower is independently movable')
    # Snapshot a linked console with the actual IDs/count, not an illustrative UI.
    install(model(other=True));yield
    select(['M-001']);yield
    with ctx():bpy.ops.aludiy.inspect_profile_slot(interface_id='FACE_NU.S0')
    screenshot('01-slot-console.png');yield
    # First processing slice: explicit T and L square-cut rules, not associations.
    install(model(slot=False,corner=True));yield
    select(['M-001','M-002']);active('M-001');yield
    with ctx():
        runtime.settings(window.scene).solid_display_mode='PROFILE'
        runtime.settings(window.scene).joint_gap_input='2'
        check(bpy.ops.aludiy.set_butt_joint('EXEC_DEFAULT',True)=={'FINISHED'},'T processing operator succeeds with explicit host selection')
    yield
    sol=solve_cutbacks(p(),runtime.get_catalog(),strict=True)
    check(sol.kinds=={'J-001':'T'} and sol.lengths['M-002'].cut_length_mm==478,'T automatically trims 20 mm plus 2 mm gap')
    check(p().nodes['N-003'].position_mm==(0,0,500) and not p().associations,'processing changes no design node and creates no position link')
    with ctx():check(panels.selection_info(bpy.context)['member_ids']==('M-001','M-002'),'processing retains full multiselection')
    body=next(o for o in window.scene.objects if o.get('aludiy_entity_id')=='M-002' and o.get('aludiy_entity_type')=='MEMBER_SOLID')
    check(abs(min(v.co.x for v in body.data.vertices)-.022)<1e-6,'real detailed mesh end is generated at the cutback plane')
    with ctx():runtime.settings(window.scene).joint_gap_input='0';bpy.ops.aludiy.set_butt_joint('EXEC_DEFAULT',True)
    yield;check(len(p().joints)==1 and solve_cutbacks(p(),runtime.get_catalog()).lengths['M-002'].cut_length_mm==480,'editing gap updates rule once without duplicate trim')
    select(['M-001','M-004']);active('M-001');yield
    with ctx():bpy.ops.aludiy.set_butt_joint('EXEC_DEFAULT',True)
    yield;sol=solve_cutbacks(p(),runtime.get_catalog(),strict=True)
    check(sol.kinds=={'J-001':'T','J-002':'L'},'endpoint intersection classified as L; interior as T')
    check(sol.lengths['M-001'].cut_length_mm==1010 and sol.lengths['M-004'].cut_length_mm==480,'L extends host by branch half-section and trims branch')
    select(['M-001']);yield
    with ctx():bpy.ops.aludiy.edit_selected_profiles('EXEC_DEFAULT',True,action='ROTATE',angle='90')
    yield;check(solve_cutbacks(p(),runtime.get_catalog()).lengths['M-002'].cut_length_mm==490,'host section rotation recalculates derived setback')
    safe_mouse();yield;key('Z',ctrl=True);yield
    check(solve_cutbacks(p(),runtime.get_catalog()).lengths['M-002'].cut_length_mm==480,'Undo rotation restores body lengths with rule identity')
    select(['M-002']);yield
    with ctx():bpy.ops.aludiy.select_endpoint(owner_id='M-002',endpoint='START')
    yield;safe_mouse();yield;key('G');yield;key('Z');yield;yield from type_text('100')
    check(g_move._ACTIVE._candidate is not None and not g_move._ACTIVE._error,'processing rules do not trap an unlinked endpoint')
    key('RET');yield
    sol=solve_cutbacks(p(),runtime.get_catalog());check(bool(sol.issues),'invalidated oblique joint becomes visible pending processing state')
    check(sol.lengths['M-001'].cut_length_mm is None,'pending processing does not expose a fake cut length')
    with ctx():
        try:result=bpy.ops.aludiy.export_cutlist(filepath=str(OUT/'invalid.csv'))
        except RuntimeError:result={'CANCELLED'}
    check(result=={'CANCELLED'} and not (OUT/'invalid.csv').exists(),'invalid processing cannot export a cut-list')
    safe_mouse();yield;key('Z',ctrl=True);yield
    check(not solve_cutbacks(p(),runtime.get_catalog()).issues,'Undo independent move restores valid processing')
    select(['M-001']);yield
    with ctx():bpy.ops.aludiy.export_cutlist(filepath=str(OUT/'valid.csv'))
    import csv
    with (OUT/'valid.csv').open(encoding='utf-8-sig') as f:rows={r['member_id']:r for r in csv.DictReader(f)}
    check(rows['M-002']['system_length_mm']=='500.000' and rows['M-002']['cut_length_mm']=='480.000','CSV separates design and square-cut reference lengths')
    with ctx():bpy.ops.aludiy.remove_joints('EXEC_DEFAULT',True)
    yield;check(not p().joints and p().nodes['N-003'].position_mm==(0,0,500),'clearing processing rules leaves design geometry intact')
    safe_mouse();yield;key('Z',ctrl=True);yield
    check(len(p().joints)==2,'one Undo restores both processing rules')
    select(['M-001','M-002']);active('M-001');yield
    with ctx():runtime.settings(window.scene).show_selection_lengths=True
    for a in (left,right):
        a.spaces.active.region_3d.view_distance=1.75
        a.spaces.active.region_3d.view_location=(.20,0,.65)
    yield;yield
    screenshot('02-L-T-cutbacks.png');yield
    expected=raw();(OUT/'expected.aludiy.json').write_text(expected)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'console-joints.blend'))
    check(p().schema_version=='0.4.0','processing saved with explicitly upgraded schema')
    addon.unregister();addon.register();yield
    check(runtime.get_project(window.scene).to_dict()==json.loads(expected),'disable/re-enable preserves processing and source data')
    (OUT/'report.json').write_text(json.dumps({'status':'passed','checks':checks,'blender':bpy.app.version_string,'ui_scale':factor},ensure_ascii=False,indent=2))
    print('CONSOLE_JOINT_GUI_OK',len(checks),flush=True);addon.unregister();bpy.ops.wm.quit_blender()

sequence=run()
def tick():
    try:next(sequence);return .30
    except StopIteration:return None
    except Exception:
        text=traceback.format_exc();print(text,flush=True)
        (OUT/'report.json').write_text(json.dumps({'status':'failed','checks':checks,'error':text},ensure_ascii=False,indent=2))
        try:screenshot('failure.png')
        except Exception:pass
        sys.stdout.flush();os._exit(1)
bpy.app.timers.register(tick,first_interval=1.0)
