"""Real Blender backend checks for reconnection transactions and selection."""
from pathlib import Path
import sys
import bpy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'extension'))
import aludiy_designer as addon
from aludiy_designer import runtime,scene_adapter,g_move
from aludiy_designer.vendor.aludiy_core import Project,Member,Node


def model():
    p=Project('P-SNAP-TEST','alpha-2026.10')
    for nid,xyz in [('N-001',(0,0,800)),('N-002',(1200,0,800)),('N-003',(0,600,800)),
                    ('N-004',(0,0,0)),('N-005',(200,0,900)),('N-006',(800,0,900))]:
        p.add_node(Node(nid,xyz))
    for mid,a,b in [('M-001','N-001','N-002'),('M-002','N-001','N-003'),('M-003','N-004','N-001'),('M-004','N-005','N-006')]:
        p.add_member(Member(mid,a,b,'generic:tslot-2020@0.1'))
    return p

addon.register()
try:
    props=bpy.ops.aludiy.move_engineering.get_rna_type().properties
    assert 'snap_target_node_id' in props, 'G reconnection not integrated'
    window=bpy.context.window
    area=next(a for a in window.screen.areas if a.type=='VIEW_3D')
    reg=next(r for r in area.regions if r.type=='WINDOW')
    with bpy.context.temp_override(window=window,area=area,region=reg):
        c=bpy.context
        p=model(); runtime.set_project(c.scene,p);scene_adapter.rebuild_scene(c.scene,p,runtime.get_catalog())
        scene_adapter.select_entity(c.scene,c.view_layer,'M-003')
        bpy.ops.aludiy.select_endpoint(endpoint='END')
        assert bpy.ops.aludiy.move_engineering(delta_mm=(200,0,100),detach=True,
              snap_target_node_id='N-005',snap_anchor_node_id='N-001')=={'FINISHED'}
        result=runtime.get_project(c.scene)
        assert result.members['M-003'].end_node_id=='N-005'
        assert result.members['M-001'].start_node_id=='N-001'
        assert g_move.endpoint_context(c)==('M-003','END')
        # Moving the reconnected junction must now update both rods.
        assert bpy.ops.aludiy.move_engineering(delta_mm=(0,0,50))=={'FINISHED'}
        result=runtime.get_project(c.scene)
        assert result.nodes['N-005'].position_mm==(200,0,950)
        # Reconnecting at zero displacement must not be dropped as a no-op.
        p=model(); p.add_node(Node('N-007',(0,0,800)));p.members['M-003'].end_node_id='N-007'
        runtime.set_project(c.scene,p);scene_adapter.rebuild_scene(c.scene,p,runtime.get_catalog())
        scene_adapter.select_entity(c.scene,c.view_layer,'M-003');bpy.ops.aludiy.select_endpoint(endpoint='END')
        assert bpy.ops.aludiy.move_engineering(delta_mm=(0,0,0),snap_target_node_id='N-001',snap_anchor_node_id='N-007')=={'FINISHED'}
        assert 'N-007' not in runtime.get_project(c.scene).nodes
        # A redundant detach-and-return must not leave DETACH armed.
        runtime.settings(c.scene).move_connection_mode='DETACH'
        assert bpy.ops.aludiy.move_engineering(delta_mm=(0,0,0),detach=True,
            snap_target_node_id='N-001',snap_anchor_node_id='N-001')=={'CANCELLED'}
        assert runtime.settings(c.scene).move_connection_mode=='KEEP', 'no-op left DETACH armed'
        # Failure does not mutate the authoritative project.
        before=runtime.settings(c.scene).project_json
        assert bpy.ops.aludiy.move_engineering(delta_mm=(0,0,-800),snap_target_node_id='N-004',snap_anchor_node_id='N-001')=={'CANCELLED'}
        assert runtime.settings(c.scene).project_json==before
        bpy.ops.object.select_all(action='DESELECT');bpy.ops.mesh.primitive_cube_add()
        assert not g_move.ALUDIY_OT_move_engineering.poll(c)
    print('ALUDIY_SNAP_BACKEND_OK: detach_reconnect,followup_propagation,coincident_join,collapse_guard,ordinary_object_guard')
finally: addon.unregister()
