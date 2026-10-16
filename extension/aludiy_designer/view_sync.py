"""Dual-viewport setup, camera linking and semantic selection linking."""

from __future__ import annotations

from dataclasses import dataclass

import bpy
from bpy.app.handlers import persistent

from .runtime import (
    AXIS_COLLECTION,
    HELPER_COLLECTION,
    SOLID_COLLECTION,
    WORKSPACE_NAME,
    entity_id_from_object,
    settings,
)

_TIMER_INTERVAL_SECONDS = 0.12
_VIEW_STATE: dict[tuple[int, int], "ViewState"] = {}
_LAST_ENTITY_BY_WINDOW: dict[int, str | None] = {}
_LAST_SELECTED_BY_WINDOW: dict[int, dict[str, str]] = {}
_WINDOW_SESSIONS: dict[int, tuple[int, int, str]] = {}
_PENDING_SETUP: dict[int, "WorkspaceSetup"] = {}
_SETUP_INTERVAL_SECONDS = 0.05
_SETUP_MAX_TICKS = 100


@dataclass(frozen=True, slots=True)
class ViewState:
    rotation: tuple[float, float, float, float]
    location: tuple[float, float, float]
    distance: float
    perspective: str
    lens: float
    clip_start: float
    clip_end: float
    camera_zoom: float
    camera_offset: tuple[float, float]
    use_local_camera: bool
    camera_name: str | None


@dataclass(slots=True)
class WorkspaceSetup:
    workspace_pointer: int
    scene_pointer: int
    initial_view: ViewState | None
    ticks: int = 0
    split_requested: bool = False


def _view3d_areas(screen: bpy.types.Screen) -> list[bpy.types.Area]:
    return sorted(
        (area for area in screen.areas if area.type == "VIEW_3D"),
        key=lambda area: (area.x, area.y),
    )


def is_line_view_area(screen: bpy.types.Screen, area: bpy.types.Area | None) -> bool:
    """Return whether *area* is the left engineering-line viewport."""

    if area is None or area.type != "VIEW_3D":
        return False
    areas = _view3d_areas(screen)
    return len(areas) >= 2 and area == areas[0]


def is_line_view_context(context: bpy.types.Context) -> bool:
    return (
        context.screen is not None
        and context.area is not None
        and context.workspace is not None
        and context.workspace.name == WORKSPACE_NAME
        and is_line_view_area(context.screen, context.area)
    )


def _region_3d(area: bpy.types.Area):
    space = area.spaces.active
    return getattr(space, "region_3d", None)


def _window_region(area: bpy.types.Area):
    return next((region for region in area.regions if region.type == "WINDOW"), None)


def _capture(area: bpy.types.Area) -> ViewState | None:
    region_3d = _region_3d(area)
    if region_3d is None:
        return None
    return ViewState(
        rotation=tuple(region_3d.view_rotation),
        location=tuple(region_3d.view_location),
        distance=float(region_3d.view_distance),
        perspective=region_3d.view_perspective,
        lens=float(area.spaces.active.lens),
        clip_start=float(area.spaces.active.clip_start),
        clip_end=float(area.spaces.active.clip_end),
        camera_zoom=float(region_3d.view_camera_zoom),
        camera_offset=tuple(region_3d.view_camera_offset),
        use_local_camera=area.spaces.active.use_local_camera,
        camera_name=(area.spaces.active.camera.name if area.spaces.active.camera else None),
    )


def _different(a: ViewState | None, b: ViewState | None, tolerance: float = 1.0e-7) -> bool:
    if a is None or b is None:
        return a != b
    if (a.perspective, a.use_local_camera, a.camera_name) != (b.perspective, b.use_local_camera, b.camera_name):
        return True
    values_a = (*a.rotation, *a.location, a.distance, a.lens, a.clip_start, a.clip_end, a.camera_zoom, *a.camera_offset)
    values_b = (*b.rotation, *b.location, b.distance, b.lens, b.clip_start, b.clip_end, b.camera_zoom, *b.camera_offset)
    return any(abs(left - right) > tolerance for left, right in zip(values_a, values_b))


def _copy_view(source: bpy.types.Area, target: bpy.types.Area, mode: str) -> None:
    source_region = _region_3d(source)
    target_region = _region_3d(target)
    if source_region is None or target_region is None:
        return
    target_region.view_rotation = source_region.view_rotation.copy()
    target_region.view_location = source_region.view_location.copy()
    # Projection is independent of orientation and distance. A Numpad-5 toggle
    # changes only this field, so both capture and copy must include it.
    target_region.view_perspective = source_region.view_perspective
    target.spaces.active.use_local_camera = source.spaces.active.use_local_camera
    target.spaces.active.camera = source.spaces.active.camera
    if mode == "FULL":
        target_region.view_distance = source_region.view_distance
        target_region.view_camera_zoom = source_region.view_camera_zoom
        target_region.view_camera_offset = source_region.view_camera_offset[:]
        for name in ("lens", "clip_start", "clip_end"):
            setattr(target.spaces.active, name, getattr(source.spaces.active, name))
    target.tag_redraw()


def _apply_initial_view(area: bpy.types.Area, state: ViewState) -> None:
    """Apply the invocation snapshot after deferred workspace/screen creation."""
    region = _region_3d(area)
    if region is None:
        raise RuntimeError("三维视窗尚未准备好")
    region.view_rotation = state.rotation
    region.view_location = state.location
    region.view_distance = state.distance
    region.view_perspective = state.perspective
    region.view_camera_zoom = state.camera_zoom
    region.view_camera_offset = state.camera_offset
    space = area.spaces.active
    space.lens, space.clip_start, space.clip_end = state.lens, state.clip_start, state.clip_end
    space.use_local_camera = state.use_local_camera
    space.camera = bpy.data.objects.get(state.camera_name) if state.camera_name else None
    area.tag_redraw()


def _forget_window(key: int) -> None:
    _WINDOW_SESSIONS.pop(key, None)
    for cache_key in tuple(_VIEW_STATE):
        if cache_key[0] == key:
            _VIEW_STATE.pop(cache_key, None)


def _ensure_role_collections(scene: bpy.types.Scene) -> None:
    for name in (AXIS_COLLECTION, SOLID_COLLECTION, HELPER_COLLECTION):
        collection = bpy.data.collections.get(name)
        if collection is None:
            collection = bpy.data.collections.new(name)
        if collection.name not in scene.collection.children:
            scene.collection.children.link(collection)


def _layer_collection_indices(view_layer: bpy.types.ViewLayer) -> dict[str, int]:
    """Mirror Blender's collection panel indexing: root is skipped, first child is 1."""

    result: dict[str, int] = {}
    index = 0

    def visit(layer_collection) -> None:
        nonlocal index
        for child in layer_collection.children:
            index += 1
            result[child.collection.name] = index
            visit(child)

    visit(view_layer.layer_collection)
    return result


def _isolate_collections(
    window: bpy.types.Window,
    area: bpy.types.Area,
    collection_names: tuple[str, ...],
) -> None:
    region = _window_region(area)
    if region is None:
        return
    space = area.spaces.active
    space.use_local_collections = True
    indices = _layer_collection_indices(window.view_layer)
    available: list[int] = []
    for name in collection_names:
        collection = bpy.data.collections.get(name)
        if collection is None or len(collection.all_objects) == 0:
            continue
        index = indices.get(name)
        if index is not None:
            available.append(index)
    if not available:
        return
    with bpy.context.temp_override(
        window=window,
        screen=window.screen,
        area=area,
        region=region,
    ):
        for position, collection_index in enumerate(available):
            result = bpy.ops.object.hide_collection(
                collection_index=collection_index,
                toggle=False,
                extend=position > 0,
            )
            if "FINISHED" not in result:
                raise RuntimeError(
                    f"cannot isolate local collection index {collection_index}"
                )


def _configure_view_collections(
    window: bpy.types.Window,
    left: bpy.types.Area,
    right: bpy.types.Area,
) -> None:
    _ensure_role_collections(window.scene)
    _isolate_collections(window, left, (AXIS_COLLECTION, HELPER_COLLECTION))
    _isolate_collections(window, right, (SOLID_COLLECTION,))


def configure_dual_views(context: bpy.types.Context, *, initial_view: ViewState | None = None) -> int:
    screen = context.window.screen
    areas = _view3d_areas(screen)
    if len(areas) < 2:
        return len(areas)
    left, right = areas[0], areas[-1]
    left_space = left.spaces.active
    right_space = right.spaces.active

    # The line view contains actual loose-edge engineering axes only. It is
    # not a wireframe rendering of the solid collection.
    left_space.shading.type = "WIREFRAME"
    left_space.overlay.show_overlays = True
    left_space.overlay.show_relationship_lines = True

    right_space.shading.type = "SOLID"
    right_space.shading.show_cavity = True
    right_space.shading.cavity_type = "BOTH"
    right_space.overlay.show_overlays = True

    settings(context.scene).view_sync_mode = "FULL"
    if initial_view is not None:
        _apply_initial_view(right, initial_view)
    # Existing files may have ORTHO on the left and PERSP on the right. Preserve
    # the user's right-hand 3D view, not the old hard-coded left projection.
    _copy_view(right, left, "FULL")
    _configure_view_collections(context.window, left, right)
    _forget_window(context.window.as_pointer())
    return len(areas)


def refresh_view_collections(scene: bpy.types.Scene) -> None:
    """Reapply per-viewport collection roles after cache objects are rebuilt."""

    manager = bpy.context.window_manager
    if manager is None:
        return
    for window in manager.windows:
        if window.scene != scene or window.workspace.name != WORKSPACE_NAME:
            continue
        areas = _view3d_areas(window.screen)
        if len(areas) >= 2:
            try:
                _configure_view_collections(window, areas[0], areas[-1])
            except RuntimeError as exc:
                print(f"AluDIY viewport collection warning: {exc}")


def setup_workspace(context: bpy.types.Context) -> None:
    """Request idempotent setup; finish only after Blender's UI notifier runs.

    workspace.duplicate() allocates a WorkSpace immediately but switches the
    window later. Never rename context.workspace or split context.screen here.
    """
    window = context.window
    if window is None or context.screen is None:
        raise RuntimeError("请在 Blender 主窗口中设置双视窗")
    key = window.as_pointer()
    if key in _PENDING_SETUP:
        return
    target = bpy.data.workspaces.get(WORKSPACE_NAME)
    initial_view = None
    if target is None:
        candidates = _view3d_areas(window.screen)
        if not candidates or getattr(window.screen, "show_fullscreen", False):
            raise RuntimeError("请先进入普通三维视窗并退出最大化/临时编辑器，再设置双视窗")
        source = context.area if context.area in candidates else max(candidates, key=lambda a: a.width * a.height)
        initial_view = _capture(source)
        old_ids = {ws.as_pointer() for ws in bpy.data.workspaces}
        with context.temp_override(window=window):
            result = bpy.ops.workspace.duplicate()
        created = [ws for ws in bpy.data.workspaces if ws.as_pointer() not in old_ids]
        if "FINISHED" not in result or len(created) != 1:
            raise RuntimeError("无法安全创建独立工作区；原工作区未改名或分屏")
        target = created[0]
        target.name = WORKSPACE_NAME
    # This assignment also requests a deferred UI switch. The timer below checks
    # the actual window/screen before touching it. Repeated requests coalesce.
    window.workspace = target
    _PENDING_SETUP[key] = WorkspaceSetup(target.as_pointer(), window.scene.as_pointer(), initial_view)
    settings(window.scene).status_message = "正在进入 AluDIY 并设置双视窗…"
    if not bpy.app.timers.is_registered(_workspace_setup_tick):
        bpy.app.timers.register(_workspace_setup_tick, first_interval=_SETUP_INTERVAL_SECONDS)


def _workspace_setup_tick() -> float | None:
    manager = bpy.context.window_manager
    windows = {w.as_pointer(): w for w in manager.windows} if manager else {}
    for key, request in tuple(_PENDING_SETUP.items()):
        window = windows.get(key)
        if window is None:
            _PENDING_SETUP.pop(key, None)
            continue
        try:
            request.ticks += 1
            if window.scene.as_pointer() != request.scene_pointer:
                raise RuntimeError("场景已改变，已取消工作区初始化")
            if request.ticks > _SETUP_MAX_TICKS:
                raise RuntimeError("工作区切换未完成；请退出临时编辑器后重试")
            if window.workspace.as_pointer() != request.workspace_pointer:
                continue
            areas = _view3d_areas(window.screen)
            if not areas:
                raise RuntimeError("AluDIY 工作区没有三维视窗，无法分屏")
            if len(areas) < 2:
                area = areas[0]
                region = _window_region(area)
                if request.split_requested or region is None or area.width < 80:
                    continue
                with bpy.context.temp_override(window=window, screen=window.screen, area=area, region=region):
                    result = bpy.ops.screen.area_split(direction="VERTICAL", factor=0.5)
                if "FINISHED" not in result:
                    raise RuntimeError("双视窗分屏未完成")
                request.split_requested = True
                continue  # Newly split areas have zero dimensions until layout refresh.
            if any(a.width < 32 or a.height < 32 or _region_3d(a) is None for a in areas):
                continue
            with bpy.context.temp_override(window=window, screen=window.screen, area=areas[-1], region=_window_region(areas[-1])):
                count = configure_dual_views(bpy.context, initial_view=request.initial_view)
            settings(window.scene).status_message = f"双视窗已就绪 · {count} 个三维视图 · 投影、方向、中心与缩放同步"
            _PENDING_SETUP.pop(key, None)
            _sync_window(window)
        except Exception as exc:
            _PENDING_SETUP.pop(key, None)
            settings(window.scene).status_message = f"双视窗配置失败：{exc}"
            print(f"AluDIY workspace setup warning: {exc}")
    return _SETUP_INTERVAL_SECONDS if _PENDING_SETUP else None


def _sync_selection(window: bpy.types.Window) -> None:
    from . import g_move
    if g_move._ACTIVE is not None:
        return
    view_layer = window.view_layer
    objects = [obj for obj in window.scene.objects
               if obj.get("aludiy_managed") and obj.name in view_layer.objects
               and entity_id_from_object(obj)]
    key = window.as_pointer()
    current = {o.name: entity_id_from_object(o) for o in objects if o.select_get()}
    previous = _LAST_SELECTED_BY_WINDOW.get(key, {})
    added = {eid for name, eid in current.items() if name not in previous}
    removed = {eid for name, eid in previous.items() if name not in current}
    desired = set(current.values()) - (removed - added)
    for obj in objects:
        wanted = entity_id_from_object(obj) in desired
        if obj.select_get() != wanted:
            obj.select_set(wanted)
    _LAST_SELECTED_BY_WINDOW[key] = {
        obj.name: entity_id_from_object(obj) for obj in objects if obj.select_get()
    }
    _LAST_ENTITY_BY_WINDOW[key] = entity_id_from_object(view_layer.objects.active)


def _sync_window(window: bpy.types.Window) -> None:
    key = window.as_pointer()
    if window.workspace.name != WORKSPACE_NAME:
        _forget_window(key)
        return
    if key in _PENDING_SETUP:
        return
    mode = settings(window.scene).view_sync_mode
    areas = _view3d_areas(window.screen)
    if len(areas) >= 2 and mode != "OFF":
        current = {area.as_pointer(): _capture(area) for area in areas}
        session = (window.workspace.as_pointer(), window.screen.as_pointer(), mode)
        entering = _WINDOW_SESSIONS.get(key) != session
        changed = [
            area
            for area in areas
            if _different(
                current[area.as_pointer()],
                _VIEW_STATE.get((window.as_pointer(), area.as_pointer())),
            )
        ]
        if entering or changed:
            context_area = bpy.context.area
            source = areas[-1] if entering else (context_area if context_area in changed else changed[-1])
            for target in areas:
                if target != source:
                    _copy_view(source, target, mode)
            current = {area.as_pointer(): _capture(area) for area in areas}
        for area in areas:
            state = current.get(area.as_pointer())
            if state is not None:
                _VIEW_STATE[(key, area.as_pointer())] = state
        _WINDOW_SESSIONS[key] = session
    elif mode == "OFF":
        _forget_window(key)
    _sync_selection(window)


def sync_tick() -> float:
    try:
        window_manager = bpy.context.window_manager
        if window_manager is not None:
            for window in window_manager.windows:
                _sync_window(window)
    except Exception as exc:  # Blender timer must stay alive and surface diagnostics.
        print(f"AluDIY view synchronization warning: {exc}")
    return _TIMER_INTERVAL_SECONDS


@persistent
def _on_file_load(_unused) -> None:
    # RNA addresses and deferred requests belong to the previous .blend.
    _PENDING_SETUP.clear()
    _VIEW_STATE.clear()
    _WINDOW_SESSIONS.clear()
    _LAST_ENTITY_BY_WINDOW.clear()
    _LAST_SELECTED_BY_WINDOW.clear()
    if bpy.app.timers.is_registered(_workspace_setup_tick):
        bpy.app.timers.unregister(_workspace_setup_tick)


def register_timer() -> None:
    if _on_file_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_file_load)
    if not bpy.app.timers.is_registered(sync_tick):
        bpy.app.timers.register(sync_tick, first_interval=0.25, persistent=True)


def unregister_timer() -> None:
    if bpy.app.timers.is_registered(sync_tick):
        bpy.app.timers.unregister(sync_tick)
    if bpy.app.timers.is_registered(_workspace_setup_tick):
        bpy.app.timers.unregister(_workspace_setup_tick)
    if _on_file_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_file_load)
    _PENDING_SETUP.clear()
    _VIEW_STATE.clear()
    _WINDOW_SESSIONS.clear()
    _LAST_ENTITY_BY_WINDOW.clear()
    _LAST_SELECTED_BY_WINDOW.clear()
