"""Explicit slot targeting; target selection never changes engineering geometry."""
import json
import bpy
from . import runtime, g_move
from .vendor.aludiy_core.associations import slot_reference
from .vendor.aludiy_core.profile_editing import interface_rails
from .vendor.aludiy_core.errors import ValidationError
from .vendor.aludiy_core import slot_selection as choice_model

_HANDLE = None


def _active_records(scene):
    s = runtime.settings(scene)
    records = choice_model.decode_targets(getattr(s, 'slot_targets_json', ''))
    if records:
        return records
    if s.slot_target_member_id:
        return (choice_model.SlotTarget(s.slot_target_member_id, s.slot_target_interface_id,
                s.slot_target_profile_id, s.slot_target_catalog_revision),)
    return ()


def selected_records(scene):
    """Read-only, including legacy single-target projects and untouched scenes."""
    s = runtime.settings(scene)
    raw = getattr(s, 'slot_selection_json', '')
    return choice_model.decode_targets(raw) if raw else _active_records(scene)


def _write_active(scene, records):
    s = runtime.settings(scene)
    s.slot_targets_json = choice_model.encode_targets(records)
    fields = ('slot_target_member_id', 'slot_target_interface_id',
              'slot_target_profile_id', 'slot_target_catalog_revision')
    first = records[0] if records else None
    values = (first.member_id, first.interface_id, first.profile_type_id,
              first.catalog_revision) if first else ('', '', '', '')
    for field, value in zip(fields, values):
        setattr(s, field, value)


def clear_target(scene):
    """Stop using rails for snapping; keep the chosen set and engineering edges."""
    # Materialize legacy selection before clearing its compatibility fields.
    s = runtime.settings(scene)
    if not getattr(s, 'slot_selection_json', '') and s.slot_target_member_id:
        try:
            s.slot_selection_json = choice_model.encode_targets(_active_records(scene))
        except ValidationError:
            pass  # An invalid ephemeral legacy target can still be stopped.
    _write_active(scene, ())


def clear_selection(scene):
    """Explicit UI reset, never an engineering data repair operation."""
    _write_active(scene, ())
    runtime.settings(scene).slot_selection_json = '[]'


def target_specs(scene, project):
    return choice_model.validated_pairs(project, runtime.get_catalog(), _active_records(scene))


def target_spec(scene, project):
    """Compatibility view for callers which only display the primary target."""
    targets = target_specs(scene, project)
    return targets[0] if targets else None


def select_inset_slot(scene, project, member_id, interface_id, *, extend=False):
    target = choice_model.make_target(project, runtime.get_catalog(), member_id, interface_id)
    # A plain click also recovers a malformed choice set, without clearing the
    # independent active target snapshot or any engineering data.
    records = selected_records(scene) if extend else ()
    runtime.settings(scene).slot_selection_json = choice_model.encode_targets(
        choice_model.select_target(records, target, extend=extend))


def activate_selection(scene, project):
    records = selected_records(scene)
    if not records:
        raise ValidationError('请先点击截面选槽，Shift+单击追加多条槽轨')
    choice_model.validated_pairs(project, runtime.get_catalog(), records)
    _write_active(scene, records)


def remove_chosen_slot(scene, member_id, interface_id):
    key = (member_id, interface_id)
    chosen = tuple(r for r in selected_records(scene) if r.key != key)
    active = tuple(r for r in _active_records(scene) if r.key != key)
    runtime.settings(scene).slot_selection_json = choice_model.encode_targets(chosen)
    _write_active(scene, active)


def sanitize_missing_target(scene, project):
    """At event/command boundaries prune only deleted hosts from both UI sets."""
    s = runtime.settings(scene)
    legacy_removed = False
    # Old saved settings may contain only a stale host ID with no profile data.
    if (s.slot_target_member_id and s.slot_target_member_id not in project.members
            and not choice_model.decode_targets(getattr(s, 'slot_targets_json', ''))):
        _write_active(scene, ())
        legacy_removed = True
    active, chosen = _active_records(scene), selected_records(scene)
    kept_active = choice_model.without_missing_hosts(project, active)
    kept_chosen = choice_model.without_missing_hosts(project, chosen)
    if not legacy_removed and active == kept_active and chosen == kept_chosen:
        return False
    removed = len({r.key for r in active + chosen if r.member_id not in project.members}) + int(legacy_removed)
    _write_active(scene, kept_active)
    s.slot_selection_json = choice_model.encode_targets(kept_chosen)
    if s.inspected_member_id and s.inspected_member_id not in project.members:
        s.inspected_member_id = s.inspected_profile_id = s.inspected_interface_id = ''
    if s.endpoint_member_id and s.endpoint_member_id not in project.members:
        s.endpoint_member_id = s.endpoint_side = ''
    mode = '仅所选槽轨' if kept_active and getattr(s,'slot_only',False) else '普通吸附可用'
    runtime.set_status(scene, f'已清理 {removed} 条已删除主杆的槽轨目标；保留 {len(kept_active)} 条定位槽轨，{mode}；工程关联不变')
    return True


def snapping_targets(scene, project):
    sanitize_missing_target(scene, project)
    return target_specs(scene, project)


def snapping_target(scene, project):
    targets = snapping_targets(scene, project)
    return targets[0] if targets else None


def choice_pairs(scene):
    return tuple(r.key for r in selected_records(scene))


def target_state(scene):
    """Guard deferred commands against selection, mode or target changes."""
    s = runtime.settings(scene)
    return (getattr(s,'slot_selection_json',''), getattr(s,'slot_targets_json',''),
            s.slot_target_member_id, s.slot_target_interface_id, s.slot_target_profile_id,
            s.slot_target_catalog_revision, bool(getattr(s,'slot_only',False)))


def links_for_targets(project, pairs):
    keys = set(choice_model.normalize_pairs(pairs))
    return tuple(r for r in project.associations.values() if r.kind == 'ON_SLOT'
                 and (r.host_member_id, r.slot_reference.interface_id) in keys)


class ALUDIY_OT_set_slot_target(bpy.types.Operator):
    bl_idname='aludiy.set_slot_target'
    bl_label='设为槽轨定位目标'
    bl_description='固定当前检查的 Member/Interface，供画线和 G 定位；不会自动创建工程关联'

    @classmethod
    def poll(cls,context):
        from . import profile_tools
        if context.mode != 'OBJECT' or profile_tools._busy():
            return False
        try:
            return bool(selected_records(context.scene))
        except ValidationError:
            return False

    def execute(self,context):
        try:
            project = runtime.get_project(context.scene)
            sanitize_missing_target(context.scene, project)
            activate_selection(context.scene, project)
            count = len(target_specs(context.scene, project))
            mode = '仅所选槽轨' if runtime.settings(context.scene).slot_only else '普通杆件 + 槽轨'
            runtime.set_status(context.scene,f'已启用 {count} 条槽轨定位 · {mode} · 不自动创建关联')
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
        try:
            p = runtime.get_project(context.scene)
            count = len(links_for_targets(p, (r.key for r in _active_records(context.scene))))
            clear_target(context.scene)
            runtime.set_status(context.scene,f'已停止槽轨定位；仍有 {count} 处这些槽的工程关联。需要独立移动请点“解除所选”或“解除所选槽关联”')
            g_move._redraw();return {'FINISHED'}
        except Exception as exc:
            self.report({'WARNING'},str(exc));return {'CANCELLED'}


class ALUDIY_OT_manage_slot_selection(bpy.types.Operator):
    bl_idname = 'aludiy.manage_slot_selection'
    bl_label = '管理槽轨选择'
    bl_description = '只管理定位/选择范围，不创建或删除工程关系'
    action: bpy.props.EnumProperty(items=(('REMOVE','移除当前槽',''),('CLEAR','清空槽轨选择',''),
        ('MODE','切换普通+槽轨 / 仅所选槽轨','')), default='REMOVE')

    @classmethod
    def poll(cls,context):
        from . import profile_tools
        return context.mode == 'OBJECT' and not profile_tools._busy()

    def execute(self,context):
        from . import profile_tools
        try:
            s = runtime.settings(context.scene)
            if self.action == 'CLEAR':
                clear_selection(context.scene)
                runtime.set_status(context.scene,'槽轨选择与定位目标已清空；工程关联全部保留')
            elif self.action == 'MODE':
                s.slot_only = not s.slot_only
                mode = '仅吸附所选槽轨' if s.slot_only else '普通杆件 + 所选槽轨共同吸附'
                runtime.set_status(context.scene, mode + '；无定位目标时使用普通吸附')
            else:
                p = runtime.get_project(context.scene)
                mid = profile_tools.active_inspector_member(context)
                sid = profile_tools.selected_slot(context.scene,mid,p)
                if not mid or not sid:
                    raise ValidationError('请先点选要移除的当前槽')
                remove_chosen_slot(context.scene,mid,sid)
                runtime.set_status(context.scene, f'已从选择/定位集合移除 {mid} / {sid}；工程关联保留')
            g_move._redraw();return {'FINISHED'}
        except Exception as exc:
            self.report({'WARNING'},str(exc));runtime.set_status(context.scene,str(exc));return {'CANCELLED'}


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



class ALUDIY_OT_unlink_slots(bpy.types.Operator):
    bl_idname = 'aludiy.unlink_slots'
    bl_label = '解除所选槽轨工程关联'
    bl_description = '确认后解除所选精确主杆/槽位上的附着关系，保留其他槽与端点位置'
    bl_options = {'REGISTER','UNDO'}
    targets_json: bpy.props.StringProperty(default='',options={'HIDDEN','SKIP_SAVE'})
    expected_project: bpy.props.StringProperty(default='',options={'HIDDEN','SKIP_SAVE'})
    expected_state: bpy.props.StringProperty(default='',options={'HIDDEN','SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        from . import profile_tools
        return context.mode == 'OBJECT' and not profile_tools._busy()

    def _pairs(self, context):
        return choice_model.normalize_pairs(json.loads(self.targets_json)) if self.targets_json else choice_pairs(context.scene)

    def invoke(self, context, event):
        try:
            pairs = self._pairs(context)
            p = runtime.get_project(context.scene)
            links = links_for_targets(p, pairs)
            if not links:
                runtime.set_status(context.scene,'所选槽轨没有工程关联；无需解除')
                return {'CANCELLED'}
            self.targets_json = json.dumps(pairs)
            self.expected_project = runtime.settings(context.scene).project_json
            self.expected_state = json.dumps(target_state(context.scene))
            return context.window_manager.invoke_props_dialog(self,width=410)
        except Exception as exc:
            self.report({'WARNING'},str(exc));return {'CANCELLED'}

    def draw(self, context):
        try:
            pairs = self._pairs(context)
            count = len(links_for_targets(runtime.get_project(context.scene),pairs))
            self.layout.label(text=f'解除 {len(pairs)} 条槽轨上的 {count} 处关联？',icon='UNLINKED')
            for mid,sid in pairs[:6]:self.layout.label(text=f'{mid} / {sid}')
            if len(pairs)>6:self.layout.label(text=f'另有 {len(pairs)-6} 条槽轨')
            self.layout.label(text='端点位置不动；保留其他槽及其他约束。Ctrl+Z 可恢复。')
        except Exception as exc:
            self.layout.label(text=str(exc),icon='ERROR')

    def execute(self, context):
        try:
            from .vendor.aludiy_core.associations import remove_slot_associations_many
            original = runtime.get_project(context.scene)
            if self.expected_project and (self.expected_project != runtime.settings(context.scene).project_json
                    or self.expected_state != json.dumps(target_state(context.scene))):
                raise ValidationError('确认期间工程或槽轨选择已变化，请重新操作')
            pairs = self._pairs(context)
            result = remove_slot_associations_many(original,slot_targets=pairs)
            if not result.changed_count:return {'CANCELLED'}
            g_move._commit_relations(context,original,result.project,g_move.target_spec(context))
            runtime.set_status(context.scene,f'已解除 {len(pairs)} 条槽轨上的 {result.changed_count} 处关联；端点位置不动，其他约束保留')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'WARNING'},str(exc));runtime.set_status(context.scene,str(exc));return {'CANCELLED'}

def _draw_target():
    c=bpy.context
    if not (c.area and c.area.type=='VIEW_3D' and c.region and c.region.type=='WINDOW'
            and c.region_data and c.workspace.name==runtime.WORKSPACE_NAME):return
    s=runtime.settings(c.scene)
    if not s.slot_target_member_id and not getattr(s,'slot_selection_json',''):return
    from . import viewport_overlay as ov
    import gpu
    try:
        p=g_move.display_project(c.scene)
        active=set(target_specs(c.scene,p))
        chosen=set(choice_model.validated_pairs(p,runtime.get_catalog(),selected_records(c.scene)))
        gpu.state.blend_set('ALPHA')
        for mid,sid in sorted(active | chosen):
            rail=next(r for r in interface_rails(p,mid,runtime.get_catalog()) if r.interface_id==sid)
            a,b=ov._project(rail.start_mm),ov._project(rail.end_mm)
            if a is None or b is None:continue
            color=(1,.72,.12,1) if (mid,sid) in active else (.25,.7,1,.8)
            ov._polyline([tuple(a),tuple(b)],color=color,width=3 if (mid,sid) in active else 1.5)
            ov.draw_snap_marker(tuple((a+b)*.5),color=color)

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

CLASSES=(ALUDIY_OT_set_slot_target,ALUDIY_OT_clear_slot_target,ALUDIY_OT_unlink_slot,
         ALUDIY_OT_manage_slot_selection,ALUDIY_OT_unlink_slots)
