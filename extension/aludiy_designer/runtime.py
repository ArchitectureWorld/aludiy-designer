"""Blender runtime state and the boundary to the vendored engineering core."""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any

import bpy

from .vendor.aludiy_core import ProfileCatalog, Project

CATALOG_REVISION = "alpha-2026.10"
PROJECT_SCHEMA_VERSION = "0.1.0"
EXTENSION_VERSION = "0.1.17-alpha"
WORKSPACE_NAME = "ALU DIY"
AXIS_COLLECTION = "ALUDIY_AXES"
SOLID_COLLECTION = "ALUDIY_SOLIDS"
HELPER_COLLECTION = "ALUDIY_HELPERS"

_PROFILE_ITEMS: list[tuple[str, str, str]] = []


def extension_root() -> Path:
    return Path(__file__).resolve().parent


def catalog_database_path() -> Path:
    return extension_root() / "resources" / "profile_catalog.sqlite"


@lru_cache(maxsize=1)
def get_catalog() -> ProfileCatalog:
    return ProfileCatalog.from_sqlite(catalog_database_path())


def profile_enum_items(_self: Any, _context: Any) -> list[tuple[str, str, str]]:
    global _PROFILE_ITEMS
    if not _PROFILE_ITEMS:
        _PROFILE_ITEMS = [
            (
                profile.profile_type_id,
                profile.display_name,
                f"{profile.supplier_id} / {profile.supplier_sku}",
            )
            for profile in get_catalog()
        ]
    return _PROFILE_ITEMS


def _solid_display_mode_updated(_self: Any, context: bpy.types.Context | None) -> None:
    if context is None or context.scene is None:
        return
    try:
        from . import scene_adapter

        from . import selection_state
        snapshot = selection_state.capture(context)
        scene_adapter.rebuild_scene(context.scene, get_project(context.scene), get_catalog())
        selection_state.restore(context, snapshot)
        label = "BOX" if _self.solid_display_mode == "BOX" else "型材细节"
        set_status(context.scene, f"三维显示精度已切换为 {label}")
    except Exception as exc:
        set_status(context.scene, f"三维显示精度更新失败：{exc}")


class AluDIYSceneSettings(bpy.types.PropertyGroup):
    joint_gap_input: bpy.props.StringProperty(name="端面间隙 mm", default="0", description="直角端面对接的非负端面间隙，按毫米解析")
    show_selection_lengths: bpy.props.BoolProperty(name="展开各杆件长度", default=False,
        description="查看完整多选集合的各根设计线长度，不是组总长")
    slot_target_member_id: bpy.props.StringProperty(default='', options={'HIDDEN','SKIP_SAVE'})
    slot_target_interface_id: bpy.props.StringProperty(default='', options={'HIDDEN','SKIP_SAVE'})
    slot_target_profile_id: bpy.props.StringProperty(default='', options={'HIDDEN','SKIP_SAVE'})
    slot_target_catalog_revision: bpy.props.StringProperty(default='', options={'HIDDEN','SKIP_SAVE'})
    edit_profile_id: bpy.props.EnumProperty(name="目标规格", items=profile_enum_items,
        description="只用于替换所选型材，不改变新画杆件的默认规格")
    profile_roll_input: bpy.props.StringProperty(name="截面角度", default="0",
        description="角度单位为度，可输入 45+45；不是长度，不接受 mm/m")
    show_section_inspector: bpy.props.BoolProperty(name="查看截面与槽位", default=True)
    inspected_member_id: bpy.props.StringProperty(default="", options={"HIDDEN","SKIP_SAVE"})
    inspected_profile_id: bpy.props.StringProperty(default="", options={"HIDDEN","SKIP_SAVE"})
    inspected_interface_id: bpy.props.StringProperty(default="", options={"HIDDEN","SKIP_SAVE"})
    endpoint_member_id: bpy.props.StringProperty(default="", options={"HIDDEN", "SKIP_SAVE"})
    endpoint_side: bpy.props.StringProperty(default="", options={"HIDDEN", "SKIP_SAVE"})
    move_connection_mode: bpy.props.EnumProperty(
        name="本次端点移动",
        items=(("KEEP", "保持连接", "共享节点驱动所有相连杆件"),
               ("DETACH", "断开此杆端", "只让选定型材端点离开公共连接点")),
        default="KEEP", options={"SKIP_SAVE"},
    )
    ground_snap_enabled: bpy.props.BoolProperty(name="地面标高吸附", default=True,
        description="仅定位到指定水平标高，不创建固定或承载约束")
    ground_elevation_input: bpy.props.StringProperty(name="地面标高", default="0",
        description="默认毫米，可输入 100、0.1m；不是型材外表面的落地检查")
    project_json: bpy.props.StringProperty(
        name="Project JSON",
        default="",
        options={"HIDDEN"},
    )
    active_profile_id: bpy.props.EnumProperty(
        name="型材",
        description="当前绘制或替换使用的型材类型",
        items=profile_enum_items,
    )
    length_input: bpy.props.StringProperty(
        name="长度",
        description="支持 1200、1.2m、600+20 等表达式",
        default="1200",
    )
    sample_width_input: bpy.props.StringProperty(name="样例宽度", default="1200")
    sample_depth_input: bpy.props.StringProperty(name="样例深度", default="600")
    resize_anchor: bpy.props.EnumProperty(
        name="固定方式",
        items=(
            ("START", "固定起端", "保持起端位置，移动末端"),
            ("END", "固定末端", "保持末端位置，移动起端"),
            ("CENTER", "固定中心", "两端相对中心对称移动"),
        ),
        default="START",
    )
    view_sync_mode: bpy.props.EnumProperty(
        name="视角联动",
        items=(
            ("FULL", "完全同步", "同步透视/正交投影、方向、中心、缩放与焦距"),
            ("ORIENTATION", "方向与中心", "投影、方向与中心同步；缩放分别控制"),
            ("OFF", "关闭", "两个视窗独立观察"),
        ),
        default="FULL",
    )
    work_plane: bpy.props.EnumProperty(
        name="工作平面",
        description="首点使用指定世界平面；连续画线时平面自动穿过当前起点",
        items=(
            ("XY", "XY 平面", "水平构造平面，适合底框和顶框"),
            ("XZ", "XZ 平面", "正立面构造平面，适合水平与竖向杆件"),
            ("YZ", "YZ 平面", "侧立面构造平面，适合水平与竖向杆件"),
        ),
        default="XY",
    )
    workplane_offset_input: bpy.props.StringProperty(
        name="首点平面偏移",
        description="无起点时构造平面沿法向的偏移，支持 800、0.8m 等表达式",
        default="0",
    )
    snap_pixel_radius: bpy.props.IntProperty(
        name="屏幕吸附半径",
        description="优先吸附任意高度的已有节点，单位为屏幕像素",
        default=14,
        min=4,
        max=48,
    )
    solid_display_mode: bpy.props.EnumProperty(
        name="三维显示精度",
        description="BOX 用于快速编辑；型材细节根据标准槽位语义生成交互预览",
        items=(
            ("BOX", "BOX", "仅显示型材外包络，更新速度最快"),
            ("PROFILE", "型材细节", "显示与目录槽位对应的 T 槽交互细节"),
        ),
        default="BOX",
        update=_solid_display_mode_updated,
    )
    snap_tolerance_mm: bpy.props.FloatProperty(
        name="吸附容差",
        default=10.0,
        min=0.1,
        soft_max=100.0,
    )
    status_message: bpy.props.StringProperty(name="状态", default="尚未创建项目")
    startup_diagnostics: bpy.props.StringProperty(
        name="启动诊断",
        default="",
        options={"HIDDEN"},
    )


def settings(scene: bpy.types.Scene) -> AluDIYSceneSettings:
    return scene.aludiy_settings


def empty_project() -> Project:
    return Project(
        project_id="P-BLENDER-001",
        catalog_revision=CATALOG_REVISION,
        schema_version=PROJECT_SCHEMA_VERSION,
    )


def get_project(scene: bpy.types.Scene) -> Project:
    """Read without mutating RNA, including first draw on an untouched scene.

    Panel.draw and operator poll callbacks are read-only Blender contexts.
    Only an explicit editing/import operator may persist through set_project.
    """
    raw = settings(scene).project_json.strip()
    if not raw:
        return empty_project()
    payload = json.loads(raw)
    project = Project.from_dict(payload)
    from .vendor.aludiy_core.associations import validate_slot_catalog
    validate_slot_catalog(project, get_catalog())
    return project


def set_project(scene: bpy.types.Scene, project: Project) -> None:
    from .vendor.aludiy_core.associations import validate_slot_catalog
    validate_slot_catalog(project, get_catalog())
    settings(scene).project_json = json.dumps(
        project.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def set_status(scene: bpy.types.Scene, message: str) -> None:
    settings(scene).status_message = str(message)


def entity_id_from_object(obj: bpy.types.Object | None) -> str | None:
    if obj is None:
        return None
    entity_id = obj.get("aludiy_entity_id") or obj.get("aludiy_source_id")
    return str(entity_id) if entity_id else None


def selected_member_ids(context: bpy.types.Context) -> tuple[str, ...]:
    objects = list(getattr(context, "selected_objects", ()))
    active_objects = getattr(getattr(context, "view_layer", None), "objects", None)
    active_object = getattr(active_objects, "active", None)

    result: list[str] = []
    if active_object in objects:
        active_id = entity_id_from_object(active_object)
        if active_id and active_id.startswith("M-"):
            result.append(active_id)
    for obj in objects:
        entity_id = entity_id_from_object(obj)
        if entity_id and entity_id.startswith("M-") and entity_id not in result:
            result.append(entity_id)
    return tuple(result)


def active_member_id(context: bpy.types.Context) -> str | None:
    member_ids = selected_member_ids(context)
    return member_ids[0] if member_ids else None


def selected_node_ids(context: bpy.types.Context) -> tuple[str, ...]:
    objects = list(getattr(context, "selected_objects", ()))
    active_objects = getattr(getattr(context, "view_layer", None), "objects", None)
    active_object = getattr(active_objects, "active", None)

    result: list[str] = []
    if active_object in objects:
        active_id = entity_id_from_object(active_object)
        if active_id and active_id.startswith("N-"):
            result.append(active_id)
    for obj in objects:
        entity_id = entity_id_from_object(obj)
        if entity_id and entity_id.startswith("N-") and entity_id not in result:
            result.append(entity_id)
    return tuple(result)


def active_node_id(context: bpy.types.Context) -> str | None:
    node_ids = selected_node_ids(context)
    return node_ids[0] if node_ids else None
