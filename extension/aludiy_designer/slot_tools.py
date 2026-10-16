"""Explicit slot targeting; target selection never changes engineering geometry."""
import bpy
from . import runtime, g_move
from .vendor.aludiy_core.associations import slot_reference
from .vendor.aludiy_core.profile_editing import interface_rails
from .vendor.aludiy_core.errors import ValidationError

_HANDLE = None


def clear_target(scene):
    s=runtime.settings(scene)
    for field in ('slot_target_member_id','slot_target_interface_id','slot_target_profile_id','slot_target_catalog_revision'):
        setattr(s,field,'')


def target_spec(scene, project):
    s=runtime.settings(scene)
    if not s.slot_target_member_id:
        return None
    ref=slot_reference(project,s.slot_target_member_id,s.slot_target_interface_id,runtime.get_catalog())
    if ref.profile_type_id!=s.slot_target_profile_id or ref.catalog_revision!=s.slot_target_catalog_revision:
        raise ValidationError('槽轨目标已经换型或目录改变；请清除目标并重新指定，不按同名槽自动匹配')
    return (s.slot_target_member_id,s.slot_target_interface_id)


class ALUDIY_OT_set_slot_target(bpy.types.Operator):
    bl_idname='aludiy.set_slot_target'
    bl_label='设为槽轨定位目标'
    bl_description='固定当前检查的 Member/Interface，供画线和 G 定位；不会自动创建工程关联'

    @classmethod
    def poll(cls,context):
        from . import profile_tools, operators
        if context.mode!='OBJECT' or g_move._ACTIVE or operators._ACTIVE_DRAW:return False
        mid=profile_tools.active_inspector_member(context)
        if not mid:return False
        try:return bool(profile_tools.selected_slot(context.scene,mid,runtime.get_project(context.scene)))
        except Exception:return False

    def execute(self,context):
        from . import profile_tools
        try:
            p=runtime.get_project(context.scene); mid=profile_tools.active_inspector_member(context)
            sid=profile_tools.selected_slot(context.scene,mid,p)
            ref=slot_reference(p,mid,sid,runtime.get_catalog())
            s=runtime.settings(context.scene)
            s.slot_target_member_id=mid;s.slot_target_interface_id=sid
            s.slot_target_profile_id=ref.profile_type_id;s.slot_target_catalog_revision=ref.catalog_revision
            runtime.set_status(context.scene,f'定位目标 {mid} / {sid} · 先吸附，再手动创建关联')
            g_move._redraw();return {'FINISHED'}
        except Exception as exc:
            self.report({'WARNING'},str(exc));return {'CANCELLED'}


class ALUDIY_OT_clear_slot_target(bpy.types.Operator):
    bl_idname='aludiy.clear_slot_target'
    bl_label='清除槽轨目标'
    bl_description='恢复普通端点/杆身吸附；不解除任何工程关联'
    @classmethod
    def poll(cls,context):
        from . import operators
        return g_move._ACTIVE is None and operators._ACTIVE_DRAW is None
    def execute(self,context):
        clear_target(context.scene)
        runtime.set_status(context.scene,'已恢复普通吸附；已有槽轨关联保留')
        g_move._redraw();return {'FINISHED'}


def draw_panel(layout,context):
    box=layout.box();box.label(text='槽轨定位与附着',icon='SNAP_EDGE')
    s=runtime.settings(context.scene)
    if s.slot_target_member_id:
        box.label(text=f'主杆 {s.slot_target_member_id} · 指定槽轨')
        box.label(text=s.slot_target_interface_id)
        try:target_spec(context.scene,g_move.display_project(context.scene))
        except Exception:
            row=box.row();row.alert=True;row.label(text='目标失效，请清除后重新指定',icon='ERROR')
        row=box.row(align=True)
        row.operator('aludiy.create_associations',text='创建槽轨关联',icon='LINKED')
        row.operator('aludiy.clear_slot_target',text='清除目标',icon='X')
        box.label(text='选端点 → G 定位 → 创建关联')
        box.label(text='清除目标 ≠ 解除关联；Ctrl 临时自由')
    else:
        box.label(text='检查主杆槽位 → 设为定位目标')
        box.label(text='相接杆件多选 → 创建关联（仅唯一匹配）')
    box.label(text='槽轨按相对站位跟随；不校验接头适配')
    p=g_move.display_project(context.scene);mids,nids=g_move.selection_summary(context)
    ends=set(nids)
    for mid in mids:
        if mid in p.members:ends.update((p.members[mid].start_node_id,p.members[mid].end_node_id))
    linked=[r for r in p.associations.values() if r.kind=='ON_SLOT' and
            (r.host_member_id in mids or r.follower_node_id in ends)]
    if linked:
        box.label(text=f'相关槽轨关联 {len(linked)} 处',icon='LINKED')
        for r in linked[:3]:
            box.label(text=f'{r.follower_node_id} → {r.host_member_id} · {r.station*100:g}%')
            box.label(text=r.slot_reference.interface_id)
        box.operator('aludiy.remove_associations',text='解除所选关联（保留位置）')


def _draw_target():
    c=bpy.context
    if not (c.area and c.area.type=='VIEW_3D' and c.region and c.region.type=='WINDOW'
            and c.region_data and c.workspace.name==runtime.WORKSPACE_NAME):return
    s=runtime.settings(c.scene)
    if not s.slot_target_member_id:return
    from . import viewport_overlay as ov
    import gpu
    try:
        p=g_move.display_project(c.scene)
        target=target_spec(c.scene,p)
        rail=next(r for r in interface_rails(p,target[0],runtime.get_catalog()) if r.interface_id==target[1])
        a,b=ov._project(rail.start_mm),ov._project(rail.end_mm)
        if a is None or b is None:return
        gpu.state.blend_set('ALPHA')
        ov._polyline([tuple(a),tuple(b)],color=(1,.72,.12,1),width=3)
        ov.draw_snap_marker(tuple((a+b)*.5),color=(1,.72,.12,1))
        ov._text(72,98,f'目标槽轨 {target[0]} / {target[1]} · 仅定位',size=12,color=(1,.82,.4,1))
    except (ValidationError, StopIteration):
        # Stale target is visible and cannot silently become a different interface.
        gpu.state.blend_set('ALPHA')
        ov._text(72,98,'槽轨目标失效：请在面板清除或重新指定',size=12,color=(1,.4,.25,1))
    except Exception as exc:
        print(f'AluDIY slot target overlay: {exc}')
    finally:gpu.state.blend_set('NONE')


def register_services():
    global _HANDLE
    if _HANDLE is None:_HANDLE=bpy.types.SpaceView3D.draw_handler_add(_draw_target,(), 'WINDOW','POST_PIXEL')


def unregister_services():
    global _HANDLE
    if _HANDLE is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_HANDLE,'WINDOW');_HANDLE=None

CLASSES=(ALUDIY_OT_set_slot_target,ALUDIY_OT_clear_slot_target)
