"""Sidebar panels for the first AluDIY experience."""

import json

import bpy

from . import view_sync
from .runtime import EXTENSION_VERSION, active_member_id, get_catalog, get_project, settings
from .vendor.aludiy_core import member_length_mm


class ALUDIY_PT_main(bpy.types.Panel):
    bl_label = "AluDIY 设计"
    bl_idname = "ALUDIY_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AluDIY"

    def draw(self, context):
        layout = self.layout
        scene_settings = settings(context.scene)

        header = layout.row(align=True)
        header.label(text=f"AluDIY {EXTENSION_VERSION}", icon="CHECKMARK")
        if scene_settings.startup_diagnostics:
            warning = layout.box()
            warning.alert = True
            warning.label(text="核心面板已加载；部分视口服务不可用", icon="ERROR")
            for item in scene_settings.startup_diagnostics.split("；"):
                if item:
                    warning.label(text=item)

        box = layout.box()
        row = box.row(align=True)
        row.operator("aludiy.setup_workspace", icon="WORKSPACE")
        row.operator("aludiy.new_project", icon="FILE_NEW")
        box.prop(scene_settings, "view_sync_mode")
        box.prop(scene_settings, "solid_display_mode")

        box = layout.box()
        box.label(text="精确空间线驱动", icon="IPO_LINEAR")
        box.prop(scene_settings, "active_profile_id")
        box.prop(scene_settings, "work_plane", expand=True)
        box.prop(scene_settings, "workplane_offset_input")
        box.label(text="每段平面穿过当前起点；X / Y / Z 锁轴", icon="ORIENTATION_GLOBAL")
        draw_row = box.row(align=True)
        draw_row.enabled = view_sync.is_line_view_context(context)
        draw_row.operator("aludiy.draw_member", icon="GREASEPENCIL")
        if not view_sync.is_line_view_context(context):
            box.label(text="请在线图视窗启动画线", icon="INFO")
        row = box.row(align=True)
        row.prop(scene_settings, "sample_width_input")
        row.prop(scene_settings, "sample_depth_input")
        box.operator("aludiy.create_sample_frame", icon="MESH_CUBE")

        box = layout.box()
        box.label(text="选中型材", icon="MOD_LENGTH")
        box.prop(scene_settings, "length_input")
        box.prop(scene_settings, "resize_anchor")
        row = box.row(align=True)
        row.operator("aludiy.resize_active_member", icon="DRIVER_DISTANCE")
        row.operator("aludiy.change_active_profile", icon="FILE_REFRESH")
        delete_row = box.row(align=True)
        delete_row.operator("aludiy.delete_selected_members", icon="TRASH")
        delete_row.label(text="Ctrl + Shift + Delete")
        box.operator("aludiy.rebuild_scene", icon="RECOVER_LAST")

        box = layout.box()
        box.label(text="工程数据", icon="FILE_FOLDER")
        row = box.row(align=True)
        row.operator("aludiy.import_project", icon="IMPORT")
        row.operator("aludiy.export_project", icon="EXPORT")
        box.operator("aludiy.export_cutlist", icon="SPREADSHEET")

        layout.separator()
        status = layout.box()
        status.label(text=scene_settings.status_message, icon="INFO")


class ALUDIY_PT_selection(bpy.types.Panel):
    bl_label = "工程对象信息"
    bl_idname = "ALUDIY_PT_selection"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AluDIY"
    bl_parent_id = "ALUDIY_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        member_id = active_member_id(context)
        if not member_id:
            layout.label(text="请选择型材轴线或三维实体")
            return
        try:
            project = get_project(context.scene)
            member = project.members[member_id]
            profile = get_catalog().get(member.profile_type_id)
        except Exception as exc:
            layout.label(text=str(exc), icon="ERROR")
            return
        layout.label(text=f"ID：{member.id}")
        layout.label(text=f"系统长度：{member_length_mm(project, member.id):.3f} mm")
        layout.label(text=f"型材：{profile.display_name}")
        layout.label(text=f"截面：{profile.section.width_mm:g} × {profile.section.height_mm:g} mm")
        layout.label(text=f"槽轨：{len(profile.section.interfaces)} 条")
        layout.label(text=f"截面旋转：{member.roll_deg:g}°")
        interfaces = layout.box()
        interfaces.label(text="稳定接口 ID")
        for interface_id in sorted(profile.section.interfaces):
            interface = profile.section.interfaces[interface_id]
            interfaces.label(
                text=f"{interface.id}  lane {interface.lane_index + 1}/{interface.lane_count}"
            )
        active = context.view_layer.objects.active
        if active is not None and active.get("aludiy_interface_ids"):
            try:
                ids = json.loads(active["aludiy_interface_ids"])
                layout.label(text=f"缓存接口：{len(ids)}")
            except (TypeError, json.JSONDecodeError):
                layout.label(text="缓存接口元数据无效", icon="ERROR")


CLASSES = (ALUDIY_PT_main, ALUDIY_PT_selection)
