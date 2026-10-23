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


def multi_model():
    q=Project('P-MULTI-SLOT-EXPERIENCE','alpha-2026.10')
    coords=[(0,0,0),(0,0,1000),(800,0,0),(800,0,1000),
        (200,0,500),(520,0,500),(1000,0,650),(1320,0,650),
        (300,650,200),(650,650,200),(-20,0,300),(-400,0,300)]
    for i,xyz in enumerate(coords,1):q.add_node(Node(f'N-{i:03}',xyz))
    for i,(a,b,prof) in enumerate([(1,2,P40),(3,4,P40),(5,6,P20),(7,8,P20),(9,10,P20),(11,12,P20)],1):
        q.add_member(Member(f'M-{i:03}',f'N-{a:03}',f'N-{b:03}',prof))
    return create_slot_associations(q,runtime.get_catalog(),host_member_id='M-001',interface_id='FACE_NU.S0',node_ids=['N-011']).project

def rail_xyz(mid,sid,t=.5):
    r=next(r for r in interface_rails(p(),mid,runtime.get_catalog()) if r.interface_id==sid)
    return tuple(a+t*(b-a) for a,b in zip(r.start_mm,r.end_mm))

def choose(mid,sid,extend=False):
    with ctx():
        select([mid]);active(mid)
        assert bpy.ops.aludiy.inspect_profile_slot(interface_id=sid,extend=extend)=={'FINISHED'}

def slot_pixel(mid,sid):
    # Caller has already made this member active; geometry is region-local.
    return next(slot.center for slot in view(left).layout.slots if slot.interface_id==sid)

def shift_click():
    # Hold a real modifier across event-loop turns; do not release it in the
    # same timer callback before Blender has processed the mouse press.
    _key('Shift_L',True);X11.XFlush(D);yield
    key('LEFTMOUSE');yield
    _key('Shift_L',False);X11.XFlush(D);yield


def restore_choices():
    choose('M-001','FACE_PU.S0')
    choose('M-001','FACE_PV.S0',True)
    choose('M-002','FACE_PU.S0',True)
    with ctx():bpy.ops.aludiy.set_slot_target()


def run():
    global D,window,left,right
    D=X11.XOpenDisplay(None);addon.register();bpy.context.window_manager.keyconfigs.update();window=bpy.context.window
    factor=float(os.environ.get('ALUDIY_TEST_UI_SCALE','1'))
    bpy.context.preferences.view.ui_scale=factor;yield;yield
    window.workspace.name=runtime.WORKSPACE_NAME
    for obj in window.scene.objects:obj.select_set(False);obj.hide_set(True)
    a=next(a for a in window.screen.areas if a.type=='VIEW_3D')
    with bpy.context.temp_override(window=window,area=a,region=next(r for r in a.regions if r.type=='WINDOW')):
        bpy.ops.screen.area_split(direction='VERTICAL',factor=.52)
    yield
    left,right=sorted([a for a in window.screen.areas if a.type=='VIEW_3D'],key=lambda a:a.x)
    with ctx():view_sync.configure_dual_views(bpy.context)
    for area in (left,right):
        rv=area.spaces.active.region_3d;rv.view_rotation=Euler((math.radians(72),0,math.radians(22))).to_quaternion()
        rv.view_location=(.5,.2,.5);rv.view_distance=4.8
        area.spaces.active.show_region_ui=area==right;area.spaces.active.show_gizmo=False
    with ctx():
        runtime.set_project(window.scene,multi_model());scene_adapter.rebuild_scene(window.scene,p(),runtime.get_catalog())
        slot_tools.clear_selection(window.scene);pt.clear_slot(window.scene)
        runtime.settings(window.scene).solid_display_mode='PROFILE'
        select(['M-001']);active('M-001');bpy.ops.ed.undo_push(message='multi-slot baseline')
    yield
    # Keep test geometry in an unobstructed lower model area at either UI scale.
    # Points covered by the section console must NOT receive model input.
    reg=next(r for r in left.regions if r.type=='WINDOW')
    anchor=Vector((.65,.25,.5))
    under=view3d_utils.region_2d_to_location_3d(reg,left.spaces.active.region_3d,
                                             (reg.width*.30,reg.height*.24),anchor)
    shift=anchor-under
    for area in (left,right):area.spaces.active.region_3d.view_location+=shift
    yield
    next(r for r in right.regions if r.type=='UI').active_panel_category='AluDIY'
    s=runtime.settings(window.scene);initial=raw()
    at(left,slot_pixel('M-001','FACE_PU.S0'));yield;key('LEFTMOUSE');yield
    check(slot_tools.choice_pairs(window.scene)==(('M-001','FACE_PU.S0'),),'plain native click selects exactly one stable rail')
    check(not slot_tools.target_specs(window.scene,p()) and raw()==initial,'choosing a slot neither activates target nor modifies graph')
    with ctx():check(g_move.selection_summary(bpy.context)[0]=={'M-001'},'inset click preserves model selection')
    at(left,slot_pixel('M-001','FACE_PV.S0'));yield;yield from shift_click()
    at(left,slot_pixel('M-001','FACE_PV.S1'));yield;yield from shift_click()
    check({('M-001','FACE_PV.S0'),('M-001','FACE_PV.S1')} <= set(slot_tools.choice_pairs(window.scene)),
          'native Shift selects both parallel lanes on one wide face')
    yield from shift_click()
    check(len(slot_tools.choice_pairs(window.scene))==2,'Shift click adds second rail on same member')
    at(left,slot_pixel('M-001','FACE_PU.S0'));yield;yield from shift_click()
    check(slot_tools.choice_pairs(window.scene)==(('M-001','FACE_PV.S0'),),'Shift clicking selected rail toggles only that rail off')
    yield from shift_click()
    with ctx():select(['M-002']);active('M-002')
    yield;at(left,slot_pixel('M-002','FACE_PU.S0'));yield;yield from shift_click()
    expected=(('M-001','FACE_PU.S0'),('M-001','FACE_PV.S0'),('M-002','FACE_PU.S0'))
    check(slot_tools.choice_pairs(window.scene)==expected,'Shift adds rail on another host without losing prior member choices')
    action('pin_rect');yield;key('LEFTMOUSE');yield
    check(slot_tools.target_specs(window.scene,p())==expected,'Use for snapping activates all three chosen rails')
    check(not s.slot_only and raw()==initial,'ordinary plus rails is default and pinning leaves project unchanged')
    at(left,slot_pixel('M-002','FACE_NU.S0'));yield;key('LEFTMOUSE');yield
    check(slot_tools.choice_pairs(window.scene)==(('M-002','FACE_NU.S0'),),'plain click replaces selection set')
    check(slot_tools.target_specs(window.scene,p())==expected,'inspecting another slot does not silently replace activated set')
    restore_choices();yield
    action('mode_rect');yield;key('LEFTMOUSE');yield
    check(s.slot_only,'explicit click enables restricted rail-only mode')
    action('mode_rect');yield;key('LEFTMOUSE');yield
    check(not s.slot_only,'explicit click returns mixed mode')
    # Real G to an unrelated ordinary endpoint with three active rails.
    with ctx():select(['M-003']);active('M-003');g_move._select_endpoint(bpy.context,'M-003','START')
    yield;mouse(*point('N-005'));yield;key('G');yield;mouse(*point('N-009'));yield
    check(g_move._ACTIVE is not None and g_move._ACTIVE._snap and g_move._ACTIVE._snap.node_id=='N-009','G snaps to unrelated ordinary endpoint while rails stay active')
    check(len(slot_tools.target_specs(window.scene,p()))==3,'ordinary target does not stop or replace activated rails')
    _key('Control_L',True);X11.XFlush(D);yield
    check(g_move._ACTIVE._free and g_move._ACTIVE._snap is None,'Ctrl suppresses all snap families')
    _key('Control_L',False);X11.XFlush(D);yield
    check(g_move._ACTIVE._snap and g_move._ACTIVE._snap.node_id=='N-009','release Ctrl restores ordinary candidate in mixed mode')
    key('ESC');yield;check(raw()==initial,'cancelling mixed-snapped move leaves all data intact')
    # Restricted mode is an explicit opt-in and can be stopped without unlinking.
    s.slot_only=True;mouse(*point('N-005'));yield;key('G');yield;mouse(*point('N-009'));yield
    check(g_move._ACTIVE is not None and all(c.kind=='SLOT' for c in g_move._ACTIVE._snap_options),'restricted mode intentionally excludes all ordinary candidate families')
    key('ESC');yield;s.slot_only=False
    # Reach an arbitrary station on the second host, not only the first slot.
    target=rail_xyz('M-002','FACE_PU.S0',.35)
    mouse(*point('N-005'));yield;key('G');yield;mouse(*pixel(target));yield
    check(any(c.kind=='SLOT' and c.member_id=='M-002' for c in g_move._ACTIVE._snap_options),'G considers a rail on the second selected host')
    for _ in range(len(g_move._ACTIVE._snap_options)+1):
        snap=g_move._ACTIVE._snap
        if snap and snap.kind=='SLOT' and snap.member_id=='M-002':break
        key('TAB');yield
    check(g_move._ACTIVE._snap.member_id=='M-002','Tab can address stable second-host slot identity')
    snap=g_move._ACTIVE._snap
    check(math.dist(g_move._ACTIVE._candidate.project.nodes['N-005'].position_mm,snap.position_mm)<1e-7,'second-host preview exactly matches selected double-precision snap candidate')
    check(math.dist(snap.position_mm,rail_xyz(snap.member_id,snap.interface_id,snap.station))<1e-8,'nearest mouse station lies exactly on finite semantic rail')
    key('ESC');yield
    mouse(*point('N-005'));yield;key('G');yield;key('X');yield;yield from type_text('100');yield
    check(abs(g_move._ACTIVE._candidate.project.nodes['N-005'].position_mm[0]-300)<1e-7,'numeric X movement is not overridden by multi-rail magnets')
    key('ESC');yield
    # Draw mode must share the mixed candidate family and block inset retargeting.
    with ctx():bpy.ops.aludiy.draw_member('INVOKE_DEFAULT')
    yield;mouse(*point('N-009'));yield
    check(ops._ACTIVE_DRAW and ops._ACTIVE_DRAW._snap.node_id=='N-009','drawing finds ordinary endpoint with active multi-rail targets')
    before_choices=slot_tools.target_state(window.scene)
    action('clear_selection_rect');yield;key('LEFTMOUSE');yield
    check(slot_tools.target_state(window.scene)==before_choices,'in-flight drawing cannot modify rail set or click through inset')
    key('ESC');yield
    with ctx():bpy.ops.aludiy.draw_member('INVOKE_DEFAULT')
    yield;mouse(*pixel(target));yield
    check(any(c.kind=='SLOT' and c.member_id=='M-002' for c in ops._ACTIVE_DRAW._snap_options),'drawing shares second-host slot candidates')
    key('ESC');yield
    # Already positioned followers: explicit batch association, no hidden move.
    choose('M-001','FACE_PU.S0');choose('M-002','FACE_PU.S0',True)
    with ctx():
        q=p()
        q.nodes['N-005'].position_mm=rail_xyz('M-001','FACE_PU.S0',.5)
        q.nodes['N-007'].position_mm=rail_xyz('M-002','FACE_PU.S0',.65)
        runtime.set_project(window.scene,q);scene_adapter.rebuild_scene(window.scene,q,runtime.get_catalog())
        select(['M-003','M-004']);active('M-004')
        bpy.ops.ed.undo_push(message='before native batch links')
    yield;before_link=raw();before_nodes=p().to_dict()['nodes'];action('create_rect');yield;key('LEFTMOUSE');yield;yield
    check(len(p().associations)==3,'one native inset command creates links on two different selected slots')
    check(p().to_dict()['nodes']==before_nodes,'batch creation leaves all endpoint coordinates unchanged')
    safe_mouse();yield;key('Z',ctrl=True);yield
    check(raw()==before_link,'one Undo reverses whole multi-slot association transaction')
    key('Z',ctrl=True,shift=True);yield
    check(len(p().associations)==3,'one Redo restores both associations and pre-existing other-slot link')
    action('unlink_slot_rect');yield;key('LEFTMOUSE');yield;key('ESC');yield
    check(len(p().associations)==3,'cancelling batch unlink confirmation changes nothing')
    action('unlink_slot_rect');yield;key('LEFTMOUSE');yield;key('RET');yield;yield
    check(len(p().associations)==1 and next(iter(p().associations.values())).slot_reference.interface_id=='FACE_NU.S0','batch unlink only deletes exact selected slots, preserving unselected slot')
    check(p().to_dict()['nodes']==before_nodes,'batch unlink preserves node positions')
    with ctx():select(['M-003']);active('M-003');g_move._select_endpoint(bpy.context,'M-003','START')
    yield;safe_mouse();yield;key('G');yield;key('X');yield;yield from type_text('100');key('RET');yield
    check(abs(p().nodes['N-005'].position_mm[0]-120)<1e-6,'unlinked endpoint immediately accepts native G X 100')
    safe_mouse();yield;key('Z',ctrl=True);yield
    check(abs(p().nodes['N-005'].position_mm[0]-20)<1e-6,'endpoint move remains one Undo after batch unlink')
    key('Z',ctrl=True);yield
    check(len(p().associations)==3,'Undo batch unlink restores both relations')
    key('Z',ctrl=True,shift=True);yield
    check(len(p().associations)==1,'Redo batch unlink removes both relations once')
    # Deleting one selected host removes only its choice/active references.
    restore_choices();yield
    with ctx():
        select(['M-001']);active('M-001');bpy.ops.ed.undo_push(message='multi-target deletion baseline')
        before_delete=raw();bpy.ops.aludiy.delete_selected_members('EXEC_DEFAULT',True)
    yield
    check(slot_tools.target_specs(window.scene,p())==(('M-002','FACE_PU.S0'),),'host deletion preserves the other active target')
    check(slot_tools.choice_pairs(window.scene)==(('M-002','FACE_PU.S0'),),'host deletion prunes only removed-host chosen rails')
    safe_mouse();yield;key('Z',ctrl=True);yield
    check(raw()==before_delete and len(slot_tools.target_specs(window.scene,p()))==3,'one deletion Undo restores graph and complete rail target set')
    choose('M-002','FACE_PU.S0',True);yield  # toggle existing off then add again
    choose('M-002','FACE_PU.S0',True);yield
    action('remove_rect');yield;key('LEFTMOUSE');yield
    check(all(mid!='M-002' for mid,sid in slot_tools.choice_pairs(window.scene)),'remove current removes only that chosen host/slot')
    check(all(mid!='M-002' for mid,sid in slot_tools.target_specs(window.scene,p())),'remove current also removes corresponding active target')
    before_clear=raw();action('clear_selection_rect');yield;key('LEFTMOUSE');yield
    check(not slot_tools.choice_pairs(window.scene) and not slot_tools.target_specs(window.scene,p()),'clear selection clears chosen and activated collections')
    check(raw()==before_clear,'clearing UI selections never deletes engineering relations')
    # Explicit new-project/import boundaries cannot carry old IDs into new model.
    restore_choices();yield
    saved_project=p();saved_choices=slot_tools.target_state(window.scene)
    with ctx():bpy.ops.aludiy.new_project('EXEC_DEFAULT',True)
    yield
    check(not slot_tools.choice_pairs(window.scene) and not slot_tools.target_specs(window.scene,p()),'new project clears transient choices and active rails before IDs can be reused')
    with ctx():
        runtime.set_project(window.scene,saved_project);scene_adapter.rebuild_scene(window.scene,saved_project,runtime.get_catalog())
    restore_choices();yield
    # Import is another explicit graph replacement boundary; preserve data but
    # never carry a previous graph's transient rail IDs into it.
    imported=OUT/'import-fixture.aludiy.json';imported.write_text(raw())
    with ctx():bpy.ops.aludiy.import_project('EXEC_DEFAULT',filepath=str(imported))
    yield
    check(not slot_tools.choice_pairs(window.scene) and not slot_tools.target_specs(window.scene,p()),
          'successful import clears obsolete chosen and activated UI targets')
    restore_choices();yield
    with ctx():select(['M-001']);active('M-001');runtime.settings(window.scene).show_selection_lengths=True
    # Real clicks leave an inspected slot and the complete chosen set visible.
    yield;at(left,slot_pixel('M-001','FACE_PU.S0'));yield;yield from shift_click();yield from shift_click()
    yield
    expected_json=raw();(OUT/'expected.aludiy.json').write_text(expected_json)
    (OUT/'expected-targets.json').write_text(json.dumps(slot_tools.target_specs(window.scene,p())))
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'multi-slot.blend'))
    screenshot('multi-slot-final.png');yield
    check(Project.from_dict(json.loads(expected_json)).to_dict()==p().to_dict(),'project JSON and identities roundtrip without schema change')
    (OUT/'report.json').write_text(json.dumps({'status':'passed','checks':checks,'blender':bpy.app.version_string,'ui_scale':factor},ensure_ascii=False,indent=2))
    addon.unregister();bpy.ops.wm.quit_blender()
sequence=run()
def tick():
    try:next(sequence);return .25
    except StopIteration:return None
    except Exception:
        text=traceback.format_exc();print(text,flush=True)
        (OUT/'report.json').write_text(json.dumps({'status':'failed','checks':checks,'error':text},ensure_ascii=False,indent=2))
        try:screenshot('failure.png')
        except Exception:pass
        sys.stdout.flush();os._exit(1)
bpy.app.timers.register(tick,first_interval=1.0)
