"""Run inside Blender 5.2.x to smoke-test registration and scene generation.

Example:
    blender --background --factory-startup --python tools/blender_smoke_test.py
"""

from pathlib import Path
import sys

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "extension"))

import aludiy_designer  # noqa: E402
from aludiy_designer import scene_adapter  # noqa: E402
from aludiy_designer.runtime import get_catalog, set_project  # noqa: E402
from aludiy_designer.vendor.aludiy_core import create_sample_frame  # noqa: E402


def main() -> None:
    aludiy_designer.register()
    try:
        project = create_sample_frame(1200.0, 600.0, "generic:tslot-2020@0.1")
        set_project(bpy.context.scene, project)
        scene_adapter.rebuild_scene(bpy.context.scene, project, get_catalog())
        axes = [obj for obj in bpy.context.scene.objects if obj.get("aludiy_entity_type") == "MEMBER_AXIS"]
        solids = [obj for obj in bpy.context.scene.objects if obj.get("aludiy_entity_type") == "MEMBER_SOLID"]
        nodes = [obj for obj in bpy.context.scene.objects if obj.get("aludiy_entity_type") == "NODE"]
        assert len(axes) == 4, len(axes)
        assert len(solids) == 4, len(solids)
        assert len(nodes) == 4, len(nodes)
        assert all(len(obj.data.vertices) == 8 for obj in solids)

        bpy.context.scene.aludiy_settings.solid_display_mode = "PROFILE"
        solids = [
            obj
            for obj in bpy.context.scene.objects
            if obj.get("aludiy_entity_type") == "MEMBER_SOLID"
        ]
        assert len(solids) == 4, len(solids)
        assert all(len(obj.data.vertices) == 72 for obj in solids)
        assert all(obj.get("aludiy_display_mode") == "PROFILE" for obj in solids)

        removal = project.remove_members(["M-001"])
        assert removal.removed_member_ids == ("M-001",)
        assert removal.removed_node_ids == ()
        set_project(bpy.context.scene, project)
        scene_adapter.rebuild_scene(bpy.context.scene, project, get_catalog())
        axes = [obj for obj in bpy.context.scene.objects if obj.get("aludiy_entity_type") == "MEMBER_AXIS"]
        solids = [obj for obj in bpy.context.scene.objects if obj.get("aludiy_entity_type") == "MEMBER_SOLID"]
        nodes = [obj for obj in bpy.context.scene.objects if obj.get("aludiy_entity_type") == "NODE"]
        assert len(axes) == 3, len(axes)
        assert len(solids) == 3, len(solids)
        assert len(nodes) == 4, len(nodes)
        assert bpy.context.scene.aludiy_settings.project_json
        print("ALUDIY_BLENDER_SMOKE_OK axes=3 solids=3 nodes=4 modes=BOX,PROFILE delete=1")
    finally:
        aludiy_designer.unregister()


if __name__ == "__main__":
    main()
