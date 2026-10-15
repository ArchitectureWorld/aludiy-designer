"""Actual Blender registration, preview/cancel, topology and command tests."""
from pathlib import Path
import sys
import json
import ast
import bpy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'extension'))
import aludiy_designer as addon
from aludiy_designer import runtime, scene_adapter
from aludiy_designer.vendor.aludiy_core import Project, Member, Node

def frame():
    p=Project('P-MOVE','alpha-2026.10')
    for nid,xyz in [('N-001',(0,0,800)),('N-002',(1200,0,800)),('N-003',(0,600,800)),('N-004',(0,0,0))]: p.add_node(Node(nid,xyz))
    for mid,a,b in [('M-001','N-001','N-002'),('M-002','N-001','N-003'),('M-003','N-004','N-001')]: p.add_member(Member(mid,a,b,'generic:tslot-2020@0.1'))
    return p

def reset():
    p=frame(); runtime.set_project(bpy.context.scene,p); scene_adapter.rebuild_scene(bpy.context.scene,p,runtime.get_catalog())
    bpy.context.view_layer.update()
    bpy.ops.object.select_all(action="DESELECT")
    return p

# Validate UI constants against the real runtime; a single invalid icon can
# abort panel drawing and hide the controls that follow it.
icons = bpy.types.UILayout.bl_rna.functions['label'].parameters['icon'].enum_items.keys()
for file in [(ROOT/'extension'/'aludiy_designer'/'panels.py')]:
    for node in ast.walk(ast.parse(file.read_text())):
        if isinstance(node, ast.keyword) and node.arg == 'icon' and isinstance(node.value, ast.Constant):
            assert node.value.value in icons, f'Invalid Blender UI icon: {file.name}: {node.value.value}'
addon.register()
try:
    p=reset()
    assert hasattr(addon,'g_move'), 'engineering G module not implemented'
    from aludiy_designer import g_move
    window=bpy.context.window
    area=next(a for a in window.screen.areas if a.type=='VIEW_3D')
    region=next(r for r in area.regions if r.type=='WINDOW')
    with bpy.context.temp_override(window=window,area=area,region=region):
        ctx=bpy.context
        # Direct entry works even when the detailed information panel is closed.
        scene_adapter.select_entity(ctx.scene,ctx.view_layer,'M-003')
        assert bpy.ops.aludiy.select_endpoint(endpoint='END')=={'FINISHED'}
        assert g_move.endpoint_context(ctx)==('M-003','END')
        before=runtime.settings(ctx.scene).project_json
        preview=addon.g_move.build_candidate(ctx,(0,0,100),detach=False)
        object_ids={o.name:o.as_pointer() for o in ctx.scene.objects if o.get('aludiy_managed')}
        g_move.update_preview_geometry(ctx.scene,preview.project,preview.affected_member_ids)
        assert runtime.settings(ctx.scene).project_json==before, 'preview wrote authoritative state'
        assert object_ids=={o.name:o.as_pointer() for o in ctx.scene.objects if o.get('aludiy_managed')}, 'preview destroyed object identity'
        g_move.update_preview_geometry(ctx.scene,p,preview.affected_member_ids)
        assert runtime.settings(ctx.scene).project_json==before
        assert bpy.ops.aludiy.move_engineering(delta_mm=(0,0,100))=={'FINISHED'}
        assert runtime.get_project(ctx.scene).nodes['N-001'].position_mm==(0,0,900)
        assert len(runtime.get_project(ctx.scene).nodes)==4
        reset(); scene_adapter.select_entity(ctx.scene,ctx.view_layer,'M-003')
        bpy.ops.aludiy.select_endpoint(endpoint='END')
        assert bpy.ops.aludiy.move_engineering(delta_mm=(0,0,100),detach=True)=={'FINISHED'}
        p=runtime.get_project(ctx.scene); new=p.members['M-003'].end_node_id
        assert new!='N-001' and p.nodes['N-001'].position_mm==(0,0,800)
        assert p.nodes[new].position_mm==(0,0,900)
        assert len(p.nodes)==5
        reset(); scene_adapter.select_entity(ctx.scene,ctx.view_layer,'M-001')
        assert bpy.ops.aludiy.move_engineering(delta_mm=(10,20,30))=={'FINISHED'}
        p=runtime.get_project(ctx.scene)
        assert p.nodes['N-001'].position_mm==(10,20,830)
        assert p.nodes['N-002'].position_mm==(1210,20,830)
        # Only engineering context claims G. Plain objects retain native G.
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.mesh.primitive_cube_add()
        assert not g_move.ALUDIY_OT_move_engineering.poll(ctx)
        # Cross-viewport synchronization must not erase Shift multiselection.
        reset(); scene_adapter.select_entity(ctx.scene,ctx.view_layer,'M-001')
        addon.view_sync._sync_selection(ctx.window)
        second=next(o for o in ctx.scene.objects if o.get('aludiy_entity_type')=='MEMBER_AXIS' and o.get('aludiy_entity_id')=='M-002')
        second.select_set(True); ctx.view_layer.objects.active=second
        addon.view_sync._sync_selection(ctx.window)
        selected={o.get('aludiy_entity_id') for o in ctx.scene.objects if o.select_get() and o.get('aludiy_managed')}
        assert selected=={'M-001','M-002'}, selected
        # Mixed selection is explicitly rejected, not partially transformed.
        cube=bpy.data.objects['Cube']; cube.hide_set(False); cube.select_set(True)
        try:
            g_move.target_spec(ctx)
            raise AssertionError('Mixed selection was accepted')
        except addon.g_move.ValidationError:
            pass
        cube.select_set(False)
        # Reload must not duplicate keymaps.
        g_move.register_services(); g_move.register_services()
        km=ctx.window_manager.keyconfigs.addon
        keys=[k for m in km.keymaps for k in m.keymap_items if k.idname=='aludiy.move_engineering'] if km else []
        if km: assert len(keys)==1,len(keys)
    print('ALUDIY_MOVE_SMOKE_OK: selection,keep,detach,preview,cancel_restore,normal_object_guard,register_idempotence')
finally:
    addon.unregister()
