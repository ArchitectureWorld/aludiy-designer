"""User-facing operators for the AluDIY Blender alpha."""

import math
from pathlib import Path

import bpy
from bpy.props import StringProperty
from bpy_extras import view3d_utils
from bpy_extras.io_utils import ExportHelper, ImportHelper
from mathutils import Vector

from . import runtime, scene_adapter, view_sync
from .runtime import (
    HELPER_COLLECTION,
    active_member_id,
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
    ValidationError,
    catalog_revision_warning,
    create_sample_frame,
    load_project,
    parse_distance_mm,
    parse_length_mm,
    parse_polar,
    resize_member,
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

_PREVIEW_NAME = "_ALUDIY_MEMBER_PREVIEW"


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
    origin = view3d_utils.region_2d_to_origin_3d(region, region_data, coordinate)
    direction = view3d_utils.region_2d_to_vector_3d(region, region_data, coordinate)
    return (
        tuple(float(value) * 1000.0 for value in origin),
        tuple(float(value) for value in direction),
    )


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
    project = get_project(context.scene)
    snapped = _nearest_node_in_view(
        context,
        event,
        project,
        settings(context.scene).snap_pixel_radius,
    )
    if (
        snapped is not None
        and operator._start_mm is not None
        and operator._axis_lock is not None
        and not point_is_on_axis(
            snapped.position_mm,
            axis_origin_mm=operator._start_mm,
            axis=operator._axis_lock,
            tolerance_mm=settings(context.scene).snap_tolerance_mm,
        )
    ):
        snapped = None
    if snapped is not None:
        return snapped.position_mm, snapped.id
    ray = _view_ray_mm(context, event)
    if ray is None:
        return None, None
    ray_origin_mm, ray_direction = ray
    if operator._start_mm is not None and operator._axis_lock is not None:
        point = closest_point_on_axis_to_ray(
            axis_origin_mm=operator._start_mm,
            axis=operator._axis_lock,
            ray_origin_mm=ray_origin_mm,
            ray_direction=ray_direction,
        )
    else:
        point = point_on_workplane_from_ray(
            ray_origin_mm=ray_origin_mm,
            ray_direction=ray_direction,
            work_plane=operator._work_plane,
            offset_mm=operator._workplane_offset_mm,
            start_mm=operator._start_mm,
        )
    snapped_world = _nearest_node(project, point, settings(context.scene).snap_tolerance_mm)
    if snapped_world is not None:
        return snapped_world.position_mm, snapped_world.id
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
            count = view_sync.setup_workspace(context)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            set_status(context.scene, f"双视窗配置失败：{exc}")
            return {"CANCELLED"}
        set_status(context.scene, f"双视窗已配置，检测到 {count} 个三维视图")
        return {"FINISHED"}


class ALUDIY_OT_new_project(bpy.types.Operator):
    bl_idname = "aludiy.new_project"
    bl_label = "新建空白项目"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        project = empty_project()
        set_project(context.scene, project)
        scene_adapter.rebuild_scene(context.scene, project, get_catalog())
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
    bl_label = "生成矩形样例框架"
    bl_description = "根据精确宽度和深度生成四根线及联动实体"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene_settings = settings(context.scene)
        try:
            width = parse_length_mm(scene_settings.sample_width_input)
            depth = parse_length_mm(scene_settings.sample_depth_input)
            profile_id = _selected_profile(context.scene)
            get_catalog().get(profile_id)
            project = create_sample_frame(width, depth, profile_id)
            set_project(context.scene, project)
            scene_adapter.rebuild_scene(context.scene, project, get_catalog())
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            set_status(context.scene, f"样例生成失败：{exc}")
            return {"CANCELLED"}
        set_status(context.scene, f"已生成 {width:g} × {depth:g} mm 矩形框架")
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
            project = get_project(context.scene)
            resize_member(
                project,
                member_id,
                length,
                anchor=scene_settings.resize_anchor,
            )
            set_project(context.scene, project)
            scene_adapter.rebuild_scene(context.scene, project, get_catalog())
            scene_adapter.select_entity(context.scene, context.view_layer, member_id)
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
        member_id = active_member_id(context)
        if not member_id:
            self.report({"WARNING"}, "请先选择型材轴线或实体")
            return {"CANCELLED"}
        profile_id = _selected_profile(context.scene)
        try:
            catalog = get_catalog()
            catalog.get(profile_id)
            project = get_project(context.scene)
            member = project.members[member_id]
            member.profile_type_id = profile_id
            member.revision += 1
            set_project(context.scene, project)
            scene_adapter.rebuild_scene(context.scene, project, catalog)
            scene_adapter.select_entity(context.scene, context.view_layer, member_id)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        set_status(context.scene, f"{member_id} 已替换为 {profile_id}")
        return {"FINISHED"}


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

    @classmethod
    def poll(cls, context):
        if context.area is None or context.area.type != "VIEW_3D":
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
        if self._start_mm is None or self._current_mm is None:
            return self._current_mm
        if not self._typed:
            return self._current_mm
        if self._typed.startswith("@"):
            polar = parse_polar(self._typed)
            return polar_endpoint_mm(
                self._start_mm,
                self._work_plane,
                polar.length_mm,
                polar.angle_deg,
            )
        length = parse_length_mm(self._typed)
        if self._axis_lock is not None:
            direction = Vector(axis_vector(self._axis_lock))
            candidate = Vector(self._current_mm) - Vector(self._start_mm)
            if candidate.dot(direction) < 0.0:
                direction.negate()
        else:
            direction = Vector(self._current_mm) - Vector(self._start_mm)
        if direction.length < 1.0e-9:
            direction = Vector((1.0, 0.0, 0.0))
        else:
            direction.normalize()
        point = Vector(self._start_mm) + direction * length
        return tuple(point)

    def _refresh_preview(self, context) -> None:
        if self._start_mm is not None and self._current_mm is not None:
            try:
                preview_end = self._resolved_end()
            except InputParseError:
                preview_end = self._current_mm
            _update_preview(context.scene, self._start_mm, preview_end)
        if context.area is not None:
            context.area.tag_redraw()

    def _commit(self, context) -> bool:
        try:
            end_mm = self._resolved_end()
            if end_mm is None or self._start_mm is None:
                return False
            project = get_project(context.scene)
            tolerance = settings(context.scene).snap_tolerance_mm
            start_node = _nearest_node(project, self._start_mm, tolerance)
            end_node = _nearest_node(project, end_mm, tolerance)
            if start_node is None:
                start_node = Node(
                    id=_next_id("N", project.nodes),
                    position_mm=tuple(self._start_mm),
                )
                project.add_node(start_node)
            if end_node is None:
                end_node = Node(
                    id=_next_id("N", project.nodes),
                    position_mm=tuple(end_mm),
                )
                project.add_node(end_node)
            if start_node.id == end_node.id:
                raise ValidationError("起点与终点吸附到了同一个节点")
            member = Member(
                id=_next_id("M", project.members),
                start_node_id=start_node.id,
                end_node_id=end_node.id,
                profile_type_id=_selected_profile(context.scene),
            )
            project.add_member(member)
            set_project(context.scene, project)
            scene_adapter.rebuild_scene(context.scene, project, get_catalog())
            scene_adapter.select_entity(context.scene, context.view_layer, member.id)
            self._start_mm = end_node.position_mm
            self._current_mm = end_node.position_mm
            self._typed = ""
            self._axis_lock = None
            self._committed_count += 1
            set_status(context.scene, f"已创建 {member.id}，继续指定下一点")
            return True
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            set_status(context.scene, f"画线失败：{exc}")
            return False

    def modal(self, context, event):
        if event.type == "MOUSEMOVE":
            try:
                point, snap_node_id = _point_from_event(context, event, self)
                if point is not None:
                    self._current_mm = point
                    self._snap_node_id = snap_node_id
                    self._cursor_error = ""
            except GeometryError as exc:
                self._cursor_error = str(exc)
            lock_label = f" · {self._axis_lock} 轴锁定" if self._axis_lock else ""
            hint = self._cursor_error or self._typed or "鼠标定位"
            self._header(context, f"{self._work_plane} 平面{lock_label} · {hint}")
            self._refresh_preview(context)
            return {"RUNNING_MODAL"}

        if event.value == "PRESS" and event.type in {"X", "Y", "Z"}:
            self._axis_lock = None if self._axis_lock == event.type else event.type
            try:
                point, snap_node_id = _point_from_event(context, event, self)
                if point is not None:
                    self._current_mm = point
                    self._snap_node_id = snap_node_id
                    self._cursor_error = ""
            except GeometryError as exc:
                self._cursor_error = str(exc)
            self._header(context)
            self._refresh_preview(context)
            return {"RUNNING_MODAL"}

        if event.value == "PRESS" and event.type == "BACK_SPACE":
            self._typed = self._typed[:-1]
            self._refresh_preview(context)
            return {"RUNNING_MODAL"}

        if event.value == "PRESS" and event.unicode:
            character = event.unicode
            if character in "0123456789.+-*/()mMcC@< ":
                if character == "@":
                    self._axis_lock = None
                self._typed += character
                self._header(context, f"输入：{self._typed}")
                self._refresh_preview(context)
                return {"RUNNING_MODAL"}

        if event.value == "PRESS" and event.type in {"RET", "NUMPAD_ENTER"}:
            if self._start_mm is not None and self._current_mm is not None:
                self._commit(context)
            return {"RUNNING_MODAL"}

        if event.value == "PRESS" and event.type == "LEFTMOUSE":
            try:
                point, snap_node_id = _point_from_event(context, event, self)
            except GeometryError as exc:
                set_status(context.scene, f"无法定位空间点：{exc}")
                return {"RUNNING_MODAL"}
            if point is None:
                return {"RUNNING_MODAL"}
            self._snap_node_id = snap_node_id
            self._current_mm = point
            if self._start_mm is None:
                self._start_mm = self._current_mm
                _update_preview(context.scene, self._start_mm, self._start_mm)
                set_status(context.scene, "已确定起点，请指定终点或输入精确长度")
            else:
                self._commit(context)
            context.area.tag_redraw()
            return {"RUNNING_MODAL"}

        if event.value == "PRESS" and event.type in {"RIGHTMOUSE", "ESC"}:
            _remove_preview(context.scene)
            _remove_draw_feedback_safely(self)
            context.window.cursor_modal_restore()
            self._clear_header(context)
            context.area.tag_redraw()
            set_status(context.scene, f"连续画线结束，共创建 {self._committed_count} 根型材")
            return {"FINISHED" if self._committed_count else "CANCELLED"}

        return {"RUNNING_MODAL"}

    def invoke(self, context, event):
        self._start_mm = None
        self._current_mm = None
        self._typed = ""
        self._committed_count = 0
        self._snap_node_id = None
        self._axis_lock = None
        self._cursor_error = ""
        self._work_plane = settings(context.scene).work_plane
        try:
            self._workplane_offset_mm = parse_distance_mm(
                settings(context.scene).workplane_offset_input
            )
        except InputParseError as exc:
            self.report({"ERROR"}, f"工作平面偏移无效：{exc}")
            return {"CANCELLED"}
        window_region = _window_region(context.area)
        if window_region is None:
            self.report({"ERROR"}, "当前三维视图没有可用的 WINDOW 区域")
            return {"CANCELLED"}
        self._source_area_pointer = context.area.as_pointer()
        self._source_region_pointer = window_region.as_pointer()
        _remove_preview(context.scene)
        context.window.cursor_modal_set("CROSSHAIR")
        try:
            _overlay_module().add_draw_feedback(self)
        except Exception as exc:
            set_status(
                context.scene,
                f"画线工具已启动；动态绘制反馈不可用：{exc}",
            )
        self._header(context)
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {"RUNNING_MODAL"}

    def cancel(self, context):
        _remove_preview(context.scene)
        _remove_draw_feedback_safely(self)
        context.window.cursor_modal_restore()
        self._clear_header(context)
        context.area.tag_redraw()


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
    bl_label = "导出基础切割清单"
    filename_ext = ".csv"
    filter_glob: StringProperty(default="*.csv", options={"HIDDEN"})

    def execute(self, context):
        try:
            write_cutlist_csv(get_project(context.scene), self.filepath)
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
    ALUDIY_OT_resize_active_member,
    ALUDIY_OT_change_active_profile,
    ALUDIY_OT_draw_member,
    ALUDIY_OT_export_project,
    ALUDIY_OT_import_project,
    ALUDIY_OT_export_cutlist,
)
