"""Explicit slot targeting; target selection never changes engineering geometry."""
import json
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


def sanitize_missing_target(scene, project):
    """Event/command boundary only: discard a deleted host's ephemeral target.

    This is NOT engineering-data repair. Read-only draw callers keep target_spec;
    schema, catalog and valid-host interface failures are still reported normally.
    """
    s = runtime.settings(scene)
    mid = s.slot_target_member_id
    if not mid or mid in project.members:
        return False
    clear_target(scene)
    if s.inspected_member_id and s.inspected_member_id not in project.members:
        s.inspected_member_id = s.inspected_profile_id = s.inspected_interface_id = ''
    if s.endpoint_member_id and s.endpoint_member_id not in project.members:
        s.endpoint_member_id = s.endpoint_side = ''
    runtime.set_status(scene, '槽轨目标主杆已删除，已恢复普通吸附；其他有效工程关联保留')
    return True


def snapping_target(scene, project):
    sanitize_missing_target(scene, project)
    return target_spec(scene, project)


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
    bl_label='停止槽轨定位（保留关联）'
    bl_description='恢复普通端点/杆身吸附；不解除任何工程关联'
    @classmethod
    def poll(cls,context):
        from . import operators
        return g_move._ACTIVE is None and operators._ACTIVE_DRAW is None
    def execute(self,context):
        s=runtime.settings(context.scene)
        count=len(slot_links(runtime.get_project(context.scene),s.slot_target_member_id,s.slot_target_interface_id))
        clear_target(context.scene)
        runtime.set_status(context.scene,f'已停止槽轨定位；仍有 {count} 处该槽工程关联。需要独立移动请点“解除所选”或“解除此槽”')
        g_move._redraw();return {'FINISHED'}


def slot_links(project, host_member_id, interface_id):
    return tuple(r for r in project.associations.values() if r.kind == 'ON_SLOT'
                 and r.host_member_id == host_member_id
                 and r.slot_reference.interface_id == interface_id)


def selected_links(context, project):
    mids, nids = g_move.selection_summary(context)
    ends = set(nids)
    for mid in mids:
        if mid in project.members:
            m = project.members[mid]; ends.update((m.start_node_id, m.end_node_id))
    return tuple(r for r in project.associations.values() if
                 (r.kind == 'COINCIDENT' and set(r.node_ids) & ends)
                 or (r.kind in {'ON_SLOT', 'ON_MEMBER'} and
                     (r.host_member_id in mids or r.follower_node_id in ends)))


class ALUDIY_OT_unlink_slot(bpy.types.Operator):
    bl_idname = 'aludiy.unlink_slot'
    bl_label = '解除此槽工程关联'
    bl_description = '真正解除这个主杆/槽位的全部附着端，保留设计线位置；不影响其他槽'
    bl_options = {'REGISTER', 'UNDO'}
    host_member_id: bpy.props.StringProperty(options={'SKIP_SAVE'})
    interface_id: bpy.props.StringProperty(options={'SKIP_SAVE'})
    expected_links: bpy.props.StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        from . import profile_tools
        return context.mode == 'OBJECT' and not profile_tools._busy()

    def _links(self, context):
        return slot_links(runtime.get_project(context.scene), self.host_member_id, self.interface_id)

    def invoke(self, context, event):
        try:
            links = self._links(context)
            if not links:
                runtime.set_status(context.scene, '这个槽没有工程关联；不需要解除')
                return {'CANCELLED'}
            self.expected_links = json.dumps([r.to_dict() for r in links], sort_keys=True)
            return context.window_manager.invoke_props_dialog(self, width=365)
        except Exception as exc:
            self.report({'WARNING'}, str(exc)); return {'CANCELLED'}

    def draw(self, context):
        self.layout.label(text=f'主杆 {self.host_member_id} / {self.interface_id}')
        self.layout.label(text=f'解除这个槽上的 {len(self._links(context))} 处附着关系？', icon='UNLINKED')
        self.layout.label(text='保留端点位置，不影响其他槽；Ctrl+Z 可恢复。')

    def execute(self, context):
        try:
            from .vendor.aludiy_core.associations import remove_slot_associations
            original = runtime.get_project(context.scene)
            links = slot_links(original, self.host_member_id, self.interface_id)
            if self.expected_links and self.expected_links != json.dumps([r.to_dict() for r in links], sort_keys=True):
                raise ValidationError('确认期间工程关系已变化，请重新操作')
            result = remove_slot_associations(original, host_member_id=self.host_member_id,
                                              interface_id=self.interface_id)
            if not result.changed_count:
                runtime.set_status(context.scene, '这个槽没有待解除的关联'); return {'CANCELLED'}
            # Selection context is captured/restored by the existing transaction path.
            g_move._commit_relations(context, original, result.project, g_move.target_spec(context))
            runtime.set_status(context.scene, f'已解除此槽 {result.changed_count} 处工程关联；位置保留，该槽约束已解除（其他已有约束仍保留）')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'WARNING'}, str(exc)); runtime.set_status(context.scene, str(exc))
            return {'CANCELLED'}


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

    except (ValidationError, StopIteration):
        # Stale target is visible and cannot silently become a different interface.
        pass  # Console displays invalid targets; no floating text in model area.
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

CLASSES=(ALUDIY_OT_set_slot_target,ALUDIY_OT_clear_slot_target,ALUDIY_OT_unlink_slot)
