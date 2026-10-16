"""Real workspace lifecycle: do NOT rename Layout or pre-split it as test setup."""
import bpy,sys,os,json,traceback,subprocess,ctypes,math
from pathlib import Path
from mathutils import Euler
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'extension'))
import aludiy_designer as addon
from aludiy_designer import view_sync as v,runtime,scene_adapter
from aludiy_designer.vendor.aludiy_core import Project,Node,Member
OUT=Path(os.environ.get('ALUDIY_EVIDENCE_DIR','/tmp/aludiy-workspace'));OUT.mkdir(parents=True,exist_ok=True)
checks=[];w=None

def check(value,label):
    assert value,label
    checks.append(label);print('WORKSPACE_CHECK_OK',label,flush=True)
def areas():return sorted((a for a in w.screen.areas if a.type=='VIEW_3D'),key=lambda a:(a.x,a.y))
def ctx(a=None):
    a=a or areas()[0]
    return bpy.context.temp_override(window=w,screen=w.screen,area=a,region=next(r for r in a.regions if r.type=='WINDOW'))
def ready():return w.workspace.name==runtime.WORKSPACE_NAME and len(areas())==2 and all(a.width>32 for a in areas()) and not getattr(v,'_PENDING_SETUP',{})
def wait_ready():
    for _ in range(24):
        yield
        if ready():return
    raise AssertionError('Setup never activated and initialized ALU DIY; active='+w.workspace.name)
def pose(a):
    s=a.spaces.active;r=s.region_3d
    return dict(rotation=list(r.view_rotation),location=list(r.view_location),distance=r.view_distance,
                perspective=r.view_perspective,lens=s.lens,clip_start=s.clip_start,clip_end=s.clip_end)
def same():return not v._different(v._capture(areas()[0]),v._capture(areas()[1]))
def image(name):
    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP',iterations=1)
    subprocess.run(['ffmpeg','-y','-loglevel','error','-f','x11grab','-video_size','1800x1100','-i',os.environ['DISPLAY'],'-frames:v','1',str(OUT/name)],check=True,timeout=12)

def run():
    global w
    addon.register();w=bpy.context.window
    original=w.workspace;original_name=original.name;original_ptr=original.as_pointer()
    original_screen=w.screen;start=areas()[0]
    r=start.spaces.active.region_3d;r.view_rotation=Euler((1.12,0,.58)).to_quaternion();r.view_location=(.4,.2,.6);r.view_distance=3.4;r.view_perspective=os.environ.get('ALUDIY_INITIAL_PROJECTION','PERSP')
    start.spaces.active.lens=61;start.spaces.active.clip_start=.02;start.spaces.active.clip_end=400
    before=pose(start);workspaces={s.as_pointer():s.name for s in bpy.data.workspaces}
    p=Project('P-WORKSPACE','alpha-2026.10')
    for nid,xyz in [('N-001',(0,0,0)),('N-002',(0,0,1000)),('N-003',(800,0,1000))]:p.add_node(Node(nid,xyz))
    for mid,a,b in [('M-001','N-001','N-002'),('M-002','N-002','N-003')]:p.add_member(Member(mid,a,b,'generic:tslot-2040@0.1'))
    runtime.set_project(w.scene,p);scene_adapter.rebuild_scene(w.scene,p,runtime.get_catalog());data=p.to_dict()
    with ctx(start):
        bpy.ops.aludiy.setup_workspace()
        bpy.ops.aludiy.setup_workspace()  # A double click before Blender's notifier runs.
    yield from wait_ready()
    check(w.workspace.name==runtime.WORKSPACE_NAME,'button enters ALU DIY automatically, not Layout.001')
    check(original.name==original_name and original.as_pointer()==original_ptr,'original Layout identity and name retained')
    check(len(bpy.data.workspaces)==len(workspaces)+1,'exactly one new workspace after same-tick double click')
    check(all(bpy.data.workspaces.get(n) is not None for n in workspaces.values()),'all original workspace tabs preserved')
    check(len([a for a in original_screen.areas if a.type=='VIEW_3D'])==1,'original Layout is not split')
    check(pose(start)==before,'original Layout pose and optics unchanged')
    check(len(areas())==2,'new workspace has exactly two actual 3D areas')
    check(same() and pose(areas()[1])==before,'both views initially inherit full perspective pose and lens')
    check(areas()[0].spaces.active.shading.type=='WIREFRAME' and areas()[1].spaces.active.shading.type=='SOLID','line and solid display roles retained')
    check(all(a.spaces.active.use_local_collections for a in areas()),'per-viewport collection isolation retained')
    count=len(bpy.data.workspaces)
    with ctx(areas()[1]):bpy.ops.aludiy.setup_workspace()
    yield from wait_ready()
    check(len(bpy.data.workspaces)==count and len(areas())==2,'repeat setup reuses same workspace without extra splits')
    check(runtime.get_project(w.scene).to_dict()==data,'setup never edits engineering data')
    left,right=areas()
    with ctx(right):bpy.ops.view3d.view_persportho()
    yield;yield
    check(same(),'native perspective/orthographic toggle synchronizes without orbit')
    right.spaces.active.region_3d.view_perspective='ORTHO';yield;yield
    check(same() and left.spaces.active.region_3d.view_perspective=='ORTHO','right projection-only change synchronizes without orbit')
    left.spaces.active.region_3d.view_perspective='PERSP';yield;yield
    check(same() and right.spaces.active.region_3d.view_perspective=='PERSP','left projection-only change synchronizes without orbit')
    right.spaces.active.lens=78;yield;yield
    check(same() and left.spaces.active.lens==78,'lens-only change synchronizes')
    left.spaces.active.region_3d.view_distance=4.8;left.spaces.active.region_3d.view_location=(.2,.5,.7);yield;yield
    check(same(),'zoom and panning remain linked')
    right.spaces.active.region_3d.view_rotation=Euler((1.0,.1,.9)).to_quaternion();yield;yield
    check(same(),'rotation remains linked')
    s=runtime.settings(w.scene);s.view_sync_mode='OFF';yield
    right.spaces.active.region_3d.view_perspective='ORTHO';right.spaces.active.region_3d.view_distance=2.6;yield;yield
    check(left.spaces.active.region_3d.view_perspective=='PERSP' and left.spaces.active.region_3d.view_distance!=2.6,'OFF leaves independent projection and distance')
    s.view_sync_mode='ORIENTATION';yield;yield
    check(left.spaces.active.region_3d.view_perspective=='ORTHO','orientation mode still uses common projection')
    check(abs(left.spaces.active.region_3d.view_distance-4.8)<1e-5,'orientation mode retains independent zoom')
    s.view_sync_mode='FULL';yield;yield
    check(same(),'re-enabling FULL immediately aligns idle views')
    # Simulate old saved ALU DIY mismatch; re-enter normally, no manual toggles.
    target=w.workspace;w.workspace=original;yield;yield
    check(w.workspace==original,'ordinary workspace can be entered normally')
    left.spaces.active.region_3d.view_perspective='ORTHO';right.spaces.active.region_3d.view_perspective='PERSP'
    right.spaces.active.lens=64;right.spaces.active.region_3d.view_distance=3.6
    canonical=pose(right)
    with ctx():bpy.ops.aludiy.setup_workspace()
    yield from wait_ready()
    check(len(bpy.data.workspaces)==count,'setup from Layout reuses existing ALU DIY')
    check(same() and pose(areas()[1])==canonical,'existing mismatch repaired from right view on setup')
    w.workspace=original;yield;yield
    left.spaces.active.region_3d.view_perspective='ORTHO';right.spaces.active.region_3d.view_perspective='PERSP'
    w.workspace=target;yield;yield;yield
    check(same() and areas()[0].spaces.active.region_3d.view_perspective=='PERSP','plain workspace-tab entry aligns idle views automatically')
    # Re-registration models update/enable cycle without duplicate service instances.
    with ctx():bpy.ops.aludiy.setup_workspace()
    check(bool(v._PENDING_SETUP),'setup has one pending request before UI update')
    addon.unregister();check(not bpy.app.timers.is_registered(v.sync_tick),'disable removes synchronization timer')
    check(not v._PENDING_SETUP and not bpy.app.timers.is_registered(v._workspace_setup_tick),'disable clears pending setup and callback')
    check(v._on_file_load not in bpy.app.handlers.load_post,'disable removes lifecycle handler')
    addon.register();yield;yield
    check(sum(h is v._on_file_load for h in bpy.app.handlers.load_post)==1,'enable registers exactly one lifecycle handler')
    check(bpy.app.timers.is_registered(v.sync_tick) and same(),'enable restores one sync service and aligned views')
    for a in areas():a.spaces.active.show_region_ui=a==right
    yield
    right.spaces.active.show_region_ui=True
    next(reg for reg in right.regions if reg.type=='UI').active_panel_category='AluDIY';yield
    with ctx():
        scene_adapter.select_entity(w.scene,w.view_layer,'M-001')
    yield
    image('01-workspace-perspective.png')
    check(runtime.get_project(w.scene).to_dict()==data,'all view tests preserve project nodes and members')
    (OUT/'expected.aludiy.json').write_text(json.dumps(data,ensure_ascii=False))
    (OUT/'view.json').write_text(json.dumps(pose(right)))
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'workspace-sync.blend'))
    # Save a legacy mismatch too; register in a new GUI must repair without gesture.
    s.view_sync_mode='OFF';left.spaces.active.region_3d.view_perspective='ORTHO'
    s.view_sync_mode='FULL'
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'workspace-legacy.blend'))
    (OUT/'report.json').write_text(json.dumps(dict(status='passed',blender=bpy.app.version_string,checks=checks),ensure_ascii=False,indent=2))
    print('WORKSPACE_GUI_OK',len(checks),flush=True);addon.unregister();bpy.ops.wm.quit_blender()
seq=run()
def tick():
    try:next(seq);return .27
    except StopIteration:return None
    except Exception:
        text=traceback.format_exc();print(text,flush=True)
        (OUT/'report.json').write_text(json.dumps(dict(status='failed',checks=checks,error=text),ensure_ascii=False,indent=2))
        try:image('failure.png')
        except Exception:pass
        sys.stdout.flush();os._exit(1)
bpy.app.timers.register(tick,first_interval=1.0)
