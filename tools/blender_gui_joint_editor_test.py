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

def unused_baseline_frame():
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


from aludiy_designer import joint_editor as je, selection_state
from aludiy_designer.vendor.aludiy_core.joints import solve_cutbacks
from aludiy_designer.vendor.aludiy_core.joint_editor import joint_choices

def frame():
    p=Project('P-JUNCTION-PHASE1','alpha-2026.10')
    for nid,pt in [('N0',(0,0,500)),('N1',(500,0,500)),('N2',(0,500,500)),('N3',(0,0,0))]:p.add_node(Node(nid,pt))
    for mid,a,b in [('M-001','N0','N1'),('M-002','N0','N2'),('M-003','N0','N3')]:p.add_member(Member(mid,a,b,'generic:tslot-2020@0.1'))
    return p

def select(mids):
    with ctx():
        bpy.ops.object.select_all(action='DESELECT')
        for o in window.scene.objects:
            if o.get('aludiy_entity_type')=='MEMBER_AXIS' and o.get('aludiy_entity_id') in mids:
                o.select_set(True);window.view_layer.objects.active=o
        runtime.settings(window.scene).endpoint_member_id=''
        runtime.settings(window.scene).endpoint_side=''
        view_sync._LAST_SELECTED_BY_WINDOW.clear()

def p():return runtime.get_project(window.scene)
def open_editor():
    with ctx():return bpy.ops.aludiy.edit_joint_options('INVOKE_DEFAULT',True)
def owner():return je._ACTIVE.owner
def update(**kwargs):
    op=owner()
    for k,v in kwargs.items():setattr(op,k,v)
    with ctx():op.check(bpy.context)

def native_bands():
    # Locate large native blue button fills, not text/OCR. Limits to invoking
    # viewport so outliner and the independent preview geometry cannot match.
    import numpy as np
    result=subprocess.run(['ffmpeg','-loglevel','error','-f','x11grab','-video_size','1800x1100','-i',os.environ['DISPLAY'],'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],stdout=subprocess.PIPE,check=True,timeout=8)
    a=np.frombuffer(result.stdout,dtype=np.uint8).reshape(1100,1800,3)[:,:left.x+left.width].astype(int)
    mask=(a[:,:,2]>a[:,:,0]+35)&(a[:,:,2]>a[:,:,1]+10)&(a[:,:,0]>30)&(a[:,:,0]<120)&(a[:,:,1]>60)
    ys=np.flatnonzero(mask.sum(axis=1)>140)
    bands=[]
    for group in np.split(ys,np.where(np.diff(ys)>5)[0]+1):
        if len(group)<5:continue
        xs=np.flatnonzero(mask[group].sum(axis=0)>len(group)/3)
        bands.append((int(xs.min()),int(group.min()),int(xs.max()),int(group.max())))
    assert len(bands)>=2, bands
    return bands

def native_cancel():
    x0,y0,x1,y1=native_bands()[-1]
    mouse((x0+x1)/2-(x1-x0)-8,1100-(y0+y1)/2);yield;key('LEFTMOUSE');yield;yield

def native_edit_gap_and_host(text,host):
    bands=native_bands();x0,y0,x1,y1=bands[0]
    current='ABC'.index(owner().host_choice);pitch=round((y1-y0+1)*1.35)
    # The fixed three-option dialog places the gap field one row after C.
    field_y=(y0+y1)/2+(3-current)*pitch
    mouse((x0+x1)/2,1100-field_y);yield;key('LEFTMOUSE');yield
    key('A',ctrl=True);yield;yield from type_text(text);key('RET');yield
    check(owner().gap_input==text,'native text field accepts precise gap input')
    # Refresh coordinates, then click the requested native radio row.
    x0,y0,x1,y1=native_bands()[0];current='ABC'.index(owner().host_choice)
    pitch=round((y1-y0+1)*1.35)
    mouse((x0+x1)/2,1100-((y0+y1)/2+('ABC'.index(host)-current)*pitch));yield;key('LEFTMOUSE');yield;yield
    check(owner().host_choice==host,'native radio click switches the host scheme')

def run():
    global D,window,left,right
    D=X11.XOpenDisplay(None);addon.register();bpy.context.window_manager.keyconfigs.update();window=bpy.context.window
    factor=float(os.environ.get('ALUDIY_TEST_UI_SCALE','1'));bpy.context.preferences.view.ui_scale=factor;yield;yield
    window.workspace.name=runtime.WORKSPACE_NAME
    for o in window.scene.objects:o.select_set(False);o.hide_set(True)
    a=next(a for a in window.screen.areas if a.type=='VIEW_3D')
    with bpy.context.temp_override(window=window,area=a,region=next(r for r in a.regions if r.type=='WINDOW')):
        bpy.ops.screen.area_split(direction='VERTICAL',factor=.52)
    yield
    left,right=sorted([a for a in window.screen.areas if a.type=='VIEW_3D'],key=lambda a:a.x)
    with ctx():view_sync.configure_dual_views(bpy.context)
    for a in (left,right):
        a.spaces.active.region_3d.view_rotation=Euler((math.radians(68),0,math.radians(32))).to_quaternion()
        a.spaces.active.region_3d.view_location=(.15,.15,.35);a.spaces.active.region_3d.view_distance=1.6
        a.spaces.active.show_region_ui=a==right;a.spaces.active.show_gizmo=False
    with ctx():
        runtime.set_project(window.scene,frame());scene_adapter.rebuild_scene(window.scene,frame(),runtime.get_catalog())
    select(['M-001','M-002','M-003']);yield;yield
    next(r for r in right.regions if r.type=='UI').active_panel_category='AluDIY'
    before=raw();geometry={o.name:tuple(tuple(v.co) for v in o.data.vertices) for o in window.scene.objects if o.type=='MESH' and o.get('aludiy_managed')}
    selected=selection_state.capture(bpy.context)
    with ctx():bpy.ops.ed.undo_push(message='Joint editor baseline')
    mouse(left.x+left.width-80,left.y+left.height-200);yield
    check(open_editor()=={'RUNNING_MODAL'},'native junction dialog invokes')
    yield;yield
    check(je._ACTIVE is not None and je._HANDLE is not None,'live local preview registered')
    check(not right.spaces.active.show_region_ui,'other viewport sidebar temporarily closes to leave usable preview space')
    check(len(owner()._choices)==3 and all(o.valid for o in owner()._choices),'three complete legal corner recipes exposed')
    check(raw()==before,'opening and drawing popup never initializes or changes engineering data')
    check(geometry=={o.name:tuple(tuple(v.co) for v in o.data.vertices) for o in window.scene.objects if o.type=='MESH' and o.get('aludiy_managed')},'preview owns no mesh cache mutations')
    update(host_choice='A',gap_input='2mm');yield;yield
    check(je._ACTIVE.option.host_member_id=='M-001','explicit host selection is independent of last active object')
    check(je._ACTIVE.option.solution.lengths['M-002'].cut_length_mm==488,'three-way preview evaluates branch lengths simultaneously')
    check(raw()==before,'switch and gap preview remain read-only')
    update(before=True,view_angle='TOP');yield;yield
    check(je._ACTIVE.before and je._ACTIVE.view_angle=='TOP','before comparison and alternate projection update')
    update(before=False,view_angle='ISO',host_choice='C');yield;yield
    screenshot('01-three-way-preview.png');yield
    if os.environ.get('ALUDIY_PROBE_ONLY'):
        key('ESC');yield;addon.unregister();bpy.ops.wm.quit_blender();return
    key('ESC');yield;yield
    check(je._ACTIVE is None and je._HANDLE is None,'native Esc tears down preview and handler')
    check(raw()==before,'native cancellation leaves engineering JSON identical')
    check(right.spaces.active.show_region_ui,'cancellation restores the original sidebar visibility')
    with ctx():check(selection_state.capture(bpy.context)==selected,'cancellation preserves complete engineering selection')
    mouse(left.x+left.width-80,left.y+left.height-200);yield;open_editor();yield;yield
    update(host_choice='C',gap_input='2');yield
    key('RET');yield;yield
    check(je._ACTIVE is None,'native Enter confirms and closes preview')
    check(len(p().joints)==2,'one apply commits the two-rule corner transaction')
    check(p().to_dict()['nodes']==frame().to_dict()['nodes'],'confirmed recipe leaves all design coordinates unchanged')
    check(not p().associations,'processing creates no hidden position associations')
    check(solve_cutbacks(p(),runtime.get_catalog(),strict=True).lengths['M-001'].cut_length_mm==488,'confirmed body length matches preview')
    after=raw()
    mouse(left.x+150,left.y+150);yield;key('Z',ctrl=True);yield;yield
    check(raw()==before,'one native Undo restores entire three-way apply')
    key('Z',ctrl=True,shift=True);yield;yield
    check(raw()==after,'one native Redo restores chosen corner')
    mouse(left.x+left.width-80,left.y+left.height-200);yield;open_editor();yield;yield
    check(owner().gap_input=='2','reopening editor loads existing local rule gap')
    update(host_choice='A',gap_input='3');yield;key('RET');yield;yield
    check(len(p().joints)==2 and all(j.host_member_id=='M-001' for j in p().joints.values()),'changing host replaces local rules rather than stacking cuts')
    check(solve_cutbacks(p(),runtime.get_catalog(),strict=True).lengths['M-002'].cut_length_mm==487,'updated gap is not repeatedly deducted')
    stable=raw()
    mouse(left.x+left.width-80,left.y+left.height-200);yield;open_editor();yield;yield
    update(gap_input='-1');yield
    check(bool(owner()._error),'invalid gap shows an explicit non-submittable reason')
    key('RET');yield;yield
    check(raw()==stable and je._ACTIVE is None,'invalid confirmation commits nothing and cleans preview')
    mouse(left.x+left.width-80,left.y+left.height-200);yield;open_editor();yield;yield
    select(['M-001']);yield;key('RET');yield;yield
    check(raw()==stable and je._ACTIVE is None,'selection change rejects stale preview commit')
    select(['M-001','M-002','M-003']);yield
    # Explicit native Cancel is reliable even over property controls (right click may open a field menu).
    mouse(left.x+left.width-80,left.y+left.height-200);yield;open_editor();yield;yield
    yield from native_cancel()
    check(raw()==stable and je._ACTIVE is None,'native Cancel button is non-destructive')
    # Persist final corner and compare exact data in a fresh Blender process.
    (OUT/'expected.aludiy.json').write_text(raw())
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'joint-editor.blend'))
    check(p().schema_version=='0.4.0','uses existing processing schema without an extra migration')
    mouse(left.x+left.width-80,left.y+left.height-200);yield;open_editor();yield;yield
    yield from native_edit_gap_and_host('2mm','B')
    screenshot('02-joint-editor-final.png');yield
    check(not je._ACTIVE.draw_error,'GPU local preview rendered without draw exceptions')
    key('ESC');yield;yield
    addon.unregister();addon.register();yield
    check(runtime.get_project(window.scene).to_dict()==json.loads((OUT/'expected.aludiy.json').read_text()),'disable/re-enable preserves joint data and has no stale preview')
    check(je._ACTIVE is None and je._HANDLE is None,'lifecycle cleanup leaves no overlay handler')
    (OUT/'report.json').write_text(json.dumps({'status':'passed','checks':checks,'blender':bpy.app.version_string,'ui_scale':factor},ensure_ascii=False,indent=2))
    print('JOINT_EDITOR_GUI_OK',len(checks),flush=True);addon.unregister();bpy.ops.wm.quit_blender()

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
