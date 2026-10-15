"""Dual-viewport setup, camera linking and semantic selection linking."""

from __future__ import annotations

from dataclasses import dataclass

import bpy

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


@dataclass(frozen=True, slots=True)
class ViewState:
    rotation: tuple[float, float, float, float]
    location: tuple[float, float, float]
    distance: float


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
    )


def _different(a: ViewState | None, b: ViewState | None, tolerance: float = 1.0e-7) -> bool:
    if a is None or b is None:
        return a != b
    values_a = (*a.rotation, *a.location, a.distance)
    values_b = (*b.rotation, *b.location, b.distance)
    return any(abs(left - right) > tolerance for left, right in zip(values_a, values_b))


def _copy_view(source: bpy.types.Area, target: bpy.types.Area, mode: str) -> None:
    source_region = _region_3d(source)
    target_region = _region_3d(target)
    if source_region is None or target_region is None:
        return
    target_region.view_rotation = source_region.view_rotation.copy()
    target_region.view_location = source_region.view_location.copy()
    if mode == "FULL":
        target_region.view_distance = source_region.view_distance
    target.tag_redraw()


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


def configure_dual_views(context: bpy.types.Context) -> int:
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
    if left_space.region_3d is not None:
        left_space.region_3d.view_perspective = "ORTHO"

    right_space.shading.type = "SOLID"
    right_space.shading.show_cavity = True
    right_space.shading.cavity_type = "BOTH"
    right_space.overlay.show_overlays = True
    if right_space.region_3d is not None:
        right_space.region_3d.view_perspective = "PERSP"

    settings(context.scene).view_sync_mode = "FULL"
    _copy_view(left, right, "FULL")
    _configure_view_collections(context.window, left, right)
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


def setup_workspace(context: bpy.types.Context) -> int:
    """Duplicate or activate the dedicated workspace and create two 3D areas."""

    existing = bpy.data.workspaces.get(WORKSPACE_NAME)
    if existing is not None:
        context.window.workspace = existing
    elif context.workspace.name != WORKSPACE_NAME:
        try:
            bpy.ops.workspace.duplicate()
            context.workspace.name = WORKSPACE_NAME
        except RuntimeError:
            # A restricted context can still use the current workspace.
            pass
    screen = context.window.screen
    areas = _view3d_areas(screen)
    if len(areas) < 2 and areas:
        area = max(areas, key=lambda item: item.width * item.height)
        region = _window_region(area)
        if region is not None:
            with context.temp_override(
                window=context.window,
                screen=screen,
                area=area,
                region=region,
            ):
                bpy.ops.screen.area_split(direction="VERTICAL", factor=0.5)
    return configure_dual_views(context)


def _sync_selection(window: bpy.types.Window) -> None:
    view_layer = window.view_layer
    active = view_layer.objects.active
    entity_id = entity_id_from_object(active)
    key = window.as_pointer()
    if entity_id == _LAST_ENTITY_BY_WINDOW.get(key):
        return
    _LAST_ENTITY_BY_WINDOW[key] = entity_id
    if entity_id is None:
        return
    for obj in window.scene.objects:
        if obj.name not in view_layer.objects:
            continue
        candidate = entity_id_from_object(obj)
        if candidate == entity_id:
            obj.select_set(True)
        elif obj.get("aludiy_managed"):
            obj.select_set(False)


def _sync_window(window: bpy.types.Window) -> None:
    if window.workspace.name != WORKSPACE_NAME:
        return
    mode = settings(window.scene).view_sync_mode
    areas = _view3d_areas(window.screen)
    if len(areas) >= 2 and mode != "OFF":
        current = {area.as_pointer(): _capture(area) for area in areas}
        changed = [
            area
            for area in areas
            if _different(
                current[area.as_pointer()],
                _VIEW_STATE.get((window.as_pointer(), area.as_pointer())),
            )
        ]
        if changed:
            context_area = bpy.context.area
            source = context_area if context_area in changed else changed[-1]
            for target in areas:
                if target != source:
                    _copy_view(source, target, mode)
            current = {area.as_pointer(): _capture(area) for area in areas}
        for area in areas:
            state = current.get(area.as_pointer())
            if state is not None:
                _VIEW_STATE[(window.as_pointer(), area.as_pointer())] = state
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


def register_timer() -> None:
    if not bpy.app.timers.is_registered(sync_tick):
        bpy.app.timers.register(sync_tick, first_interval=0.25, persistent=True)


def unregister_timer() -> None:
    if bpy.app.timers.is_registered(sync_tick):
        bpy.app.timers.unregister(sync_tick)
    _VIEW_STATE.clear()
    _LAST_ENTITY_BY_WINDOW.clear()
