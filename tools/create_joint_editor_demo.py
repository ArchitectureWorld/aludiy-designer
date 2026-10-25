"""Generate two isolated tabletop-frame acceptance files from a verified UI layout."""
from pathlib import Path
import os,sys,json,math
import bpy
from mathutils import Euler,Vector
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'extension'))
import aludiy_designer as addon
addon.register()
from aludiy_designer import runtime,scene_adapter,view_sync
from aludiy_designer.vendor.aludiy_core import Project,Member,Node
from aludiy_designer.vendor.aludiy_core.joint_editor import apply_joint_choice
from aludiy_designer.vendor.aludiy_core.joints import solve_cutbacks
out=Path(os.environ['ALUDIY_DEMO_DIR']);out.mkdir(parents=True,exist_ok=True)
p=Project('P-DESK-JUNCTION-PHASE1','alpha-2026.10')
def member(mid,a,b):
    p.add_node(Node(mid+'-A',a));p.add_node(Node(mid+'-B',b));p.add_member(Member(mid,mid+'-A',mid+'-B','generic:tslot-2020@0.1'))
for i,(x,y) in enumerate(((0,0),(1200,0),(1200,600),(0,600)),1):member(f'L{i}',(x,y,0),(x,y,750))
member('X1',(0,0,750),(1200,0,750));member('X2',(0,600,750),(1200,600,750))
member('Y1',(0,0,750),(0,600,750));member('Y2',(1200,0,750),(1200,600,750))
scene=bpy.context.scene

def save(project,name):
    runtime.set_project(scene,project);scene_adapter.rebuild_scene(scene,project,runtime.get_catalog())
    for o in scene.objects:
        o.select_set(False)
        if o.get('aludiy_entity_type')=='MEMBER_AXIS' and o.get('aludiy_entity_id') in ('L1','X1','Y1'):
            o.select_set(True);bpy.context.view_layer.objects.active=o
    s=runtime.settings(scene);s.endpoint_member_id='';s.endpoint_side='';s.joint_gap_input='0'
    s.status_message='选择 L1 / X1 / Y1 → 中键 → 交接处理 → 预览 / 切换 L·T·三向方案'
    view_sync._LAST_SELECTED_BY_WINDOW.clear()
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':
                space=area.spaces.active;rv=space.region_3d
                rv.view_rotation=Euler((math.radians(66),0,math.radians(32))).to_quaternion()
                rv.view_location=Vector((.6,.3,.375));rv.view_distance=2.7;rv.view_perspective='PERSP'
    (out/(name+'.aludiy.json')).write_text(json.dumps(project.to_dict(),ensure_ascii=False,indent=2))
    bpy.ops.wm.save_as_mainfile(filepath=str(out/(name+'.blend')))

save(p,'桌架交接第一阶段测试')
q=p
for leg,x,y in [('L1','X1','Y1'),('L2','X1','Y2'),('L3','X2','Y2'),('L4','X2','Y1')]:
    q=apply_joint_choice(q,runtime.get_catalog(),member_ids=(leg,x,y),host_member_id=leg).project
assert len(q.joints)==8 and not solve_cutbacks(q,runtime.get_catalog()).issues
assert [n.position_mm for n in q.nodes.values()]==[n.position_mm for n in p.nodes.values()]
save(q,'桌架四角已处理示例')
print('DESK_JUNCTION_DEMOS_OK')
addon.unregister()
