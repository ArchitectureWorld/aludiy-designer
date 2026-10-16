"""Start a fresh real GUI on a saved mismatched workspace; no navigation gestures."""
import bpy,sys,os,json,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'extension'))
import aludiy_designer as addon
from aludiy_designer import view_sync as v,runtime
OUT=Path(os.environ['ALUDIY_EVIDENCE_DIR'])
def verify():
    try:
        w=bpy.context.window;areas=sorted((a for a in w.screen.areas if a.type=='VIEW_3D'),key=lambda a:a.x)
        assert w.workspace.name==runtime.WORKSPACE_NAME
        assert len(areas)==2
        assert not v._different(v._capture(areas[0]),v._capture(areas[1]))
        assert areas[0].spaces.active.region_3d.view_perspective=='PERSP'
        assert runtime.get_project(w.scene).to_dict()==json.loads((OUT/'expected.aludiy.json').read_text())
        assert not v._PENDING_SETUP
        print('WORKSPACE_FRESH_GUI_REOPEN_OK',bpy.data.filepath,flush=True)
        addon.unregister();bpy.ops.wm.quit_blender()
    except Exception:
        traceback.print_exc();sys.stdout.flush();os._exit(1)
    return None
def start():
    addon.register();bpy.app.timers.register(verify,first_interval=.8);return None
bpy.app.timers.register(start,first_interval=1)
