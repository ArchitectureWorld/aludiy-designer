"""Scoped engineering G movement and screen-space endpoint selection.

Never monkeypatch Blender's transform functions or read back arbitrary meshes.
The original project stays untouched until confirmation. Previews update only
managed display caches in place; cancelling restores them from the snapshot.
"""
import json
import math

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatVectorProperty, StringProperty
from bpy_extras import view3d_utils
from mathutils import Matrix, Vector

from . import runtime, scene_adapter
from .viewport_geometry import world_ray_mm, project_point_mm
from .vendor.aludiy_core import Project, parse_distance_mm
from .vendor.aludiy_core.associations import exact_snap_delta, create_associations, remove_associations
from .vendor.aludiy_core.geometry import derive_member_mesh
from .vendor.aludiy_core.movement import movement_node_ids, preview_move, duplicate_members
from .vendor.aludiy_core.errors import ValidationError
from .vendor.aludiy_core.snapping import node_candidates, ground_candidate, preview_reconnect, member_candidates, engineering_candidates, describe_candidate

_ACTIVE = None
_KEYMAPS = []
_DRAW_HANDLE = None
_MOUSE = {}  # area pointer -> region-local cursor; ephemeral, never project data


def _window_region(area):
    return next((r for r in area.regions if r.type == 'WINDOW'), None) if area else None


def selected_objects(context):
    # Local Collections may hide the linked node in the solid viewport. Selection
    # is an engineering/view-layer state, not restricted to the current area.
    return [o for o in context.view_layer.objects if o.select_get()]


def engineering_objects(context):
    return [o for o in selected_objects(context)
            if o.get('aludiy_managed') and o.get('aludiy_entity_type') in {'NODE','MEMBER_AXIS','MEMBER_SOLID'}]


def endpoint_context(context):
    """Only an explicitly selected member endpoint permits detachment."""
    s = runtime.settings(context.scene)
    owner, side = s.endpoint_member_id, s.endpoint_side
    if not owner or side not in {'START', 'END'}:
        return None
    p = runtime.get_project(context.scene)
    m = p.members.get(owner)
    if m is None:
        return None
    nid = m.start_node_id if side == 'START' else m.end_node_id
    objects = engineering_objects(context)
    ids = {runtime.entity_id_from_object(o) for o in objects}
    active = context.view_layer.objects.active
    if ids == {nid} and runtime.entity_id_from_object(active) == nid:
        return owner, side
    return None


def target_spec(context):
    selected = selected_objects(context)
    managed = engineering_objects(context)
    if len(managed) != len(selected):
        raise ValidationError('请分开选择工程构件与普通 Blender 对象，再按 G')
    endpoint = endpoint_context(context)
    if endpoint:
        return {'endpoint': endpoint}
    mids, nids = set(), set()
    for o in managed:
        eid = runtime.entity_id_from_object(o)
        (nids if o.get('aludiy_entity_type') == 'NODE' else mids).add(eid)
    return {'member_ids': sorted(mids), 'node_ids': sorted(nids)}


def build_candidate(context, delta_mm, *, detach=False):
    return preview_move(runtime.get_project(context.scene), delta_mm, detach=detach, **target_spec(context))


def display_project(scene):
    if _ACTIVE is not None and getattr(_ACTIVE, '_scene', None) == scene and _ACTIVE._candidate is not None:
        return _ACTIVE._candidate.project
    return runtime.get_project(scene)


def update_preview_geometry(scene, project, affected_ids):
    """Update existing object datablocks, never delete an active transform target.

    Newly split nodes only exist in the candidate until commit; the overlay
    shows the new point without inserting an orphan node into the live scene.
    """
    affected = set(affected_ids)
    # Processing can change bodies whose design endpoints did not move.
    affected.update(mid for j in project.joints.values() for mid in (j.host_member_id,j.branch_member_id))
    catalog = runtime.get_catalog()
    mode = runtime.settings(scene).solid_display_mode
    derived = {mid: derive_member_mesh(project, mid, catalog, mode=mode) for mid in affected}
    for obj in scene.objects:
        if not obj.get('aludiy_managed'):
            continue
        eid, kind = runtime.entity_id_from_object(obj), obj.get('aludiy_entity_type')
        if kind == 'NODE':
            if eid in project.nodes:
                obj.location = scene_adapter._mm_to_m(project.nodes[eid].position_mm)
            elif (_ACTIVE is not None and getattr(_ACTIVE,'_scene',None)==scene
                  and _ACTIVE._snap is not None and _ACTIVE._snap.node_id in project.nodes):
                # Hiding a selected source would deselect it in Blender and break
                # the next G after cancellation. Keep its cache/selection alive
                # at the candidate target until the real commit rebuilds it.
                obj.location = scene_adapter._mm_to_m(project.nodes[_ACTIVE._snap.node_id].position_mm)
        elif eid in affected and kind in {'MEMBER_AXIS','MEMBER_SOLID'}:
            obj.matrix_world = Matrix.Identity(4)
            if kind == 'MEMBER_AXIS':
                m = project.members[eid]
                for v, nid in zip(obj.data.vertices, (m.start_node_id, m.end_node_id)):
                    v.co = scene_adapter._mm_to_m(project.nodes[nid].position_mm)
            else:
                mesh = derived[eid]
                coords = [scene_adapter._mm_to_m(v) for v in mesh.vertices_mm]
                if len(obj.data.vertices) == len(coords):
                    for vert, co in zip(obj.data.vertices, coords):
                        vert.co = co
                else:
                    obj.data.clear_geometry()
                    obj.data.from_pydata(coords, [], mesh.faces)
            obj.data.update()
    _redraw()


def _redraw():
    wm = bpy.context.window_manager
    if wm:
        for window in wm.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()


def _select_endpoint(context, owner, side):
    p = runtime.get_project(context.scene)
    m = p.members[owner]
    nid = m.start_node_id if side == 'START' else m.end_node_id
    # The endpoint is the only selected engineering target, never its whole member.
    for obj in context.view_layer.objects:
        if obj.select_get():
            obj.select_set(False)
    nodes = [o for o in context.scene.objects if o.get('aludiy_managed')
             and o.get('aludiy_entity_type') == 'NODE' and runtime.entity_id_from_object(o) == nid]
    if not nodes:
        raise ValidationError('工程节点显示缓存缺失，请先从工程数据重建视图')
    nodes[0].select_set(True)
    context.view_layer.objects.active = nodes[0]
    s = runtime.settings(context.scene)
    s.endpoint_member_id, s.endpoint_side = owner, side
    s.move_connection_mode = 'KEEP'
    count = sum(nid in (r.start_node_id,r.end_node_id) for r in p.members.values())
    runtime.set_status(context.scene, f'{owner} {"起端" if side=="START" else "终端"} · {nid} · 节点共用 {count} 根（含自身）；G 移动')
    _redraw()


class ALUDIY_OT_select_endpoint(bpy.types.Operator):
    bl_idname = 'aludiy.select_endpoint'
    bl_label = '选择工程端点'
    bl_description = '选择型材的起端或终端控制点；不进入网格编辑模式'
    endpoint: EnumProperty(items=(('START','起端',''),('END','终端','')), default='START')
    owner_id: StringProperty(default='', options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(engineering_objects(context)) and _ACTIVE is None

    def execute(self, context):
        owner = self.owner_id or _handle_owner(context)
        if not owner:
            self.report({'WARNING'}, '请先只选择一根型材，再选择它的端点')
            return {'CANCELLED'}
        try:
            _select_endpoint(context, owner, self.endpoint)
        except Exception as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


def _handle_owner(context):
    ep = endpoint_context(context)
    if ep:
        return ep[0]
    objects = engineering_objects(context)
    mids = {runtime.entity_id_from_object(o) for o in objects
            if o.get('aludiy_entity_type') in {'MEMBER_AXIS','MEMBER_SOLID'}}
    if len(mids) == 1 and not any(o.get('aludiy_entity_type') == 'NODE' for o in objects):
        return next(iter(mids))
    return None


def projected_handles(context):
    owner = _handle_owner(context)
    if not owner:
        return ()
    p = display_project(context.scene)
    m = p.members.get(owner)
    region = _window_region(context.area)
    rv3d = context.area.spaces.active.region_3d
    if m is None or region is None or rv3d is None:
        return ()
    return tuple((side, nid, view3d_utils.location_3d_to_region_2d(
        region, rv3d, Vector(scene_adapter._mm_to_m(p.nodes[nid].position_mm)), default=None))
        for side,nid in (('START',m.start_node_id),('END',m.end_node_id)))


class ALUDIY_OT_pick_endpoint(bpy.types.Operator):
    bl_idname = 'aludiy.pick_endpoint'
    bl_label = '选择型材端点控制点'
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return (context.area is not None and context.area.type == 'VIEW_3D'
                and context.region is not None and context.region.type == 'WINDOW'
                and context.mode == 'OBJECT' and context.workspace.name == runtime.WORKSPACE_NAME
                and _ACTIVE is None and bool(engineering_objects(context)))

    def invoke(self, context, event):
        from . import profile_tools
        if profile_tools.handle_inspector_click(context,event):
            return {'FINISHED'}
        if event.shift or event.ctrl or event.alt: return {'PASS_THROUGH'}
        region = _window_region(context.area)
        cursor = Vector((event.mouse_x-region.x,event.mouse_y-region.y))
        candidates = [(float((p-cursor).length),side,nid) for side,nid,p in projected_handles(context) if p is not None]
        if not candidates or min(candidates)[0] > 16:
            return {'PASS_THROUGH'}
        _, side, _ = min(candidates)
        _select_endpoint(context,_handle_owner(context),side)
        return {'FINISHED'}


class ALUDIY_OT_hover_endpoint(bpy.types.Operator):
    bl_idname = 'aludiy.hover_endpoint'
    bl_label = '端点悬停提示'
    bl_options = {'INTERNAL'}
    @classmethod
    def poll(cls, context):
        return (context.workspace is not None and context.workspace.name==runtime.WORKSPACE_NAME
                and context.mode=='OBJECT' and hasattr(context.scene,'aludiy_settings'))
    def invoke(self, context, event):
        from . import profile_tools
        profile_tools.record_pointer(context,event)
        region = _window_region(context.area)
        if context.area and context.area.type=='VIEW_3D' and region:
            _MOUSE[context.area.as_pointer()] = (event.mouse_x-region.x,event.mouse_y-region.y)
        _redraw()
        return {'PASS_THROUGH'}


def _copy_member_ids(project, spec):
    mids = tuple(spec.get('member_ids', ()))
    # Copy physical members, never orphan engineering handles or an implicit closure.
    if spec.get('endpoint') or not mids:
        raise ValidationError('复制请选择完整型材；单独节点或杆端不能作为型材副本')
    owned = {n for mid in mids if mid in project.members for n in
             (project.members[mid].start_node_id, project.members[mid].end_node_id)}
    if not set(spec.get('node_ids', ())).issubset(owned):
        raise ValidationError('请取消选中独立节点，只复制所选完整型材')
    return mids


def _select_copies(context, mapping, snapshot):
    from . import selection_state
    active = snapshot[1] if snapshot else None
    old_id = active[1] if active and active[0]=='ENGINEERING' else None
    new_id = mapping.get(old_id, next(iter(mapping.values())))
    kind = active[2] if active and active[0]=='ENGINEERING' else 'MEMBER_AXIS'
    selection_state.restore(context, ([('ENGINEERING',m,'MEMBER_AXIS') for m in mapping.values()],
                                    ('ENGINEERING',new_id,kind)))


class ALUDIY_OT_move_engineering(bpy.types.Operator):
    bl_idname = 'aludiy.move_engineering'
    bl_label = 'G 移动工程对象'
    bl_description = '鼠标移动型材或端点；X/Y/Z 锁轴，Shift+轴锁平面；数值默认毫米；Esc 取消'
    bl_options = {'REGISTER','UNDO','BLOCKING'}
    delta_mm: FloatVectorProperty(name='位移 (mm)', size=3, default=(0,0,0))
    detach: BoolProperty(name='断开选中杆端', default=False)
    delta_json: StringProperty(default='', options={'HIDDEN','SKIP_SAVE'})
    target_json: StringProperty(default='', options={'HIDDEN'})
    snap_target_node_id: StringProperty(default='', options={'HIDDEN'})
    snap_anchor_node_id: StringProperty(default='', options={'HIDDEN'})
    connect_only: BoolProperty(name='点选连接目标', default=False, options={'HIDDEN','SKIP_SAVE'})
    duplicate: BoolProperty(name='工程复制', default=False, options={'HIDDEN','SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return (context.area is not None and context.area.type == 'VIEW_3D'
                and context.mode == 'OBJECT' and bool(engineering_objects(context)) and _ACTIVE is None)

    def execute(self, context):
        try:
            original = runtime.get_project(context.scene)
            spec = json.loads(self.target_json) if self.target_json else target_spec(context)
            source = original
            copies = None
            if self.duplicate:
                copies = duplicate_members(original, _copy_member_ids(original, spec))
                source = copies.project
                spec = {'member_ids': list(copies.member_map.values())}
            delta = tuple(json.loads(self.delta_json)) if self.delta_json else tuple(self.delta_mm)
            if self.snap_target_node_id:
                anchor = self.snap_anchor_node_id or movement_node_ids(original, **spec)[0]
                result = preview_reconnect(original, delta, detach=self.detach,
                    anchor_node_id=anchor, target_node_id=self.snap_target_node_id, **spec)
            else:
                result = preview_move(source,delta,detach=self.detach,**spec)
            if not result.moved_node_ids and not self.duplicate:
                runtime.settings(context.scene).move_connection_mode='KEEP'
                runtime.set_status(context.scene,'位置与连接未改变')
                return {'CANCELLED'}
            from .operators import _commit_project_update
            selected_id = (spec['member_ids'][0] if self.duplicate else result.detached_node_id or (result.moved_node_ids[0] if spec.get('endpoint') or spec.get('node_ids')
                            else spec['member_ids'][0]))
            _commit_project_update(context,original,result.project,selected_entity_id=selected_id)
            # Preserve multiselection after reconstruction; useful for consecutive moves.
            wanted = set(spec.get('member_ids',())) | set(spec.get('node_ids',()))
            if self.snap_target_node_id and self.snap_anchor_node_id in wanted:
                wanted.discard(self.snap_anchor_node_id)
                wanted.add(self.snap_target_node_id)
            if spec.get('endpoint'):
                owner,side = spec['endpoint']; _select_endpoint(context,owner,side)
            elif wanted:
                for o in context.scene.objects:
                    if o.get('aludiy_managed'):
                        o.select_set(runtime.entity_id_from_object(o) in wanted)
            runtime.settings(context.scene).move_connection_mode = 'KEEP'
            if self.duplicate:
                _select_copies(context, copies.member_map, getattr(self, '_copy_selection', None))
            message = ((f'已复制 {len(copies.member_map)} 根；未继承 {copies.dropped_external_count} 处选区外依赖')
                       if copies else f'已连接到 {self.snap_target_node_id}' if self.snap_target_node_id else
                       ('已断开杆端并移动' if self.detach else '保持连接移动'))
            runtime.set_status(context.scene, f'{message} · 更新 {len(result.affected_member_ids)} 根 · Ctrl+Z 撤销')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'WARNING'}, str(exc))
            runtime.set_status(context.scene,f'移动未提交：{exc}')
            return {'CANCELLED'}

    def invoke(self, context, event):
        global _ACTIVE
        from . import operators, slot_tools, selection_state
        if operators._ACTIVE_DRAW is not None:
            return {'PASS_THROUGH'}
        if self.duplicate and context.workspace.name != runtime.WORKSPACE_NAME:
            return {'PASS_THROUGH'}
        self._copy_base = None
        self._copy_selection = None
        try:
            self._scene, self._area = context.scene, context.area
            self._region = _window_region(context.area)
            self._spec = target_spec(context)
            self._original = runtime.get_project(context.scene)
            self._raw = runtime.settings(context.scene).project_json
            slot_tools.sanitize_missing_target(context.scene, self._original)
            source_spec = dict(self._spec)
            if self.duplicate:
                copies = duplicate_members(self._original, _copy_member_ids(self._original, self._spec))
                self._copy_base = self._original
                self._copy_selection = selection_state.capture(context)
                self._original = copies.project
                self._spec = {'member_ids': list(copies.member_map.values())}
                self._copy_map = copies.member_map
                self._copy_dropped = copies.dropped_external_count
            ids = movement_node_ids(self._original,**self._spec)
            self._target_ids = set(ids)
            # For whole/group moves use the selected endpoint closest to the
            # invocation cursor, not the lexicographically first project node.
            mouse = Vector((event.mouse_x-self._region.x,event.mouse_y-self._region.y))
            rv = self._area.spaces.active.region_3d
            projected = [(nid,view3d_utils.location_3d_to_region_2d(self._region,rv,
                Vector(self._original.nodes[nid].position_mm)*.001,default=None)) for nid in ids]
            nearest = [(float((point-mouse).length),nid) for nid,point in projected if point is not None]
            self._anchor_id = min(nearest)[1] if nearest else ids[0]
            self._origin = Vector(self._original.nodes[self._anchor_id].position_mm)
            self.snap_anchor_node_id = self._anchor_id
            self.snap_target_node_id = ''
            self.delta_json = ''
            self._exact_delta = (0.0,0.0,0.0)

            self._start_mouse = (event.mouse_x-self._region.x,event.mouse_y-self._region.y)
            # N-panel button activation waits for a cursor location in the viewport.
            self._waiting = context.region.type != 'WINDOW' or not (0 <= self._start_mouse[0] < self._region.width and 0 <= self._start_mouse[1] < self._region.height)
            if self.connect_only:
                if not self._spec.get('endpoint'):
                    raise ValidationError('先选择型材的起端或终端，再点选连接目标')
                self._waiting = False
            self._mouse = self._start_mouse
            self._axis = None
            self._plane_lock = False
            self._typed, self._error = '', ''
            self._delta = Vector((0,0,0))
            self._last_direction = Vector((1,0,0))
            self._candidate = None
            self._affected = set()
            self._closed = False
            self._snap = None
            self._snap_options = ()
            self._snap_choice = 0
            self._choice_keys = ()
            self._free = bool(event.ctrl)
            self._ground = (parse_distance_mm(runtime.settings(self._scene).ground_elevation_input)
                            if runtime.settings(self._scene).ground_snap_enabled else None)
            self._navigating = False
            self._needs_rebase = False
            self._screen_normal = context.area.spaces.active.region_3d.view_rotation @ Vector((0,0,1))
            self.detach = bool(self._spec.get('endpoint') and runtime.settings(context.scene).move_connection_mode=='DETACH')
            self.target_json = json.dumps(source_spec)
            self._rebase_pointer(context)
            _ACTIVE = self
            if self.duplicate:
                self._candidate = preview_move(self._original, (0,0,0), **self._spec)
                scene_adapter.rebuild_scene(self._scene, self._original, runtime.get_catalog())
                _select_copies(context, self._copy_map, self._copy_selection)
            context.window_manager.modal_handler_add(self)
            context.window.cursor_modal_set('CROSSHAIR')
            self._feedback(context)
            return {'RUNNING_MODAL'}
        except Exception as exc:
            _ACTIVE = None
            if self._copy_base is not None:
                scene_adapter.rebuild_scene(self._scene, self._copy_base, runtime.get_catalog())
                selection_state.restore(context, self._copy_selection)
            self.report({'WARNING'},str(exc))
            return {'CANCELLED'}

    def _ray(self, mouse):
        rv = self._area.spaces.active.region_3d
        origin = view3d_utils.region_2d_to_origin_3d(self._region,rv,mouse) * 1000
        direction = view3d_utils.region_2d_to_vector_3d(self._region,rv,mouse)
        return origin,direction

    def _plane_point(self, mouse, normal):
        ro,rd = self._ray(mouse)
        denom = rd.dot(normal)
        if abs(denom) < 1e-6:
            raise ValidationError('当前视线与移动平面平行，请旋转视角或输入精确距离')
        return ro + rd*((self._origin-ro).dot(normal)/denom)

    def _pointer_value(self, mouse):
        if self._axis is not None:
            axis = Vector(tuple(1 if i=='XYZ'.index(self._axis) else 0 for i in range(3)))
            if self._plane_lock:
                return self._plane_point(mouse,axis)
            ro,rd = self._ray(mouse)
            denom=1-rd.dot(axis)**2
            if abs(denom)<1e-6:
                raise ValidationError('锁定轴正对视线；可直接输入距离，或旋转视角')
            t = ((ro-self._origin).dot(axis)-(ro-self._origin).dot(rd)*rd.dot(axis))/denom
            return axis*t
        return self._plane_point(mouse,self._screen_normal)

    def _rebase_pointer(self, context):
        try:
            self._pointer_start = self._pointer_value(self._start_mouse)
        except ValidationError:
            self._pointer_start = None

    def _project_point(self, point):
        return project_point_mm(self._region, self._area.spaces.active.region_3d, point)

    def _snap_delta(self, context, delta):
        from . import slot_tools
        self._snap = None
        if self._free:
            self._snap_options = ()
            return delta
        excluded = set(self._target_ids)
        if self.detach and self._spec.get('endpoint'):
            owner = self._spec['endpoint'][0]
            if any(m.id!=owner and self._anchor_id in (m.start_node_id,m.end_node_id)
                   for m in self._original.members.values()):
                excluded.discard(self._anchor_id)
        exact = tuple(self._original.nodes[self._anchor_id].position_mm[i]+delta[i] for i in range(3)) if self._typed else None
        cursor = self._project_point(exact) if exact is not None else self._mouse
        if cursor is None:
            self._snap_options = ()
            return delta
        ro, rd = world_ray_mm(self._region, self._area.spaces.active.region_3d, self._mouse)
        excluded_members = {m.id for m in self._original.members.values()
                            if m.start_node_id in self._target_ids or m.end_node_id in self._target_ids}
        origin = self._original.nodes[self._anchor_id].position_mm
        options = engineering_candidates(
            self._original, origin_mm=origin, cursor_px=cursor, project_point=self._project_point,
            ray_origin_mm=tuple(ro), ray_direction=tuple(rd), excluded_node_ids=excluded,
            excluded_member_ids=excluded_members, radius_px=runtime.settings(self._scene).snap_pixel_radius,
            axis=self._axis, plane_lock=self._plane_lock, exact_position_mm=exact,
            ground_mm=self._ground, raw_position_mm=tuple(origin[i]+delta[i] for i in range(3)),
            nodes_only=self.connect_only, catalog=runtime.get_catalog(),
            slot_target=slot_tools.snapping_target(self._scene,self._original))
        keys = tuple(c.key for c in options)
        if keys != self._choice_keys:
            self._snap_choice = 0
        self._choice_keys, self._snap_options = keys, options
        if options:
            self._snap = options[self._snap_choice % len(options)]
            # Exact typed displacement is never silently rounded.
            return delta if self._typed else exact_snap_delta(self._original.nodes[self._anchor_id].position_mm,self._snap.position_mm)
        return delta

    def _snap_label(self):
        if self._free:
            return 'Ctrl 自由移动 · 不吸附，不新建连接'
        if self._typed and self._snap is None:
            return '精确输入优先 · 未命中节点，不新建连接'
        if self._snap is not None:
            suffix = f' · Tab 切换 {self._snap_choice % len(self._snap_options)+1}/{len(self._snap_options)}' if len(self._snap_options)>1 else ''
            return describe_candidate(self._snap, self._original) + suffix
        return describe_candidate(None, self._original) + ' · Ctrl 自由移动'

    def _update(self, context):
        if self._waiting: return
        try:
            if self._typed:
                distance = parse_distance_mm(self._typed)
                if self._axis and not self._plane_lock:
                    direction=Vector(tuple(1 if i=='XYZ'.index(self._axis) else 0 for i in range(3)))
                else:
                    direction=self._last_direction
                delta=tuple(float(v)*distance for v in direction)
            elif self.connect_only:
                delta=Vector((0,0,0))
            else:
                if self._pointer_start is None: self._rebase_pointer(context)
                if self._pointer_start is None:
                    raise ValidationError('当前方向无法用鼠标定位；输入距离或切换观察方向')
                delta=self._pointer_value(self._mouse)-self._pointer_start
                if delta.length>1e-6: self._last_direction=delta.normalized()
            delta=self._snap_delta(context,delta)
            if self.connect_only and (self._snap is None or self._snap.kind!='NODE'):
                raise ValidationError('点选一个工程端点作为连接目标（Tab 切换重合候选）')
            if self.connect_only and self._snap is not None and self._snap.kind=='NODE':
                candidate=preview_reconnect(self._original,delta,anchor_node_id=self._anchor_id,
                    target_node_id=self._snap.node_id,detach=self.detach,**self._spec)
            else:
                candidate=preview_move(self._original,delta,detach=self.detach,**self._spec)
            self._affected.update(candidate.affected_member_ids)
            update_preview_geometry(self._scene,candidate.project,self._affected)
            self._candidate, self._delta = candidate, Vector(delta)
            self._exact_delta = tuple(delta)
            self._error=''
        except Exception as exc:
            self._error=str(exc)
            self._candidate=None
            update_preview_geometry(self._scene,self._original,self._affected)
        self._feedback(context)

    def _feedback(self, context):
        mode='复制摆放' if self.duplicate else ('断开选中杆端' if self.detach else '保持连接')
        axis=('排除 '+self._axis if self._plane_lock else self._axis) if self._axis else '屏幕平面'
        message=f'G · {mode} · {axis} · 源 {self._anchor_id} | {self._snap_label()} | Δ {self._delta.x:.1f}, {self._delta.y:.1f}, {self._delta.z:.1f} mm | Enter 确认 · Esc 取消'
        if self._error: message='不可提交：'+self._error
        if self._waiting: message='把鼠标移入视窗，左键确定移动起点；Esc 取消'
        self._area.header_text_set(message)
        _redraw()

    def modal(self, context, event):
        if self._closed: return {'CANCELLED'}
        if event.type in {'ESC','RIGHTMOUSE'} and event.value=='PRESS':
            self.cancel(context); return {'CANCELLED'}
        if context.scene!=self._scene or runtime.settings(self._scene).project_json!=self._raw:
            self.cancel(context); return {'CANCELLED'}
        from . import profile_tools
        if profile_tools.modal_inset_guard(context,event):
            return {'RUNNING_MODAL'}
        free = bool(event.ctrl)
        if free != self._free:
            self._free = free
            self._update(context)
        if event.type in {'LEFT_CTRL','RIGHT_CTRL'}:
            return {'RUNNING_MODAL'}
        if event.type == 'MIDDLEMOUSE':
            self._navigating = event.value != 'RELEASE'
            self._needs_rebase = True
            return {'PASS_THROUGH'}
        if event.type in {'WHEELUPMOUSE','WHEELDOWNMOUSE','TRACKPADPAN','TRACKPADZOOM'} or getattr(event,'alt',False):
            self._needs_rebase = True
            return {'PASS_THROUGH'}
        if self._navigating:
            return {'PASS_THROUGH'}
        mouse=(event.mouse_x-self._region.x,event.mouse_y-self._region.y)
        inside=0<=mouse[0]<self._region.width and 0<=mouse[1]<self._region.height
        if event.type=='MOUSEMOVE':
            if not getattr(event,'alt',False) and inside:
                self._mouse=mouse
                if self._needs_rebase:
                    self._screen_normal = self._area.spaces.active.region_3d.view_rotation @ Vector((0,0,1))
                    try:
                        self._pointer_start = self._pointer_value(mouse)-self._delta
                        self._needs_rebase = False
                    except ValidationError: pass
                self._update(context)
            return {'RUNNING_MODAL'}
        if event.value!='PRESS': return {'RUNNING_MODAL'}
        if event.type == 'TAB':
            if len(self._snap_options)>1:
                self._snap_choice = (self._snap_choice + (-1 if event.shift else 1)) % len(self._snap_options)
                self._update(context)
            return {'RUNNING_MODAL'}
        if event.type in {'X','Y','Z'}:
            plane=bool(event.shift)
            self._axis = None if self._axis==event.type and self._plane_lock==plane else event.type
            self._plane_lock=plane
            self._rebase_pointer(context); self._update(context)
            return {'RUNNING_MODAL'}
        if event.type in {'RET','NUMPAD_ENTER','LEFTMOUSE'}:
            if event.type=='LEFTMOUSE' and not inside: return {'RUNNING_MODAL'}
            if self._waiting:
                self._waiting=False; self._start_mouse=self._mouse=mouse
                self._rebase_pointer(context); self._feedback(context)
                return {'RUNNING_MODAL'}
            # Re-evaluate modifiers and candidates on the confirmation event;
            # this prevents a stale target surviving Ctrl press/release.
            self._update(context)
            if self._error or self._candidate is None: return {'RUNNING_MODAL'}
            # Discard visual preview before executing one undoable engineering edit.
            self.delta_mm=tuple(self._delta)
            self.delta_json=json.dumps(self._exact_delta)
            self.snap_target_node_id = (self._snap.node_id or '') if self.connect_only and self._snap is not None and not self._free else ''
            self._restore_and_close(context)
            return self.execute(context)
        if event.type=='BACK_SPACE':
            self._typed=self._typed[:-1]; self._update(context); return {'RUNNING_MODAL'}
        character=getattr(event,'unicode','') or getattr(event,'ascii','')
        if character and character in '0123456789.+-*/() mMcC':
            self._typed+=character; self._update(context)
        return {'RUNNING_MODAL'}

    def _restore_and_close(self, context):
        global _ACTIVE
        try:
            if self.duplicate and self._copy_base is not None:
                from . import selection_state
                scene_adapter.rebuild_scene(self._scene, self._copy_base, runtime.get_catalog())
                selection_state.restore(context, self._copy_selection)
            else:
                update_preview_geometry(self._scene,self._original,self._affected)
        finally:
            self._closed=True; _ACTIVE=None
            self._area.header_text_set(None)
            context.window.cursor_modal_restore()
            _redraw()

    def cancel(self, context):
        if not getattr(self,'_closed',True):
            self._restore_and_close(context)
            runtime.settings(self._scene).move_connection_mode='KEEP'
            runtime.set_status(self._scene,'复制已取消，未留下副本' if self.duplicate else '移动已取消，位置与连接关系均未改变')


def _disc(point, radius, color):
    # Triangle fans stay readable on GPUs that ignore point-size state.
    import gpu
    from gpu_extras.batch import batch_for_shader
    cx,cy=point
    vertices=[]
    for i in range(24):
        a,b=2*math.pi*i/24,2*math.pi*(i+1)/24
        vertices.extend(((cx,cy,0),(cx+radius*math.cos(a),cy+radius*math.sin(a),0),
                         (cx+radius*math.cos(b),cy+radius*math.sin(b),0)))
    shader=gpu.shader.from_builtin('UNIFORM_COLOR')
    batch=batch_for_shader(shader,'TRIS',{'pos':vertices})
    shader.bind(); shader.uniform_float('color',color); batch.draw(shader)


def _draw_handles():
    ctx=bpy.context
    if (not ctx.area or ctx.area.type!='VIEW_3D' or ctx.region.type!='WINDOW' or not ctx.region_data
            or ctx.workspace.name!=runtime.WORKSPACE_NAME or not ctx.space_data.overlay.show_overlays): return
    try:
        from . import viewport_overlay as ov
        import gpu
        gpu.state.blend_set('ALPHA')
        _draw_selection(ctx,ov)
        handles=projected_handles(ctx)
        cursor=Vector(_MOUSE.get(ctx.area.as_pointer(),(-10000,-10000)))
        ep=endpoint_context(ctx)
        for side,nid,point in handles:
            if point is None: continue
            hover=(point-cursor).length<=16
            active=ep is not None and ep[1]==side
            color=ov.START_COLOR if side=='START' else ov.END_COLOR
            _disc(point,12 if hover or active else 10,(1,1,1,1))
            _disc(point,8.5 if hover or active else 6.5,color)
            if hover or active:
                label=('起端' if side=='START' else '终端')+' · '+nid
                if _ACTIVE is None:
                    label += ' | G 移动'
                ov._text(point.x+16,point.y+16,label,size=14)
        if _ACTIVE is not None and _ACTIVE._scene==ctx.scene:
            op=_ACTIVE
            mode='复制摆放' if op.duplicate else ('解除杆端关联' if op.detach else '吸附仅定位')
            axis=(('排除 ' if op._plane_lock else '')+op._axis) if op._axis else '屏幕平面'
            from . import view_sync
            if ctx.area == op._area or view_sync.is_line_view_context(ctx):
                x=72 if ctx.space_data.show_region_toolbar else 14
                top=ctx.region.height-58
                ov._filled_rect(x,top-112,min(590,ctx.region.width-x-14),112,(.035,.045,.065,.94))
                ov._text(x+12,top-24,f'{"Shift+D" if op.duplicate else "G"} · {mode} · {axis} · 源 {op._anchor_id}',size=14)
                ov._text(x+12,top-49,f'ΔX {op._delta.x:.1f}   ΔY {op._delta.y:.1f}   ΔZ {op._delta.z:.1f} mm',size=13)
                ov._text(x+12,top-74,op._error or (f'输入：{op._typed}' if op._typed else 'X/Y/Z 锁轴 · 左键/Enter 确认 · Esc 取消'),size=12,
                         color=(1,.45,.25,1) if op._error else ov.TEXT_COLOR)
                ov._text(x+12,top-99,op._snap_label(),size=12)
            if op._snap is not None:
                sp=ov._project(op._snap.position_mm)
                if sp is not None:
                    color=(1,.4,.2,1) if op._error else ((.2,1,.55,1) if op._snap.kind=='NODE' else (.25,.7,1,1))
                    _disc(sp,10,(1,1,1,1)); _disc(sp,7,color)
                    text=op._snap_label() if not op._error else '不可连接：'+op._error
                    ov._text(sp.x+15,sp.y-24,text,size=12,color=color)
            candidate=op._candidate.project if op._candidate else op._original
            selected_mids,selected_nodes=selection_summary(ctx)
            for mid in op._affected:
                if mid in selected_mids: continue
                m=candidate.members[mid]
                pts=[ov._project(candidate.nodes[n].position_mm) for n in (m.start_node_id,m.end_node_id)]
                if all(p is not None for p in pts):
                    _dashed(ov,pts[0],pts[1],(.3,.8,1,.85))
    except Exception as exc:
        # Never remove core controls because a GPU overlay is unavailable.
        print(f'AluDIY endpoint overlay: {exc}')
    finally:
        try:
            import gpu
            gpu.state.blend_set('NONE')
        except Exception: pass



def selection_summary(context):
    mids,nids=set(),set()
    for obj in engineering_objects(context):
        eid=runtime.entity_id_from_object(obj)
        if obj.get('aludiy_entity_type')=='NODE': nids.add(eid)
        else: mids.add(eid)
    return mids,nids


def _dashed(ov,a,b,color):
    length=(b-a).length
    steps=max(1,int(length/12))
    for i in range(steps):
        p=a.lerp(b,i/steps);q=a.lerp(b,min(1,(i+.55)/steps))
        ov._polyline([tuple(p),tuple(q)],color=color,width=2.0)


def _draw_selection(context,ov):
    mids,nids=selection_summary(context)
    p=display_project(context.scene)
    active=runtime.entity_id_from_object(context.view_layer.objects.active)
    for mid in mids:
        if mid not in p.members:continue
        m=p.members[mid];start=ov._project(p.nodes[m.start_node_id].position_mm);end=ov._project(p.nodes[m.end_node_id].position_mm)
        if start is None or end is None:continue
        pts=[tuple(start),tuple(end)]
        ov._polyline(pts,color=(1,1,1,1) if mid==active else (.2,.8,1,1),width=8 if mid==active else 6)
        ov._polyline(pts,colors=[ov.START_COLOR,ov.END_COLOR],width=3)
        center=(start+end)*.5;ov._text(center.x+6,center.y+8,mid,size=12)
    for nid in nids:
        if nid not in p.nodes:continue
        pt=ov._project(p.nodes[nid].position_mm)
        if pt is not None:
            _disc(pt,10,(1,1,1,1) if nid==active else (.2,.8,1,1))
            _disc(pt,6,(.08,.18,.22,1))
    if p.joints:
        from .vendor.aludiy_core.joints import solve_cutbacks
        if solve_cutbacks(p,runtime.get_catalog()).issues:
            ov._text(72,98,'交接待处理：退让暂停，请调整或清除交接',size=12,color=(1,.5,.2,1))
    # Mark manual and legacy relationships separately from selection.
    relation_points=set()
    for r in p.associations.values():
        relation_points.update(r.node_ids if r.kind=='COINCIDENT' else (r.follower_node_id,))
    refs={}
    for m in p.members.values():
        for n in (m.start_node_id,m.end_node_id):refs[n]=refs.get(n,0)+1
    relation_points.update(n for n,count in refs.items() if count>1)
    for nid in relation_points:
        pt=ov._project(p.nodes[nid].position_mm)
        if pt is not None:
            ov.draw_snap_marker((pt.x,pt.y),color=(1,.8,.25,1))
    if mids or nids:
        y=35;x=72 if context.space_data.show_region_toolbar else 14
        ov._filled_rect(x,y, min(580,context.region.width-x-12),48,(.035,.045,.065,.94))
        ov._text(x+10,y+29,f'已选 {len(mids)} 根型材 / {len(nids)} 个节点 · 当前 {active or "—"}',size=13)
        influenced=0
        if _ACTIVE and _ACTIVE._scene==context.scene: influenced=len(set(_ACTIVE._affected)-mids)
        ov._text(x+10,y+9,f'实线：选中 · 虚线：关联影响 {influenced} 根 · 菱形：已有关系',size=11)


class ALUDIY_OT_create_associations(bpy.types.Operator):
    bl_idname='aludiy.create_associations'
    bl_label='创建关联'
    bl_description='多选已相接杆件或重合节点，创建显式端点/杆身/槽轨关系；不移动构件'
    bl_options={'REGISTER','UNDO'}
    @classmethod
    def poll(cls,context): return ALUDIY_OT_move_engineering.poll(context)
    def execute(self,context):
        try:
            spec=target_spec(context)
            from . import slot_tools
            from .vendor.aludiy_core.associations import create_slot_associations
            original=runtime.get_project(context.scene)
            target=slot_tools.snapping_target(context.scene,original)
            if target:
                result=create_slot_associations(original,runtime.get_catalog(),
                    host_member_id=target[0],interface_id=target[1],**spec)
            else:
                if spec.get('endpoint'): raise ValidationError('请 Shift 多选相接杆件/节点；或先指定目标槽轨')
                result=create_associations(original,catalog=runtime.get_catalog(),**spec)
            if not result.changed_count:
                runtime.set_status(context.scene,'这些关联已存在');return {'CANCELLED'}
            _commit_relations(context,original,result.project,spec)
            runtime.set_status(context.scene,f'已创建 {result.changed_count} 处关联；杆身/槽轨按相对位置跟随主杆')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'WARNING'},str(exc));runtime.set_status(context.scene,str(exc));return {'CANCELLED'}


class ALUDIY_OT_remove_associations(bpy.types.Operator):
    bl_idname='aludiy.remove_associations'
    bl_label='解除关联'
    bl_description='解除所选构件或节点相关关系，保留当前几何位置'
    bl_options={'REGISTER','UNDO'}
    @classmethod
    def poll(cls,context): return ALUDIY_OT_move_engineering.poll(context)
    def execute(self,context):
        try:
            spec=target_spec(context);original=runtime.get_project(context.scene)
            result=remove_associations(original,**spec)
            if not result.changed_count:
                runtime.set_status(context.scene,'所选对象没有待解除关联');return {'CANCELLED'}
            _commit_relations(context,original,result.project,spec)
            runtime.set_status(context.scene,f'已解除 {result.changed_count} 处关联；位置不变')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'WARNING'},str(exc));runtime.set_status(context.scene,str(exc));return {'CANCELLED'}


def _commit_relations(context,original,project,spec):
    from .operators import _commit_project_update
    mids=set(spec.get('member_ids',()));nids=set(spec.get('node_ids',()))
    selected=next(iter(mids or nids),None)
    if spec.get('endpoint'):
        owner,side=spec['endpoint'];selected=owner
    from . import selection_state
    snapshot=selection_state.capture(context)
    try:
        _commit_project_update(context,original,project,selected_entity_id=selected)
    finally:
        selection_state.restore(context,snapshot)
    if spec.get('endpoint'):_select_endpoint(context,owner,side)
    _redraw()

def register_services():
    global _DRAW_HANDLE
    wm=bpy.context.window_manager
    if wm and wm.keyconfigs.addon and not _KEYMAPS:
        km=wm.keyconfigs.addon.keymaps.new(name='Object Mode',space_type='EMPTY')
        move_key=km.keymap_items.new('aludiy.move_engineering',type='G',value='PRESS',head=True)
        move_key.properties.connect_only=False
        _KEYMAPS.append((km,move_key))
        copy_key=km.keymap_items.new('aludiy.move_engineering',type='D',value='PRESS',shift=True,head=True)
        copy_key.properties.duplicate=True
        _KEYMAPS.append((km,copy_key))
        km=wm.keyconfigs.addon.keymaps.new(name='3D View',space_type='VIEW_3D')
        _KEYMAPS.append((km,km.keymap_items.new('aludiy.pick_endpoint',type='LEFTMOUSE',value='PRESS',any=True,head=True)))
        km=wm.keyconfigs.addon.keymaps.new(name='Window',space_type='EMPTY')
        _KEYMAPS.append((km,km.keymap_items.new('aludiy.hover_endpoint',type='MOUSEMOVE',value='ANY',any=True,head=True)))
    if _DRAW_HANDLE is None and not bpy.app.background:
        _DRAW_HANDLE=bpy.types.SpaceView3D.draw_handler_add(_draw_handles,(),'WINDOW','POST_PIXEL')


def unregister_services():
    global _DRAW_HANDLE,_ACTIVE
    if _ACTIVE is not None:
        try: _ACTIVE.cancel(bpy.context)
        except Exception: _ACTIVE=None
    for km,kmi in reversed(_KEYMAPS):
        try: km.keymap_items.remove(kmi)
        except (RuntimeError,ReferenceError): pass
    _KEYMAPS.clear(); _MOUSE.clear()
    if _DRAW_HANDLE is not None:
        try: bpy.types.SpaceView3D.draw_handler_remove(_DRAW_HANDLE,'WINDOW')
        except (RuntimeError,ReferenceError): pass
        _DRAW_HANDLE=None


CLASSES=(ALUDIY_OT_create_associations,ALUDIY_OT_remove_associations,ALUDIY_OT_select_endpoint,ALUDIY_OT_pick_endpoint,ALUDIY_OT_hover_endpoint,ALUDIY_OT_move_engineering)
