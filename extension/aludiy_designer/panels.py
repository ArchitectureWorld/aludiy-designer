"""Sidebar panels for the first AluDIY experience."""

import json

import bpy

from . import view_sync, g_move
from .runtime import (
    EXTENSION_VERSION,
    active_member_id,
    active_node_id,
    get_catalog,
    get_project,
    settings,
)
from .vendor.aludiy_core import member_length_mm



def selection_info(context):
    from . import profile_tools
    from .vendor.aludiy_core.section_picker import selection_readout
    mids,nids=g_move.selection_summary(context)
    return selection_readout(g_move.display_project(context.scene),mids,nids,
        active_member=profile_tools.active_inspector_member(context),endpoint=g_move.endpoint_context(context))


def draw_selection_readout(layout, context):
    """Read the same candidate as the viewports; never write a project on draw."""
    info=selection_info(context);s=settings(context.scene)
    layout.label(text='当前选择',icon='RESTRICT_SELECT_OFF')
    from . import joint_tools
    body=joint_tools.solution(context)
    if body and body.issues:
        layout.label(text='交接待处理 · 退让暂停 / 禁止出料',icon='ERROR')
    mids,nids=info['member_ids'],info['node_ids']
    if mids or nids:
        layout.label(text=f'已选 {len(mids)} 根型材 / {len(nids)} 个节点')
    else:
        layout.label(text='未选择型材或工程节点')
    mid=info['active_member']
    if mid:
        p=g_move.display_project(context.scene);m=p.members[mid]
        profile=get_catalog().get(m.profile_type_id)
        end={'START':' · 起端','END':' · 终端'}.get(info['endpoint'],'')
        layout.label(text=f'当前 {mid}{end} · {profile.section.width_mm:g}×{profile.section.height_mm:g} mm')
        layout.label(text=f"设计线长度  {info['length_mm']:.3f} mm")
        if body and not body.issues:
            item=body.lengths[mid]
            layout.label(text=f"实体参考长度  {item.cut_length_mm:.3f} mm")
            layout.label(text=f"起/终端退让  {item.start_setback_mm:g} / {item.end_setback_mm:g} mm")
    elif len(nids)==1:
        nid,xyz=info['node_coordinates'][0]
        layout.label(text=f'节点 {nid}')
        for axis,value in zip('XYZ',xyz):layout.label(text=f'{axis}  {value:.3f} mm')
    if len(mids)>1:
        layout.prop(s,'show_selection_lengths',text='各杆件长度',emboss=False,
                    icon='TRIA_DOWN' if s.show_selection_lengths else 'TRIA_RIGHT')
        if s.show_selection_lengths:
            for member,length in info['lengths']:
                layout.label(text=f'{member}   {length:.3f} mm')
    from . import operators
    op=operators._ACTIVE_DRAW
    if op is not None and op._scene==context.scene and op._start_mm is not None and op._display_point is not None:
        import math
        layout.label(text=f'正在绘制  {math.dist(op._start_mm,op._display_point):.3f} mm')


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
        draw_selection_readout(box, context)
        box.separator()
        row = box.row(align=True)
        row.operator("aludiy.setup_workspace", icon="WORKSPACE")
        row.operator("aludiy.new_project", icon="FILE_NEW")
        box.prop(scene_settings, "view_sync_mode")
        box.prop(scene_settings, "solid_display_mode")

        from . import profile_tools
        profile_tools.draw_panel(layout, context)
        from . import joint_tools
        joint_tools.draw_panel(layout, context)

        box = layout.box()
        box.label(text="移动与端点", icon="EMPTY_ARROWS")
        ep = g_move.endpoint_context(context)
        owner = g_move._handle_owner(context)
        if ep:
            project = get_project(context.scene)
            member = project.members[ep[0]]
            nid = member.start_node_id if ep[1] == "START" else member.end_node_id
            count = sum(nid in (m.start_node_id, m.end_node_id) for m in project.members.values())
            box.label(text=f"{ep[0]} · {'起端' if ep[1] == 'START' else '终端'} · 节点共用 {count} 根（含自身）")
            box.prop(scene_settings, "move_connection_mode", expand=True)
            if scene_settings.move_connection_mode == "DETACH":
                box.label(text="仅断开这根型材的这一端", icon="UNLINKED")
        elif owner:
            box.label(text=f"{owner} · 整根移动 / 点击下方端点")
        elif active_node_id(context):
            box.label(text="公共节点 · 保持连接移动")
        else:
            box.label(text="选型材→点端部圆点→G；多选可成组移动")
        row = box.row(align=True)
        row.enabled = bool(owner)
        op = row.operator("aludiy.select_endpoint", text="起端（绿）")
        op.endpoint = "START"
        op = row.operator("aludiy.select_endpoint", text="终端（红）")
        op.endpoint = "END"
        move = box.operator("aludiy.move_engineering", text="G · 鼠标移动", icon="EMPTY_ARROWS")
        move.connect_only = False
        box.operator("aludiy.translate_active_member", text="整根精确平移 ΔXYZ")
        mids,nids=g_move.selection_summary(context)
        box.label(text=f"已选 {len(mids)} 根型材 / {len(nids)} 个节点")
        relation_row=box.row(align=True)
        relation_row.operator("aludiy.create_associations",icon="LINKED")
        relation_row.operator("aludiy.remove_associations",icon="UNLINKED")
        box.label(text="G 吸附仅定位 · Ctrl 临时自由移动")
        box.label(text="多选相接杆件/节点 → 创建关联")
        box.label(text="杆身关联：设计轴线；主杆不切断")
        box.prop(scene_settings, "ground_snap_enabled")
        ground = box.row()
        ground.enabled = scene_settings.ground_snap_enabled
        ground.prop(scene_settings, "ground_elevation_input")
        box.label(text="输入默认 mm；X/Y/Z 锁轴；Tab 切换候选")

        box = layout.box()
        box.label(text="精确空间线驱动", icon="IPO_LINEAR")
        box.prop(scene_settings, "active_profile_id")
        box.prop(scene_settings, "work_plane", expand=True)
        box.prop(scene_settings, "workplane_offset_input")
        box.label(text="每段平面穿过当前起点；X / Y / Z 锁轴", icon="ORIENTATION_GLOBAL")
        box.label(text="画线 / G 共用：端点·中点·垂足·杆身")
        box.label(text="Ctrl 暂停吸附 · Tab 切换 · Shift+轴锁平面")
        box.label(text="吸附仅定位；需要联动请创建关联")
        draw_row = box.row(align=True)
        draw_row.enabled = view_sync.is_line_view_context(context)
        draw_row.operator("aludiy.draw_member", icon="GREASEPENCIL")
        if not view_sync.is_line_view_context(context):
            box.label(text="请在线图视窗启动画线", icon="INFO")
        row = box.row(align=True)
        row.prop(scene_settings, "sample_width_input")
        row.prop(scene_settings, "sample_depth_input")
        box.operator("aludiy.create_sample_frame", icon="MESH_CUBE")
        box.label(text="插入位置：3D 游标（世界 XY）")

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
        project = get_project(context.scene)
        node_id = active_node_id(context)
        member_id = active_member_id(context)

        if node_id:
            node = project.nodes.get(node_id)
            if node is None:
                layout.label(text=f"节点 {node_id} 不在工程数据中", icon="ERROR")
                return
            layout.label(text=f"节点：{node.id}", icon="EMPTY_AXIS")
            layout.label(
                text=(
                    f"X {node.position_mm[0]:.3f}  Y {node.position_mm[1]:.3f}  "
                    f"Z {node.position_mm[2]:.3f} mm"
                )
            )
            layout.operator("aludiy.edit_active_node", icon="ORIENTATION_GLOBAL")
            return

        if not member_id:
            layout.label(text="请选择型材轴线、三维实体或工程节点")
            return
        try:
            member = project.members[member_id]
            profile = get_catalog().get(member.profile_type_id)
        except Exception as exc:
            layout.label(text=str(exc), icon="ERROR")
            return

        start_node = project.nodes[member.start_node_id]
        end_node = project.nodes[member.end_node_id]
        layout.label(text=f"ID：{member.id}")
        layout.label(text=f"系统长度：{member_length_mm(project, member.id):.3f} mm")

        points = layout.box()
        points.label(text="起点坐标")
        points.label(
            text=f"X {start_node.position_mm[0]:.3f}  Y {start_node.position_mm[1]:.3f}  Z {start_node.position_mm[2]:.3f}"
        )
        op = points.operator("aludiy.edit_member_endpoint", text="编辑起点", icon="TRIA_LEFT")
        op.endpoint = "START"
        points.label(text="终点坐标")
        points.label(
            text=f"X {end_node.position_mm[0]:.3f}  Y {end_node.position_mm[1]:.3f}  Z {end_node.position_mm[2]:.3f}"
        )
        op = points.operator("aludiy.edit_member_endpoint", text="编辑终点", icon="TRIA_RIGHT")
        op.endpoint = "END"
        points.operator("aludiy.translate_active_member", text="精确平移", icon="EMPTY_ARROWS")

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
