"""Background operator boundary test; native popup is covered by the GUI suite."""
import sys,json
from pathlib import Path
import bpy
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'extension'))
import aludiy_designer as addon
from aludiy_designer import runtime,scene_adapter,g_move
from aludiy_designer.vendor.aludiy_core import Project,Node,Member
from aludiy_designer.vendor.aludiy_core.joints import solve_cutbacks
addon.register()
assert hasattr(bpy.types,'ALUDIY_OT_edit_joint_options'), 'missing native joint editor operator'
p=Project('P-EDITOR-NATIVE','alpha-2026.10')
for nid,pt in [('N0',(0,0,500)),('N1',(500,0,500)),('N2',(0,500,500)),('N3',(0,0,0))]:p.add_node(Node(nid,pt))
for mid,a,b in [('M-001','N0','N1'),('M-002','N0','N2'),('M-003','N0','N3')]:p.add_member(Member(mid,a,b,'generic:tslot-2020@0.1'))
runtime.set_project(bpy.context.scene,p);scene_adapter.rebuild_scene(bpy.context.scene,p,runtime.get_catalog())
bpy.ops.object.select_all(action='DESELECT')
for obj in bpy.context.scene.objects:
    if obj.get('aludiy_entity_type')=='MEMBER_AXIS':obj.select_set(True);bpy.context.view_layer.objects.active=obj
before=p.to_dict()
result=bpy.ops.aludiy.edit_joint_options('EXEC_DEFAULT',host_member_id='M-003',gap_input='2mm')
assert result=={'FINISHED'},result
q=runtime.get_project(bpy.context.scene)
assert len(q.joints)==2 and q.to_dict()['nodes']==before['nodes']
assert solve_cutbacks(q,runtime.get_catalog(),strict=True).lengths['M-001'].cut_length_mm==488
assert len(g_move.selection_summary(bpy.context)[0])==3
result=bpy.ops.aludiy.edit_joint_options('EXEC_DEFAULT',host_member_id='M-001',gap_input='1')
assert result=={'FINISHED'} and len(runtime.get_project(bpy.context.scene).joints)==2
from aludiy_designer import joint_editor
assert joint_editor._ACTIVE is None
print('JOINT_EDITOR_BACKGROUND_OK')
addon.unregister()
