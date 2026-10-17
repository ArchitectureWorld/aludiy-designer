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
    addon.register();bpy.context.window_manager.keyconfigs.update();window=bpy.context.window
    bpy.context.preferences.view.ui_scale=1.0;yield
    window.workspace.name=runtime.WORKSPACE_NAME
    for o in window.scene.objects:o.hide_set(True)
    a=next(a for a in window.screen.areas if a.type=='VIEW_3D')
    with bpy.context.temp_override(window=window,area=a,region=next(r for r in a.regions if r.type=='WINDOW')):
        bpy.ops.screen.area_split(direction='VERTICAL',factor=.52)
    yield
    left,right=sorted([a for a in window.screen.areas if a.type=='VIEW_3D'],key=lambda a:a.x)
    with ctx():view_sync.configure_dual_views(bpy.context)
    for a in (left,right):
        rv=a.spaces.active.region_3d;rv.view_rotation=Euler((math.radians(72),0,math.radians(22))).to_quaternion()
        rv.view_location=(.35,0,.5);rv.view_distance=2.4
        a.spaces.active.show_region_ui=a==right;a.spaces.active.show_gizmo=False
    reset();select(['M-001']);yield
    next(r for r in right.regions if r.type=='UI').active_panel_category='AluDIY';yield
    from aludiy_designer import profile_tools as pt, panels, slot_tools, viewport_overlay as ov
    check(hasattr(pt,'inspector_layout'),'one shared visible layout drives inset rendering and picking')
    def view(area):
        with ctx(area):return pt.inspector_layout(bpy.context)
    def at(area,point):
        reg=next(r for r in area.regions if r.type=='WINDOW');mouse(reg.x+point[0],reg.y+point[1])
    def slot_pos(area,sid):
        return next(s.center for s in view(area).layout.slots if s.interface_id==sid)
    def selected():
        return sorted(o.name for o in window.view_layer.objects if o.select_get())
    initial=raw();selection=selected()
    at(left,slot_pos(left,'FACE_PV.S0'));yield
    with ctx():check(pt.hovered_slot(bpy.context,view(left))=='FACE_PV.S0','slot hover prehighlight matches mouse position')
    key('LEFTMOUSE');yield
    check(runtime.settings(window.scene).inspected_interface_id=='FACE_PV.S0','real left click selects exact slot in left inset')
    check(selected()==selection and raw()==initial,'slot click preserves model selection and engineering data')
    check(not runtime.settings(window.scene).slot_target_member_id,'slot click does not implicitly pin target or create association')
    at(left,view(left).layout.pin_rect.center);yield;key('LEFTMOUSE');yield
    check(slot_tools.target_spec(window.scene,p())==('M-001','FACE_PV.S0'),'inset Use for Snapping pins selected stable interface')
    at(right,slot_pos(right,'FACE_PV.S1'));yield;key('LEFTMOUSE');yield
    check(runtime.settings(window.scene).inspected_interface_id=='FACE_PV.S1','right inset also selects the other parallel lane')
    check(slot_tools.target_spec(window.scene,p())[1]=='FACE_PV.S0','inspecting another slot does not silently replace pinned target')
    at(right,view(right).layout.pin_rect.center);yield;key('LEFTMOUSE');yield
    check(slot_tools.target_spec(window.scene,p())[1]=='FACE_PV.S1','right inset button explicitly changes pinned target')
    at(right,view(right).layout.clear_rect.center);yield;key('LEFTMOUSE');yield
    check(slot_tools.target_spec(window.scene,p()) is None and raw()==initial,'inset Clear restores normal snaps without changing project')
    # Selection and empty background are deliberately tested with modifiers too.
    select(['M-001','M-002']);yield
    with ctx():
        window.view_layer.objects.active=next(o for o in window.view_layer.objects if o.get('aludiy_entity_id')=='M-001' and o.get('aludiy_entity_type')=='MEMBER_AXIS')
    selection=selected();yield
    at(left,slot_pos(left,'FACE_PV.S0'));yield;key('LEFTMOUSE',shift=True);yield
    check(selected()==selection,'Shift-click in inset cannot modify the multi-selection behind it')
    lay=view(left).layout;at(left,(lay.rect.x+8,lay.rect.y+lay.rect.height-10));yield;key('LEFTMOUSE');yield
    check(selected()==selection and raw()==initial,'click empty inset consumes input without touching geometry or selection')
    with ctx():
        info=panels.selection_info(bpy.context)
        check(info['member_ids']==('M-001','M-002') and info['active_member']=='M-001','sidebar readout distinguishes complete selection and active member')
        check(info['length_mm']==1000 and len(info['lengths'])==2,'sidebar active length is not group sum; individual values available')
        runtime.settings(window.scene).show_selection_lengths=True
        class Layout:
            def __init__(self):self.events=[]
            def box(self):return self
            def row(self,*a,**k):return self
            def column(self,*a,**k):return self
            def separator(self,*a,**k):pass
            def label(self,**k):self.events.append(('label',k.get('text','')))
            def prop(self,*a,**k):self.events.append(('prop',a[1]))
            def operator(self,name,**k):self.events.append(('op',name));return self
        rec=Layout();panels.draw_selection_readout(rec,bpy.context)
        check(any('1000.000 mm' in v for kind,v in rec.events if kind=='label'),'actual sidebar drawer emits exact engineering length')
        from unittest.mock import patch
        dims=[]
        with patch.object(ov,'_draw_member_reference_dimension',side_effect=lambda *a:dims.append('member')),patch.object(ov,'_draw_node_coordinate_reference',side_effect=lambda *a:dims.append('node')):
            ov._draw_direction_overlay()
        check(not dims,'selected line overlay does not draw static dimensions or witness lines')
    screenshot('01-interactive-section-clean-view.png');yield
    # During movement the inset is an input guard, not a new movement plane.
    select(['M-001']);yield
    with ctx():bpy.ops.aludiy.select_endpoint(owner_id='M-001',endpoint='END')
    yield;mouse(*point('N-002'));yield;key('G');yield;key('Z');yield;yield from type_text('100')
    with ctx():check(abs(panels.selection_info(bpy.context)['length_mm']-1100)<1e-6,'sidebar length tracks uncommitted endpoint movement')
    before_delta=tuple(g_move._ACTIVE._exact_delta);sid=runtime.settings(window.scene).inspected_interface_id
    at(left,slot_pos(left,'FACE_PV.S1'));yield;key('LEFTMOUSE');yield
    check(g_move._ACTIVE is not None and tuple(g_move._ACTIVE._exact_delta)==before_delta and raw()==initial,'clicking inset during G neither moves cursor geometry nor commits')
    check(runtime.settings(window.scene).inspected_interface_id==sid,'slot is locked while G transaction is in progress')
    key('ESC');yield
    with ctx():check(panels.selection_info(bpy.context)['length_mm']==1000,'cancel restores sidebar length and leaves geometry unchanged')
    # Roll hit mapping is recalculated instead of reusing old pixel regions.
    select(['M-001']);yield
    with ctx():bpy.ops.aludiy.edit_selected_profiles(action='ROTATE',angle='90')
    yield;at(left,slot_pos(left,'FACE_PV.S0'));yield;key('LEFTMOUSE');yield
    check(runtime.settings(window.scene).inspected_interface_id=='FACE_PV.S0','rotated section stays directly pickable with same interface ID')
    # Actual drawing modal clicks over inset must not define even a first point.
    km=bpy.context.window_manager.keyconfigs.addon.keymaps.new(name='Object Mode',space_type='EMPTY')
    km.keymap_items.new('aludiy.draw_member','F8','PRESS');bpy.context.window_manager.keyconfigs.update()
    mouse(left.x+240,left.y+320);yield;key('F8');yield
    check(ops._ACTIVE_DRAW is not None,'existing drawing command still starts')
    before=raw();at(left,slot_pos(left,'FACE_PV.S0'));yield;key('LEFTMOUSE');yield
    check(ops._ACTIVE_DRAW._start_mm is None and raw()==before,'inset click cannot start an accidental segment in drawing mode')
    # Numeric/Enter at an inset is also blocked: it must not locate on the model
    # behind the card, while Esc/right click is always available to finish.
    from types import SimpleNamespace
    with ctx():check(pt.modal_inset_guard(bpy.context,SimpleNamespace(type='RET',mouse_x=cursor[0],mouse_y=cursor[1])),
                    'keyboard confirmation over inset cannot relocalize a hidden model point')
    mouse(*point('N-001'));yield;key('LEFTMOUSE');yield;key('X');yield
    mouse(*pixel((300,0,0)));yield;yield from type_text('200')
    with ctx():
        rec=Layout();panels.draw_selection_readout(rec,bpy.context)
        check(any(v=='正在绘制  200.000 mm' for kind,v in rec.events if kind=='label'),
              'sidebar drawer shows actual numeric drawing preview, not an old selected length')
    count=len(p().members);at(left,slot_pos(left,'FACE_PV.S0'));yield;key('RET');yield
    check(len(p().members)==count and ops._ACTIVE_DRAW is not None,'Enter over inset does not commit the preview behind it')
    key('RIGHTMOUSE');yield;check(ops._ACTIVE_DRAW is None,'right click still exits drawing over inset')
    # Model click outside inset is not swallowed.
    select(['M-001']);yield;mouse(*point('N-002'));yield;key('LEFTMOUSE');yield
    with ctx():check(g_move.endpoint_context(bpy.context)==('M-001','END'),'normal endpoint picking outside inset remains native to plugin')
    # Hidden inspector and narrow region leave no invisible blocked targets.
    with ctx():
        runtime.settings(window.scene).show_section_inspector=False
        check(pt.inspector_layout(bpy.context) is None,'hidden inset has no clickable area')
        runtime.settings(window.scene).show_section_inspector=True
    # Same layout is scaled for high-DPI preferences without modifying geometry.
    factor=float(os.environ.get('ALUDIY_TEST_UI_SCALE','1'))
    bpy.context.preferences.view.ui_scale=factor;yield;yield
    at(left,slot_pos(left,'FACE_PV.S1'));yield;key('LEFTMOUSE');yield
    check(runtime.settings(window.scene).inspected_interface_id=='FACE_PV.S1','inset picking stays aligned after DPI scaling')
    select(['M-001','M-002']);yield
    with ctx():
        runtime.settings(window.scene).show_selection_lengths=True
        runtime.settings(window.scene).solid_display_mode='PROFILE'
    screenshot('02-final-section-sidebar.png');yield
    expected=raw();(OUT/'expected.aludiy.json').write_text(expected)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'section-ui.blend'))
    check(not p().associations,'all inspection and target controls leave association data untouched')
    expected_keys=len(g_move._KEYMAPS)
    addon.unregister()
    check(not g_move._KEYMAPS and not pt._CURSOR_BY_WINDOW and pt._DRAW_HANDLE is None
          and pt._clear_pointer_on_load not in bpy.app.handlers.load_post,'disable removes input and hover resources')
    addon.register();bpy.context.window_manager.keyconfigs.update();yield
    check(len(g_move._KEYMAPS)==expected_keys,'reenable does not duplicate mouse handlers')
    (OUT/'report.json').write_text(json.dumps({'status':'passed','blender':bpy.app.version_string,'checks':checks,'ui_scale':factor},ensure_ascii=False,indent=2))
    print('SECTION_UI_GUI_OK',len(checks),flush=True)
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
