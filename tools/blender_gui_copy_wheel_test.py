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
    install(model());yield
    with ctx():
        select(['M-002']);active('M-002')
        props=bpy.ops.aludiy.move_engineering.get_rna_type().properties
        check('duplicate' in props,'copy integrates transactional G operator')
    safe_mouse();yield
    before=raw();key('D',shift=True);yield
    check(g_move._ACTIVE is not None and g_move._ACTIVE.duplicate,'real Shift+D starts engineering copy')
    check(raw()==before,'copy preview does not persist engineering data')
    check(len(g_move.display_project(window.scene).members)==3,'copy preview exposes independent member')
    key('X');yield;yield from type_text('200');key('RET');yield
    check(len(p().members)==3,'confirm copy creates exactly one engineering member')
    check(p().nodes['N-003'].position_mm==(20,0,500),'copy does not move original')
    safe_mouse();yield;key('Z',ctrl=True);yield
    check(raw()==before,'single Undo removes copy and restores original graph')
    check(hasattr(bpy.types,'ALUDIY_OT_middle_context'),'native middle-tap macro registered')
    from aludiy_designer import action_wheel as aw
    def mmb(down):
        XT.XTestFakeButtonEvent(D,2,int(down),0);X11.XFlush(D)
    with ctx():select(['M-002']);active('M-002')
    yield
    safe_mouse();yield
    before_view=tuple(left.spaces.active.region_3d.view_rotation)
    mmb(True);mmb(False);yield;yield
    check(aw._WHEEL is not None,'stationary real middle click opens command wheel')
    check(tuple(left.spaces.active.region_3d.view_rotation)==before_view,'middle tap leaves orientation unchanged')
    check(raw()==before,'opening wheel leaves original graph unchanged')
    screenshot('01-action-wheel.png');yield
    mmb(True);mmb(False);yield
    check(aw._WHEEL is None,'second middle click closes wheel')
    safe_mouse();yield;mmb(True);yield
    mouse(cursor[0]+110,cursor[1]+60);yield;mmb(False);yield;yield
    check(aw._WHEEL is None,'middle drag never opens wheel')
    check(tuple(left.spaces.active.region_3d.view_rotation)!=before_view,'middle drag retains native orbit')
    safe_mouse();yield;mmb(True);mmb(False);yield;yield
    check(aw._WHEEL is not None,'wheel can reopen after navigation')
    mouse(left.x+30,left.y+30);yield;key('LEFTMOUSE');yield
    check(aw._WHEEL is None,'left click outside closes wheel')
    with ctx():check(g_move.selection_summary(bpy.context)[0]=={'M-002'},'outside dismissal cannot deselect model')
    safe_mouse();yield;mmb(True);mmb(False);yield;yield
    check(aw._WHEEL is not None,'open wheel again for command dispatch')
    rect=dict(aw._WHEEL._layout.buttons)['COPY'];reg=g_move._window_region(left)
    mouse(reg.x+rect.center[0],reg.y+rect.center[1]);yield;key('LEFTMOUSE');yield;yield
    check(aw._WHEEL is None and g_move._ACTIVE is not None and g_move._ACTIVE.duplicate,'wheel Copy dispatches engineering move after closing')
    key('ESC');yield
    check(raw()==before and g_move._ACTIVE is None,'wheel Copy cancellation leaves no hidden engineering copies')
    check(len([o for o in window.scene.objects if o.get('aludiy_entity_type')=='MEMBER_SOLID'])==2,'cancel copy restores original display cache count')
    # Graph duplication boundaries and Cancel/Redo.
    select(['M-002']);active('M-002');yield;safe_mouse();yield;before=raw();key('D',shift=True);yield
    key('RET');yield
    check(len(p().members)==3,'explicit zero-distance copy creates an independent overlapping member')
    safe_mouse();yield;key('Z',ctrl=True);yield
    check(raw()==before,'zero-distance copy is one undoable transaction')
    key('Z',ctrl=True,shift=True);yield
    check(len(p().members)==3,'native Redo restores copy exactly once')
    install(model());yield
    with ctx():
        q=create_slot_associations(p(),runtime.get_catalog(),host_member_id='M-001',interface_id='FACE_PU.S0',member_ids=['M-002']).project
        runtime.set_project(window.scene,q);scene_adapter.rebuild_scene(window.scene,q,runtime.get_catalog())
        select(['M-001','M-002']);active('M-001')
        bpy.ops.aludiy.set_butt_joint('EXEC_DEFAULT',True)
        bpy.ops.ed.undo_push(message='copy-group-baseline')
    yield;before=raw();old=p().to_dict();safe_mouse();yield;key('D',shift=True);yield
    check(len(g_move.display_project(window.scene).associations)==2,'group copy preview remaps internal slot links')
    check(len(g_move.display_project(window.scene).joints)==2,'group copy retains internal processing')
    key('Y');yield;yield from type_text('250');key('RET');yield
    check(len(p().members)==4 and len(p().nodes)==8,'group copy creates complete independent rods and nodes')
    check(all(p().nodes[n['id']].position_mm==tuple(n['position_mm']) for n in old['nodes']),'group placement never moves original framework')
    with ctx():check(len(g_move.selection_summary(bpy.context)[0])==2,'only two copied rods remain selected after placement')
    safe_mouse();yield;key('Z',ctrl=True);yield
    check(raw()==before,'one Undo removes complete copy including relationships and joints')
    select(['M-002']);active('M-002');yield;safe_mouse();yield;key('D',shift=True);yield
    check(g_move._ACTIVE._copy_dropped==2,'follower-only copy reports omitted external slot and processing dependencies')
    key('X');yield;yield from type_text('100');key('RET');yield
    check(len(p().associations)==1 and len(p().joints)==1,'follower copy is not bound to original host')
    safe_mouse();yield;key('G');yield;key('Z');yield;yield from type_text('50');key('RET');yield
    check(g_move._ACTIVE is None and len(p().members)==3,'independent copied follower accepts a second G without copying again')
    # Reported pinned host deletion: both graph and ephemeral target are handled.
    install(model());yield
    with ctx():
        q=create_slot_associations(p(),runtime.get_catalog(),host_member_id='M-001',interface_id='FACE_PU.S0',member_ids=['M-002']).project
        runtime.set_project(window.scene,q);scene_adapter.rebuild_scene(window.scene,q,runtime.get_catalog())
        select(['M-001']);active('M-001')
        bpy.ops.aludiy.inspect_profile_slot(interface_id='FACE_PU.S0');bpy.ops.aludiy.set_slot_target()
        bpy.ops.ed.undo_push(message='delete-pinned-baseline')
        check(bpy.ops.aludiy.delete_selected_members('EXEC_DEFAULT',True)=={'FINISHED'},'engineering deletion succeeds for pinned host')
    yield
    check(not p().associations and runtime.settings(window.scene).slot_target_member_id=='','host deletion clears true relationships and ephemeral target')
    with ctx():select(['M-002']);bpy.ops.aludiy.select_endpoint(owner_id='M-002',endpoint='START')
    yield;safe_mouse();yield;key('G');yield;key('X');yield;yield from type_text('100');key('RET');yield
    check(abs(p().nodes['N-003'].position_mm[0]-120)<1e-8,'previously attached endpoint moves immediately after host deletion')
    with ctx():
        st=runtime.settings(window.scene);st.slot_target_member_id='deleted-host';st.slot_target_interface_id='FACE_PU.S0'
    safe_mouse();yield;key('G');yield;key('Y');yield;yield from type_text('80');key('RET');yield
    check(g_move._ACTIVE is None and p().nodes['N-003'].position_mm[1]==80,'old stale target falls back to normal snap without trapping G')
    check(runtime.settings(window.scene).slot_target_member_id=='','fallback clears the actual ephemeral reference')
    # Native and mixed selections.
    with ctx():
        left.spaces.active.use_local_collections=False
        for obj in window.view_layer.objects:obj.select_set(False)
        bpy.ops.mesh.primitive_cube_add(location=(2,2,2))
        native=bpy.context.object;native.name='NativeCopyProbe'
    yield;safe_mouse();yield;raw_native=raw();count_native=len(window.scene.objects);key('D',shift=True);yield;key('ESC');yield
    print('NATIVE_COPY_DIAGNOSTIC',count_native,len(window.scene.objects),g_move._ACTIVE,[o.name for o in g_move.selected_objects(bpy.context)],flush=True)
    check(g_move._ACTIVE is None and len(window.scene.objects)==count_native+1,'ordinary Cube Shift+D remains native')
    check(raw()==raw_native,'ordinary copy does not modify engineering data')
    with ctx():
        for o in list(window.scene.objects):
            if o.name.startswith('NativeCopyProbe'):bpy.data.objects.remove(o,do_unlink=True)
    install(model());yield
    with ctx():
        select(['M-002']);active('M-002')
        ordinary=bpy.data.objects.new('MixedCopyProbe',None);window.scene.collection.objects.link(ordinary);ordinary.select_set(True)
        count_mixed=len(window.scene.objects);before_mixed=raw()
    yield;safe_mouse();yield;key('D',shift=True);yield
    check(g_move._ACTIVE is None and raw()==before_mixed and len(window.scene.objects)==count_mixed,'mixed ordinary/engineering Shift+D rejects atomically')
    with ctx():bpy.data.objects.remove(ordinary,do_unlink=True);select(['M-002']);active('M-002')
    yield;safe_mouse();yield;mmb(True);mmb(False);yield;yield
    check(aw._WHEEL is not None,'wheel available after rejected mixed copy')
    rect=dict(aw._WHEEL._layout.buttons)['DELETE'];reg=g_move._window_region(left)
    mouse(reg.x+rect.center[0],reg.y+rect.center[1]);yield;key('LEFTMOUSE');yield;yield
    check(aw._WHEEL is None and raw()==before_mixed,'wheel Delete opens confirmation without immediate deletion')
    key('ESC');yield
    check(raw()==before_mixed,'cancel Delete confirmation preserves model')
    select(['M-001','M-002']);active('M-001');yield
    def click_wheel(name):
        rect=dict(aw._WHEEL._layout.buttons)[name];reg=g_move._window_region(left)
        mouse(reg.x+rect.center[0],reg.y+rect.center[1])
    safe_mouse();yield;mmb(True);mmb(False);yield;yield;click_wheel('LINK');yield;key('LEFTMOUSE');yield;yield
    check(len(p().associations)==1,'wheel Create uses existing explicit association engine')
    safe_mouse();yield;mmb(True);mmb(False);yield;yield;click_wheel('UNLINK');yield;key('LEFTMOUSE');yield;yield
    check(not p().associations,'wheel Unlink removes true graph relationship')
    safe_mouse();yield;key('Z',ctrl=True);yield
    check(len(p().associations)==1,'one Undo restores wheel-unlinked relation')
    safe_mouse();yield;mmb(True);mmb(False);yield;yield;key('RIGHTMOUSE');yield
    check(aw._WHEEL is None,'right click closes wheel')
    with ctx():bpy.ops.aludiy.action_wheel('INVOKE_DEFAULT',location=(200,300))
    yield;addon.unregister();addon.register();bpy.context.window_manager.keyconfigs.update();yield
    check(aw._WHEEL is None and not aw._PENDING and not aw._GESTURES,'disable/re-enable clears wheel and deferred state')
    safe_mouse();yield;mmb(True);mmb(False);yield;yield
    check(aw._WHEEL is not None,'native macro reusable after re-enable')
    key('ESC');yield
    safe_mouse();yield;mmb(True);yield
    mouse(cursor[0]+60,cursor[1]+35);yield;key('ESC');yield;mmb(False);yield;yield
    check(not aw._GESTURES,'cancelled native orbit cannot leak gesture observer')
    # Other view, navigation modifiers, modal and stale drawing target guards.
    right.spaces.active.show_region_ui=False;yield
    mouse(right.x+160,right.y+200);yield;mmb(True);mmb(False);yield;yield
    check(aw._WHEEL is not None and aw._WHEEL._area==right,'right solid viewport opens the same engineering wheel')
    key('ESC');yield
    oldname=window.workspace.name;window.workspace.name='NativeNavigationProbe';yield
    safe_mouse();yield;mmb(True);mmb(False);yield;yield
    check(aw._WHEEL is None,'ordinary workspace middle click does not open engineering UI')
    window.workspace.name=oldname;yield
    safe_mouse();yield;_key('Shift_L',True);mmb(True);yield
    location=tuple(left.spaces.active.region_3d.view_location)
    mouse(cursor[0]+60,cursor[1]+40);yield;mmb(False);_key('Shift_L',False);X11.XFlush(D);yield
    check(aw._WHEEL is None and tuple(left.spaces.active.region_3d.view_location)!=location,'Shift-middle drag retains native pan')
    with ctx():select(['M-001']);active('M-001')
    yield;safe_mouse();yield;key('G');yield;mmb(True);mmb(False);yield;yield
    check(g_move._ACTIVE is not None and aw._WHEEL is None,'G modal navigation does not summon command wheel')
    key('ESC');yield
    with ctx():
        runtime.settings(window.scene).slot_target_member_id='deleted-drawing-host'
        bpy.ops.aludiy.draw_member('INVOKE_DEFAULT')
    yield;safe_mouse();mouse(cursor[0]+12,cursor[1]+10);yield
    check(ops._ACTIVE_DRAW is not None and not ops._ACTIVE_DRAW._cursor_error,'drawing also ignores only the missing ephemeral target')
    check(runtime.settings(window.scene).slot_target_member_id=='','drawing fallback clears stale host rather than requiring manual stop')
    key('ESC');yield
    with ctx():
        select(['M-001']);active('M-001')
        bpy.ops.aludiy.inspect_profile_slot(interface_id='FACE_PU.S0');bpy.ops.aludiy.set_slot_target()
        bpy.ops.ed.undo_push(message='delete-target-undo-baseline')
        delete_before=raw()
        bpy.ops.aludiy.delete_selected_members('EXEC_DEFAULT',True)
    yield;safe_mouse();yield;key('Z',ctrl=True);yield
    check(raw()==delete_before and runtime.settings(window.scene).slot_target_member_id=='M-001','one delete Undo restores host, true graph and pinned target')
    select(['M-001','M-002']);active('M-001');yield
    right.spaces.active.show_region_ui=True
    next(r for r in right.regions if r.type=='UI').active_panel_category='AluDIY'
    with ctx():runtime.settings(window.scene).show_selection_lengths=True
    expected=raw();(OUT/'expected.aludiy.json').write_text(expected)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'copy-wheel.blend'))
    mouse(left.x+250,left.y+350);yield;mmb(True);mmb(False);yield;yield
    screenshot('02-copy-wheel-final.png');yield;key('ESC');yield
    (OUT/'report.json').write_text(json.dumps({'status':'passed','checks':checks,'blender':bpy.app.version_string,'ui_scale':factor},ensure_ascii=False,indent=2))
    addon.unregister();bpy.ops.wm.quit_blender()
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
