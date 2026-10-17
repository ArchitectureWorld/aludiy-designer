"""User-facing operators for the AluDIY Blender alpha."""

import math
from pathlib import Path

import bpy
from bpy.props import EnumProperty, StringProperty
from bpy_extras import view3d_utils
from bpy_extras.io_utils import ExportHelper, ImportHelper
from mathutils import Vector

from . import runtime, scene_adapter, view_sync
from .viewport_geometry import world_ray_mm, project_point_mm
from .vendor.aludiy_core.io import append_sample_frame
from .runtime import (
    HELPER_COLLECTION,
    active_member_id,
    active_node_id,
    empty_project,
    get_catalog,
    get_project,
    set_project,
    set_status,
    settings,
    selected_member_ids,
)
from .vendor.aludiy_core import (
    GeometryError,
    InputParseError,
    Member,
    Node,
    Project,
    ValidationError,
    catalog_revision_warning,
    create_sample_frame,
    load_project,
    parse_distance_mm,
    parse_length_mm,
    parse_polar,
    move_node,
    resize_member,
    translate_member,
    save_project,
    write_cutlist_csv,
)

from .vendor.aludiy_core.drawing import (
    axis_vector,
    closest_point_on_axis_to_ray,
    point_is_on_axis,
    point_on_workplane_from_ray,
    polar_endpoint_mm,
)

from .vendor.aludiy_core.snapping import engineering_candidates, describe_candidate, resolve_draw_endpoint, JOIN_TOLERANCE_MM

_PREVIEW_NAME = "_ALUDIY_MEMBER_PREVIEW"
_ACTIVE_DRAW = None


def _overlay_module():
    """Import the optional GPU overlay only when an interactive tool needs it."""

    from . import viewport_overlay

    return viewport_overlay


def _remove_draw_feedback_safely(operator) -> None:
    try:
        _overlay_module().remove_draw_feedback(operator)
    except Exception as exc:
        print(f"AluDIY draw-feedback cleanup warning: {exc}")


def _first_profile_id() -> str:
    return get_catalog().profile_ids()[0]


def _selected_profile(scene: bpy.types.Scene) -> str:
    value = settings(scene).active_profile_id
    return value or _first_profile_id()


def _editable_project(scene: bpy.types.Scene) -> tuple[Project, Project]:
    """Return the persisted project and an isolated candidate for editing."""

    project = get_project(scene)
    return project, Project.from_dict(project.to_dict())


def _commit_project_update(
    context: bpy.types.Context,
    original_project: Project,
    updated_project: Project,
    *,
    selected_entity_id: str,
) -> None:
    """Atomically rebuild caches and persist a candidate engineering project."""

    catalog = get_catalog()
    try:
        scene_adapter.rebuild_scene(context.scene, updated_project, catalog)
        set_project(context.scene, updated_project)
    except Exception:
        try:
            scene_adapter.rebuild_scene(context.scene, original_project, catalog)
            set_project(context.scene, original_project)
        except Exception as restore_exc:
            print(f"AluDIY precise-edit restore warning: {restore_exc}")
        raise
    try:
        scene_adapter.select_entity(context.scene, context.view_layer, selected_entity_id)
    except Exception as select_exc:
        print(f"AluDIY precise-edit selection warning: {select_exc}")


def _next_id(prefix: str, values) -> str:
    largest = 0
    for value in values:
        if value.startswith(f"{prefix}-"):
            try:
                largest = max(largest, int(value.split("-", 1)[1]))
            except ValueError:
                continue
    return f"{prefix}-{largest + 1:03d}"


def _window_region(area: bpy.types.Area | None):
    if area is None:
        return None
    return next((region for region in area.regions if region.type == "WINDOW"), None)


def _view_ray_mm(
    context: bpy.types.Context,
    event,
) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    region = _window_region(context.area)
    region_data = getattr(context.area.spaces.active, "region_3d", None) if context.area else None
    if region is None or region_data is None:
        return None
    coordinate = (event.mouse_x - region.x, event.mouse_y - region.y)
    return world_ray_mm(region, region_data, coordinate)


def _nearest_node_in_view(
    context: bpy.types.Context,
    event,
    project,
    tolerance_px: float,
):
    region = _window_region(context.area)
    region_data = getattr(context.area.spaces.active, "region_3d", None) if context.area else None
    if region is None or region_data is None:
        return None
    cursor = Vector((event.mouse_x - region.x, event.mouse_y - region.y))
    candidates = []
    for node in project.nodes.values():
        world = Vector(tuple(value * scene_adapter.MM_TO_M for value in node.position_mm))
        projected = view3d_utils.location_3d_to_region_2d(
            region,
            region_data,
            world,
            default=None,
        )
        if projected is not None:
            candidates.append(((projected - cursor).length, node))
    if not candidates:
        return None
    distance, node = min(candidates, key=lambda item: item[0])
    return node if distance <= tolerance_px else None


def _point_from_event(context: bpy.types.Context, event, operator):
    """Pick with the same engineering candidates as G, never change topology."""
    project = get_project(context.scene)
    region = _window_region(context.area)
    rv3d = context.area.spaces.active.region_3d
    ray = _view_ray_mm(context, event)
    if ray is None:
        return None, None
    ro, rd = ray
    axis = operator._axis_lock if operator._start_mm is not None else None
    plane_lock = bool(getattr(operator, '_plane_lock', False) and axis)
    point, pointer_error = None, None
    try:
        if axis and not plane_lock:
            point = closest_point_on_axis_to_ray(
                axis_origin_mm=operator._start_mm, axis=axis,
                ray_origin_mm=ro, ray_direction=rd)
        else:
            plane = {'X': 'YZ', 'Y': 'XZ', 'Z': 'XY'}[axis] if plane_lock else operator._work_plane
            point = point_on_workplane_from_ray(
                ray_origin_mm=ro, ray_direction=rd, work_plane=plane,
                offset_mm=operator._workplane_offset_mm, start_mm=operator._start_mm)
    except GeometryError as exc:
        pointer_error = exc
    operator._snap = None
    if getattr(operator, '_free', False):
        operator._snap_options = ()
        operator._choice_keys = ()
        if point is None and pointer_error:
            raise pointer_error
        return point, None
    def project_point(position):
        return project_point_mm(region, rv3d, position)
    start = operator._start_mm
    origin = start or point or (0.0, 0.0, operator._workplane_offset_mm)
    excluded = {nid for nid, node in project.nodes.items()
                if start is not None and math.dist(node.position_mm, start) <= JOIN_TOLERANCE_MM}
    from . import slot_tools
    opts = engineering_candidates(
        project, origin_mm=origin,
        cursor_px=(event.mouse_x - region.x, event.mouse_y - region.y),
        project_point=project_point, ray_origin_mm=ro, ray_direction=rd,
        excluded_node_ids=excluded, radius_px=settings(context.scene).snap_pixel_radius,
        axis=axis, plane_lock=plane_lock, perpendicular=start is not None,
        catalog=get_catalog(), slot_target=slot_tools.target_spec(context.scene,project))
    if start is not None:
        opts = tuple(c for c in opts if math.dist(c.position_mm, start) > JOIN_TOLERANCE_MM)
    keys = tuple(c.key for c in opts)
    if keys != getattr(operator, '_choice_keys', ()):
        operator._snap_choice = 0
    operator._choice_keys, operator._snap_options = keys, opts
    if opts:
        operator._snap = opts[getattr(operator, '_snap_choice', 0) % len(opts)]
        return operator._snap.position_mm, operator._snap.node_id
    if point is None and pointer_error:
        # Axis looking down the camera is ambiguous for the mouse, but a typed
        # exact length on the axis remains well-defined, using positive direction.
        if operator._typed and start is not None and axis and not plane_lock:
            return tuple(start[i] + axis_vector(axis)[i] for i in range(3)), None
        raise pointer_error
    return point, None


def _distance(a, b) -> float:
    return math.dist(tuple(a), tuple(b))


def _nearest_node(project, point_mm, tolerance_mm: float):
    candidates = [
        (math.dist(node.position_mm, point_mm), node)
        for node in project.nodes.values()
    ]
    if not candidates:
        return None
    distance, node = min(candidates, key=lambda item: item[0])
    return node if distance <= tolerance_mm else None


def _preview_object(scene: bpy.types.Scene):
    return scene.objects.get(_PREVIEW_NAME)


def _remove_preview(scene: bpy.types.Scene) -> None:
    obj = _preview_object(scene)
    if obj is not None:
        scene_adapter.remove_object_and_orphan_data(obj)


def _update_preview(scene: bpy.types.Scene, start_mm, end_mm) -> None:
    obj = _preview_object(scene)
    if obj is None:
        collection = scene_adapter.ensure_collection(scene, HELPER_COLLECTION)
        mesh = bpy.data.meshes.new(f"{_PREVIEW_NAME}_Mesh")
        mesh.from_pydata([(0, 0, 0), (0, 0, 0)], [(0, 1)], [])
        obj = bpy.data.objects.new(_PREVIEW_NAME, mesh)
        collection.objects.link(obj)
        obj.show_in_front = True
        obj.display_type = "WIRE"
        view_sync.refresh_view_collections(scene)
    start = tuple(value * scene_adapter.MM_TO_M for value in start_mm)
    end = tuple(value * scene_adapter.MM_TO_M for value in end_mm)
    obj.data.vertices[0].co = start
    obj.data.vertices[1].co = end
    obj.data.update()


class ALUDIY_OT_setup_workspace(bpy.types.Operator):
    bl_idname = "aludiy.setup_workspace"
    bl_label = "设置双视窗工作区"
    bl_description = "建立线图与三维实体双视窗并启用联动"

    def execute(self, context):
        try:
            view_sync.setup_workspace(context)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            set_status(context.scene, f"双视窗配置失败：{exc}")
            return {"CANCELLED"}
        return {"FINISHED"}


class ALUDIY_OT_new_project(bpy.types.Operator):
    bl_idname = "aludiy.new_project"
    bl_label = "新建空白项目"
    bl_description = "清空当前 AluDIY 工程并新建；已有内容时先请求确认"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return getattr(context, "mode", "OBJECT") == "OBJECT"

    def invoke(self, context, event):
        project = get_project(context.scene)
        if project.members or project.nodes:
            return context.window_manager.invoke_confirm(
                self, event, title="清空当前工程并新建？",
                message=f"将移除当前 {len(project.members)} 根型材及 {len(project.nodes)} 个节点，请先保存。",
                confirm_text="清空并新建", icon="WARNING",
            )
        return self.execute(context)

    def execute(self, context):
        try:
            original_project = get_project(context.scene)
            _commit_project_update(
                context, original_project, empty_project(), selected_entity_id="",
            )
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            set_status(context.scene, f"新建失败，已保留原工程：{exc}")
            return {"CANCELLED"}
        set_status(context.scene, "已创建空白工程项目")
        return {"FINISHED"}


class ALUDIY_OT_delete_selected_members(bpy.types.Operator):
    bl_idname = "aludiy.delete_selected_members"
    bl_label = "删除工程型材"
    bl_description = "删除选中的 AluDIY 工程型材，并同步移除线、实体和孤立节点"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        area = getattr(context, "area", None)
        return (
            area is not None
            and area.type == "VIEW_3D"
            and getattr(context, "mode", "OBJECT") == "OBJECT"
            and bool(selected_member_ids(context))
        )

    def invoke(self, context, event):
        count = len(selected_member_ids(context))
        return context.window_manager.invoke_confirm(
            self,
            event,
            title="删除工程型材",
            message=f"将删除 {count} 根工程型材，并同步清理未使用节点。",
            confirm_text="删除",
            icon="WARNING",
        )

    def execute(self, context):
        original_project = get_project(context.scene)
        project = get_project(context.scene)
        selected_ids = selected_member_ids(context)
        member_ids = tuple(
            member_id for member_id in selected_ids if member_id in project.members
        )
        if not member_ids:
            message = "请选择有效的 AluDIY 工程线或型材实体"
            self.report({"WARNING"}, message)
            set_status(context.scene, message)
            return {"CANCELLED"}

        catalog = get_catalog()
        try:
            result = project.remove_members(member_ids)
            scene_adapter.rebuild_scene(context.scene, project, catalog)
            set_project(context.scene, project)
        except Exception as exc:
            try:
                scene_adapter.rebuild_scene(context.scene, original_project, catalog)
                set_project(context.scene, original_project)
            except Exception as restore_exc:
                print(f"AluDIY engineering-delete restore warning: {restore_exc}")
            self.report({"ERROR"}, str(exc))
            set_status(context.scene, f"工程删除失败：{exc}")
            return {"CANCELLED"}

        message = (
            f"已删除 {len(result.removed_member_ids)} 根工程型材，"
            f"清理 {len(result.removed_node_ids)} 个孤立节点"
        )
        self.report({"INFO"}, message)
        set_status(context.scene, message)
        return {"FINISHED"}


class ALUDIY_OT_create_sample_frame(bpy.types.Operator):
    bl_idname = "aludiy.create_sample_frame"
    bl_label = "插入矩形样例"
    bl_description = "在 3D 游标处插入世界 XY 矩形框架；保留已有工程，不自动合并节点"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return getattr(context, "mode", "OBJECT") == "OBJECT"

    def execute(self, context):
        scene_settings = settings(context.scene)
        try:
            width = parse_length_mm(scene_settings.sample_width_input)
            depth = parse_length_mm(scene_settings.sample_depth_input)
            profile_id = _selected_profile(context.scene)
            get_catalog().get(profile_id)
            original_project = get_project(context.scene)
            scale = 1.0 / scene_adapter.MM_TO_M
            origin = tuple(float(value) * scale for value in context.scene.cursor.location)
            result = append_sample_frame(
                original_project, width, depth, profile_id, origin_mm=origin,
            )
            _commit_project_update(
                context, original_project, result.project,
                selected_entity_id=result.member_ids[0],
            )
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            set_status(context.scene, f"样例插入失败，已保留原工程：{exc}")
            return {"CANCELLED"}
        set_status(
            context.scene,
            f"已插入 {width:g} × {depth:g} mm 样例（4 根）；"
            f"保留原有 {len(original_project.members)} 根型材；不自动连接",
        )
        return {"FINISHED"}


class ALUDIY_OT_rebuild_scene(bpy.types.Operator):
    bl_idname = "aludiy.rebuild_scene"
    bl_label = "从工程数据重建视图"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            project = get_project(context.scene)
            scene_adapter.rebuild_scene(context.scene, project, get_catalog())
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        set_status(context.scene, "线图和三维缓存已从工程数据重建")
        return {"FINISHED"}


class _CoordinateDialogMixin:
    def _set_position(self, position_mm) -> None:
        self.x_input = f"{position_mm[0]:g}"
        self.y_input = f"{position_mm[1]:g}"
        self.z_input = f"{position_mm[2]:g}"

    def _position(self):
        return (
            parse_distance_mm(self.x_input),
            parse_distance_mm(self.y_input),
            parse_distance_mm(self.z_input),
        )

    def draw(self, _context):
        layout = self.layout
        row = layout.row(align=True)
        row.prop(self, "x_input")
        row.prop(self, "y_input")
        row.prop(self, "z_input")


class ALUDIY_OT_edit_active_node(_CoordinateDialogMixin, bpy.types.Operator):
    bl_idname = "aludiy.edit_active_node"
    bl_label = "编辑节点坐标"
    bl_description = "用精确 XYZ 坐标移动工程节点，并更新全部相邻型材"
    bl_options = {"REGISTER", "UNDO"}

    x_input: StringProperty(name="X", default="0")
    y_input: StringProperty(name="Y", default="0")
    z_input: StringProperty(name="Z", default="0")

    @classmethod
    def poll(cls, context):
        return active_node_id(context) is not None

    def invoke(self, context, _event):
        node_id = active_node_id(context)
        if node_id is None:
            return {"CANCELLED"}
        self._set_position(get_project(context.scene).nodes[node_id].position_mm)
        return context.window_manager.invoke_props_dialog(self, width=480)

    def execute(self, context):
        node_id = active_node_id(context)
        if node_id is None:
            self.report({"WARNING"}, "请先选择工程节点")
            return {"CANCELLED"}
        try:
            position = self._position()
            original_project, project = _editable_project(context.scene)
            result = move_node(project, node_id, position)
            _commit_project_update(
                context,
                original_project,
                project,
                selected_entity_id=node_id,
            )
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            set_status(context.scene, f"节点修改失败：{exc}")
            return {"CANCELLED"}
        set_status(
            context.scene,
            f"{node_id} 已移动；更新 {len(result.affected_member_ids)} 根关联型材",
        )
        return {"FINISHED"}


class ALUDIY_OT_edit_member_endpoint(_CoordinateDialogMixin, bpy.types.Operator):
    bl_idname = "aludiy.edit_member_endpoint"
    bl_label = "编辑型材端点"
    bl_description = "精确修改型材起点或终点；共享节点会驱动相邻型材更新"
    bl_options = {"REGISTER", "UNDO"}

    x_input: StringProperty(name="X", default="0")
    y_input: StringProperty(name="Y", default="0")
    z_input: StringProperty(name="Z", default="0")

    endpoint: EnumProperty(
        name="端点",
        items=(
            ("START", "起点", "编辑 Member 的起始节点"),
            ("END", "终点", "编辑 Member 的终止节点"),
        ),
        default="START",
    )

    @classmethod
    def poll(cls, context):
        return active_member_id(context) is not None

    def _node_id(self, context):
        member_id = active_member_id(context)
        if member_id is None:
            return None
        member = get_project(context.scene).members[member_id]
        return member.start_node_id if self.endpoint == "START" else member.end_node_id

    def invoke(self, context, _event):
        node_id = self._node_id(context)
        if node_id is None:
            return {"CANCELLED"}
        self._set_position(get_project(context.scene).nodes[node_id].position_mm)
        return context.window_manager.invoke_props_dialog(self, width=480)

    def draw(self, context):
        self.layout.prop(self, "endpoint", expand=True)
        _CoordinateDialogMixin.draw(self, context)

    def execute(self, context):
        member_id = active_member_id(context)
        if member_id is None:
            self.report({"WARNING"}, "请先选择型材轴线或实体")
            return {"CANCELLED"}
        try:
            original_project, project = _editable_project(context.scene)
            member = project.members[member_id]
            node_id = member.start_node_id if self.endpoint == "START" else member.end_node_id
            result = move_node(project, node_id, self._position())
            _commit_project_update(
                context,
                original_project,
                project,
                selected_entity_id=member_id,
            )
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            set_status(context.scene, f"端点修改失败：{exc}")
            return {"CANCELLED"}
        label = "起点" if self.endpoint == "START" else "终点"
        set_status(
            context.scene,
            f"{member_id} {label}已更新；影响 {len(result.affected_member_ids)} 根型材",
        )
        return {"FINISHED"}


class ALUDIY_OT_translate_active_member(bpy.types.Operator):
    bl_idname = "aludiy.translate_active_member"
    bl_label = "精确平移型材"
    bl_description = "按 XYZ 增量平移型材的两个端点，并传播共享节点关系"
    bl_options = {"REGISTER", "UNDO"}

    x_input: StringProperty(name="ΔX", default="0")
    y_input: StringProperty(name="ΔY", default="0")
    z_input: StringProperty(name="ΔZ", default="0")

    @classmethod
    def poll(cls, context):
        return active_member_id(context) is not None

    def invoke(self, context, _event):
        self.x_input = self.y_input = self.z_input = "0"
        return context.window_manager.invoke_props_dialog(self, width=480)

    def draw(self, _context):
        row = self.layout.row(align=True)
        row.prop(self, "x_input")
        row.prop(self, "y_input")
        row.prop(self, "z_input")

    def execute(self, context):
        member_id = active_member_id(context)
        if member_id is None:
            self.report({"WARNING"}, "请先选择型材轴线或实体")
            return {"CANCELLED"}
        try:
            delta = (
                parse_distance_mm(self.x_input),
                parse_distance_mm(self.y_input),
                parse_distance_mm(self.z_input),
            )
            original_project, project = _editable_project(context.scene)
            result = translate_member(project, member_id, delta)
            _commit_project_update(
                context,
                original_project,
                project,
                selected_entity_id=member_id,
            )
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            set_status(context.scene, f"型材平移失败：{exc}")
            return {"CANCELLED"}
        set_status(
            context.scene,
            f"{member_id} 已平移 Δ({delta[0]:g}, {delta[1]:g}, {delta[2]:g}) mm；"
            f"影响 {len(result.affected_member_ids)} 根型材",
        )
        return {"FINISHED"}


class ALUDIY_OT_resize_active_member(bpy.types.Operator):
    bl_idname = "aludiy.resize_active_member"
    bl_label = "按精确长度调整型材"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        member_id = active_member_id(context)
        if not member_id:
            self.report({"WARNING"}, "请先选择型材轴线或实体")
            return {"CANCELLED"}
        scene_settings = settings(context.scene)
        try:
            length = parse_length_mm(scene_settings.length_input)
            original_project, project = _editable_project(context.scene)
            resize_member(
                project,
                member_id,
                length,
                anchor=scene_settings.resize_anchor,
            )
            _commit_project_update(
                context,
                original_project,
                project,
                selected_entity_id=member_id,
            )
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        set_status(
            context.scene,
            f"{member_id} 已调整为 {length:g} mm（{scene_settings.resize_anchor}）",
        )
        return {"FINISHED"}


class ALUDIY_OT_change_active_profile(bpy.types.Operator):
    bl_idname = "aludiy.change_active_profile"
    bl_label = "替换选中型材规格"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from .profile_tools import edit_selection
        try:
            changed = edit_selection(context, profile_type_id=_selected_profile(context.scene))
            return {"FINISHED"} if changed else {"CANCELLED"}
        except Exception as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}


class ALUDIY_OT_draw_member(bpy.types.Operator):
    bl_idname = "aludiy.draw_member"
    bl_label = "连续绘制型材线"
    bl_description = "在 XY/XZ/YZ 构造平面绘制；X/Y/Z 锁轴；支持精确长度或 @长度<角度"
    bl_options = {"REGISTER", "UNDO", "BLOCKING"}

    _start_mm = None
    _current_mm = None
    _typed = ""
    _committed_count = 0
    _snap_node_id = None
    _axis_lock = None
    _work_plane = "XY"
    _workplane_offset_mm = 0.0
    _cursor_error = ""
    _source_area_pointer = 0
    _source_region_pointer = 0
    _draw_feedback_handle = None
    _plane_lock = False
    _snap = None
    _display_snap = None
    _display_point = None
    _free = False
    _snap_options = ()
    _snap_choice = 0
    _input_error = ""

    @classmethod
    def poll(cls, context):
        from . import g_move
        if (context.area is None or context.area.type != "VIEW_3D" or context.mode != "OBJECT"
                or _ACTIVE_DRAW is not None or g_move._ACTIVE is not None):
            return False
        if context.workspace is not None and context.workspace.name == runtime.WORKSPACE_NAME:
            return view_sync.is_line_view_context(context)
        return True

    def _header(self, context, message: str = "") -> None:
        if context.area is not None:
            context.area.header_text_set(
                message
                or f"AluDIY 空间画线：{self._work_plane} 平面｜X/Y/Z 锁轴｜长度或 @长度<角度｜右键完成"
            )

    def _clear_header(self, context) -> None:
        if context.area is not None:
            context.area.header_text_set(None)

    def _resolved_end(self):
        return resolve_draw_endpoint(self._start_mm, self._current_mm, self._typed,
            axis=self._axis_lock if not self._plane_lock else None,
            work_plane=self._work_plane)

    def _refresh_preview(self, context) -> None:
        self._input_error = ''
        self._display_snap = self._snap
        self._display_point = self._current_mm
        if self._start_mm is not None and self._current_mm is not None:
            try:
                preview_end = self._resolved_end()
                self._display_point = preview_end
                if self._snap and math.dist(preview_end, self._snap.position_mm) > JOIN_TOLERANCE_MM:
                    self._display_snap = None
            except InputParseError as exc:
                self._input_error = str(exc)
                self._display_snap = None
                preview_end = self._current_mm
            _update_preview(context.scene, self._start_mm, preview_end)
        self._snap_node_id = self._display_snap.node_id if self._display_snap else None
        self._update_header(context)
        self._redraw_views(context)

    def _redraw_views(self, context):
        for area in context.window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

    def _update_header(self, context):
        if self._free:
            hint = 'Ctrl 自由定位 · 不吸附'
        elif self._typed and self._display_snap is None:
            hint = '精确长度优先 · 仅定位'
        else:
            hint = describe_candidate(self._display_snap, get_project(context.scene))
        if self._display_snap and len(self._snap_options) > 1:
            hint += f' · Tab {self._snap_choice % len(self._snap_options)+1}/{len(self._snap_options)}'
        if self._axis_lock:
            mode = ('平面排除 ' if self._plane_lock else '锁轴 ') + self._axis_lock
        else:
            mode = f'{self._work_plane} 自由定位面'
        self._header(context, f'{mode} | {self._input_error or self._cursor_error or hint} | 右键结束')

    def _locate(self, context, event):
        try:
            point, node_id = _point_from_event(context, event, self)
            if point is not None:
                self._current_mm, self._snap_node_id = point, node_id
                self._cursor_error = ''
        except (GeometryError, ValidationError) as exc:
            self._cursor_error = str(exc)
            self._snap = None
        self._refresh_preview(context)

    def _commit(self, context) -> bool:
        try:
            if getattr(self, '_cursor_error', '') and not self._typed:
                return False
            end_mm = self._resolved_end()
            if end_mm is None or self._start_mm is None:
                return False
            from .vendor.aludiy_core.associations import append_independent_member
            original = get_project(context.scene)
            project, member_id = append_independent_member(original, self._start_mm, end_mm,
                                                           _selected_profile(context.scene))
            _commit_project_update(context, original, project, selected_entity_id=member_id)
            member = project.members[member_id]
            self._start_mm = project.nodes[member.end_node_id].position_mm
            self._current_mm = self._start_mm
            self._typed = ""
            self._axis_lock = None
            self._plane_lock = False
            self._snap = self._display_snap = None
            self._snap_options, self._choice_keys = (), ()
            self._snap_choice = 0
            self._committed_count += 1
            set_status(context.scene, f"已创建 {member.id}，继续指定下一点")
            return True
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            set_status(context.scene, f"画线失败：{exc}")
            return False

    def modal(self, context, event):
        global _ACTIVE_DRAW
        if event.value == 'PRESS' and event.type in {'RIGHTMOUSE', 'ESC'}:
            _remove_preview(self._scene)
            _remove_draw_feedback_safely(self)
            context.window.cursor_modal_restore()
            self._clear_header(context)
            _ACTIVE_DRAW = None
            self._redraw_views(context)
            set_status(self._scene, f'连续画线结束，共创建 {self._committed_count} 根；未确认段已取消')
            return {'FINISHED' if self._committed_count else 'CANCELLED'}
        if context.scene != self._scene:
            self.cancel(context)
            return {'CANCELLED'}
        from . import profile_tools
        if profile_tools.modal_inset_guard(context,event):
            return {'RUNNING_MODAL'}
        free = bool(event.ctrl)
        if free != self._free:
            self._free = free
            if self._last_event is not None:
                self._locate(context, self._last_event)
        if event.type in {'LEFT_CTRL', 'RIGHT_CTRL'}:
            return {'RUNNING_MODAL'}
        if event.type == 'MIDDLEMOUSE':
            self._navigating = event.value != 'RELEASE'
            return {'PASS_THROUGH'}
        if self._navigating or event.type in {'WHEELUPMOUSE','WHEELDOWNMOUSE','TRACKPADPAN','TRACKPADZOOM'} or event.alt:
            return {'PASS_THROUGH'}
        region = _window_region(context.area)
        inside = (region is not None and context.area.as_pointer() == self._source_area_pointer
                  and region.x <= event.mouse_x < region.x+region.width
                  and region.y <= event.mouse_y < region.y+region.height)
        if inside:
            for overlay in context.area.regions:
                if overlay.type in {'UI', 'TOOLS'} and overlay.width > 1 and overlay.height > 1:
                    if overlay.x <= event.mouse_x < overlay.x+overlay.width and overlay.y <= event.mouse_y < overlay.y+overlay.height:
                        inside = False
        # Sidebar/header/other-view clicks never define engineering coordinates.
        if not inside:
            return {'RUNNING_MODAL'}
        if event.type == 'MOUSEMOVE':
            from types import SimpleNamespace
            self._last_event = SimpleNamespace(mouse_x=event.mouse_x, mouse_y=event.mouse_y)
            self._locate(context, event)
            return {'RUNNING_MODAL'}
        if event.value != 'PRESS':
            return {'RUNNING_MODAL'}
        if event.type == 'TAB':
            if len(self._snap_options)>1:
                self._snap_choice = (self._snap_choice + (-1 if event.shift else 1)) % len(self._snap_options)
                self._locate(context, event)
            return {'RUNNING_MODAL'}
        if event.type in {"X", "Y", "Z"}:
            plane = bool(event.shift)
            self._axis_lock = None if (self._axis_lock == event.type and self._plane_lock == plane) else event.type
            self._plane_lock = plane if self._axis_lock else False
            self._locate(context, event)
            self._refresh_preview(context)
            return {'RUNNING_MODAL'}
        if event.type == 'BACK_SPACE':
            self._typed = self._typed[:-1]
            self._locate(context, event)
            self._refresh_preview(context)
            return {'RUNNING_MODAL'}
        if event.type in {'RET','NUMPAD_ENTER'}:
            self._locate(context, event)
            if self._start_mm is not None and self._current_mm is not None:
                self._commit(context)
                self._refresh_preview(context)
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE':
            self._locate(context, event)
            if self._current_mm is None or self._cursor_error:
                return {'RUNNING_MODAL'}
            if self._start_mm is None:
                self._start_mm = self._current_mm
                set_status(context.scene, '已确定起点；X / Y / Z 锁轴，输入精确长度，Ctrl 暂停吸附')
            else:
                self._commit(context)
            self._refresh_preview(context)
            return {'RUNNING_MODAL'}
        if event.unicode and not event.ctrl:
            char = event.unicode
            if char in '0123456789.+-*/()mMcC@< ' and self._start_mm is not None:
                if char == '@':
                    self._axis_lock, self._plane_lock = None, False
                self._typed += char
                self._locate(context, event)
                self._refresh_preview(context)
                return {'RUNNING_MODAL'}
        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        global _ACTIVE_DRAW
        if _ACTIVE_DRAW is not None:
            self.report({'WARNING'}, '请先结束当前画线')
            return {'CANCELLED'}
        self._start_mm = self._current_mm = None
        self._typed, self._cursor_error, self._input_error = '', '', ''
        self._committed_count = 0
        self._snap_node_id = self._axis_lock = None
        self._snap = self._display_snap = self._display_point = None
        self._snap_options, self._choice_keys = (), ()
        self._snap_choice = 0
        self._plane_lock, self._free, self._navigating = False, bool(event.ctrl), False
        self._last_event = None
        self._scene = context.scene
        self._source_window_pointer = context.window.as_pointer()
        self._work_plane = settings(context.scene).work_plane
        try:
            self._workplane_offset_mm = parse_distance_mm(settings(context.scene).workplane_offset_input)
        except InputParseError as exc:
            self.report({'ERROR'}, f'工作平面偏移无效：{exc}')
            return {'CANCELLED'}
        window_region = _window_region(context.area)
        if window_region is None:
            return {'CANCELLED'}
        self._source_area_pointer = context.area.as_pointer()
        self._source_region_pointer = window_region.as_pointer()
        _remove_preview(context.scene)
        context.window.cursor_modal_set('CROSSHAIR')
        try:
            _overlay_module().add_draw_feedback(self)
        except Exception as exc:
            set_status(context.scene, f'画线工具已启动；动态反馈不可用：{exc}')
        self._header(context)
        _ACTIVE_DRAW = self
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        global _ACTIVE_DRAW
        _remove_preview(getattr(self, '_scene', context.scene))
        _remove_draw_feedback_safely(self)
        context.window.cursor_modal_restore()
        self._clear_header(context)
        _ACTIVE_DRAW = None
        self._redraw_views(context)


class ALUDIY_OT_export_project(bpy.types.Operator, ExportHelper):
    bl_idname = "aludiy.export_project"
    bl_label = "导出 AluDIY 项目"
    filename_ext = ".aludiy.json"
    filter_glob: StringProperty(default="*.aludiy.json", options={"HIDDEN"})

    def execute(self, context):
        try:
            save_project(get_project(context.scene), self.filepath)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        set_status(context.scene, f"项目已导出：{Path(self.filepath).name}")
        return {"FINISHED"}


class ALUDIY_OT_import_project(bpy.types.Operator, ImportHelper):
    bl_idname = "aludiy.import_project"
    bl_label = "导入 AluDIY 项目"
    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json;*.aludiy.json", options={"HIDDEN"})

    def execute(self, context):
        try:
            project = load_project(self.filepath)
            catalog = get_catalog()
            for member in project.members.values():
                catalog.get(member.profile_type_id)
            revision_warning = catalog_revision_warning(project, runtime.CATALOG_REVISION)
            set_project(context.scene, project)
            scene_adapter.rebuild_scene(context.scene, project, catalog)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        if revision_warning:
            self.report({"WARNING"}, revision_warning)
            set_status(context.scene, revision_warning)
        else:
            set_status(context.scene, f"项目已导入：{Path(self.filepath).name}")
        return {"FINISHED"}


class ALUDIY_OT_export_cutlist(bpy.types.Operator, ExportHelper):
    bl_idname = "aludiy.export_cutlist"
    bl_label = "导出长度 / 退让参考清单"
    filename_ext = ".csv"
    filter_glob: StringProperty(default="*.csv", options={"HIDDEN"})

    def execute(self, context):
        try:
            write_cutlist_csv(get_project(context.scene), self.filepath, get_catalog())
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        set_status(context.scene, f"切割清单已导出：{Path(self.filepath).name}")
        return {"FINISHED"}


_ADDON_KEYMAPS: list[tuple[object, object]] = []


def register_keymaps() -> None:
    if _ADDON_KEYMAPS:
        return
    key_config = bpy.context.window_manager.keyconfigs.addon
    if key_config is None:
        return
    keymap = key_config.keymaps.new(name="3D View", space_type="VIEW_3D")
    keymap_item = keymap.keymap_items.new(
        "aludiy.delete_selected_members",
        type="DEL",
        value="PRESS",
        ctrl=True,
        shift=True,
    )
    keymap_item.active = True
    _ADDON_KEYMAPS.append((keymap, keymap_item))


def unregister_keymaps() -> None:
    for keymap, keymap_item in reversed(_ADDON_KEYMAPS):
        try:
            keymap.keymap_items.remove(keymap_item)
        except (AttributeError, ReferenceError, RuntimeError):
            pass
    _ADDON_KEYMAPS.clear()


CLASSES = (
    ALUDIY_OT_setup_workspace,
    ALUDIY_OT_new_project,
    ALUDIY_OT_delete_selected_members,
    ALUDIY_OT_create_sample_frame,
    ALUDIY_OT_rebuild_scene,
    ALUDIY_OT_edit_active_node,
    ALUDIY_OT_edit_member_endpoint,
    ALUDIY_OT_translate_active_member,
    ALUDIY_OT_resize_active_member,
    ALUDIY_OT_change_active_profile,
    ALUDIY_OT_draw_member,
    ALUDIY_OT_export_project,
    ALUDIY_OT_import_project,
    ALUDIY_OT_export_cutlist,
)
