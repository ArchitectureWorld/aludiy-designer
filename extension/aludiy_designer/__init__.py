"""AluDIY Designer Blender extension entry point."""

from __future__ import annotations

import bpy

from . import operators, panels, runtime, view_sync
from .vendor.aludiy_core.startup import try_optional_service

bl_info = {
    "name": "AluDIY Designer",
    "author": "ArchitectureWorld",
    "version": (0, 1, 5),
    "blender": (5, 2, 0),
    "location": "View3D > Sidebar > AluDIY",
    "description": "Line-driven aluminum extrusion design with linked 3D feedback",
    "category": "3D View",
}

CLASSES = (
    runtime.AluDIYSceneSettings,
    *operators.CLASSES,
    *panels.CLASSES,
)

_OPTIONAL_SERVICE_ERRORS: list[str] = []


def _register_overlay() -> None:
    # Deliberately lazy: an unavailable GPU overlay must never hide the core UI.
    from . import viewport_overlay

    viewport_overlay.register_direction_overlay()


def _unregister_overlay() -> None:
    try:
        from . import viewport_overlay

        viewport_overlay.unregister_direction_overlay()
    except Exception as exc:
        print(f"AluDIY optional overlay cleanup warning: {exc}")


def _publish_startup_diagnostics() -> None:
    message = "；".join(_OPTIONAL_SERVICE_ERRORS)
    for scene in getattr(bpy.data, "scenes", ()):
        try:
            scene.aludiy_settings.startup_diagnostics = message
            if message:
                scene.aludiy_settings.status_message = f"核心界面已加载；可选服务异常：{message}"
        except Exception:
            continue


def _register_optional_services() -> None:
    _OPTIONAL_SERVICE_ERRORS.clear()
    for name, callback in (
        ("视角同步", view_sync.register_timer),
        ("视口绘制反馈", _register_overlay),
        ("工程删除快捷键", operators.register_keymaps),
    ):
        error = try_optional_service(name, callback)
        if error is not None:
            _OPTIONAL_SERVICE_ERRORS.append(error)
            print(f"AluDIY optional service warning: {error}")
    _publish_startup_diagnostics()


def register() -> None:
    registered: list[type] = []
    try:
        for cls in CLASSES:
            bpy.utils.register_class(cls)
            registered.append(cls)
        bpy.types.Scene.aludiy_settings = bpy.props.PointerProperty(
            type=runtime.AluDIYSceneSettings
        )
    except Exception:
        if hasattr(bpy.types.Scene, "aludiy_settings"):
            del bpy.types.Scene.aludiy_settings
        for cls in reversed(registered):
            try:
                bpy.utils.unregister_class(cls)
            except Exception:
                pass
        raise

    # Core classes and the N-panel are now live. Optional services may degrade.
    _register_optional_services()


def unregister() -> None:
    try:
        operators.unregister_keymaps()
    except Exception as exc:
        print(f"AluDIY optional keymap cleanup warning: {exc}")
    _unregister_overlay()
    try:
        view_sync.unregister_timer()
    except Exception as exc:
        print(f"AluDIY optional view-sync cleanup warning: {exc}")
    if hasattr(bpy.types.Scene, "aludiy_settings"):
        del bpy.types.Scene.aludiy_settings
    for cls in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
    _OPTIONAL_SERVICE_ERRORS.clear()
