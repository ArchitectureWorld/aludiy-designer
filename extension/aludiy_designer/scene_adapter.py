"""Generate Blender cache objects from the authoritative AluDIY project."""

from __future__ import annotations

import json
from typing import Iterable

import bpy

from .runtime import AXIS_COLLECTION, HELPER_COLLECTION, SOLID_COLLECTION, settings
from .vendor.aludiy_core import ProfileCatalog, Project, derive_member_mesh

MM_TO_M = 0.001


def _mm_to_m(point: Iterable[float]) -> tuple[float, float, float]:
    values = tuple(float(value) * MM_TO_M for value in point)
    return values[0], values[1], values[2]


def ensure_collection(scene: bpy.types.Scene, name: str) -> bpy.types.Collection:
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
    if collection.name not in scene.collection.children:
        scene.collection.children.link(collection)
    return collection


def remove_object_and_orphan_data(obj: bpy.types.Object) -> None:
    """Remove a generated object and its now-unused mesh datablock."""

    data = getattr(obj, "data", None)
    bpy.data.objects.remove(obj, do_unlink=True)
    if data is not None and isinstance(data, bpy.types.Mesh) and data.users == 0:
        bpy.data.meshes.remove(data)


def _remove_managed_objects(scene: bpy.types.Scene) -> None:
    for obj in list(scene.objects):
        if obj.get("aludiy_managed"):
            remove_object_and_orphan_data(obj)


def _tag_object(obj: bpy.types.Object, *, entity_type: str, entity_id: str) -> None:
    obj["aludiy_managed"] = True
    obj["aludiy_entity_type"] = entity_type
    obj["aludiy_entity_id"] = entity_id


def _create_axis_object(
    collection: bpy.types.Collection,
    member_id: str,
    start_mm: tuple[float, float, float],
    end_mm: tuple[float, float, float],
    profile_type_id: str,
    interface_ids: tuple[str, ...],
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(f"AXIS_{member_id}_Mesh")
    mesh.from_pydata([_mm_to_m(start_mm), _mm_to_m(end_mm)], [(0, 1)], [])
    mesh.update()
    obj = bpy.data.objects.new(f"轴线_{member_id}", mesh)
    collection.objects.link(obj)
    _tag_object(obj, entity_type="MEMBER_AXIS", entity_id=member_id)
    obj["aludiy_profile_type_id"] = profile_type_id
    obj["aludiy_interface_ids"] = json.dumps(interface_ids)
    obj.display_type = "WIRE"
    obj.show_in_front = True
    obj.hide_render = True
    return obj


def _ensure_material() -> bpy.types.Material:
    material = bpy.data.materials.get("AluDIY Aluminum")
    if material is None:
        material = bpy.data.materials.new("AluDIY Aluminum")
        material.diffuse_color = (0.42, 0.46, 0.50, 1.0)
        material.metallic = 0.8
        material.roughness = 0.26
    return material


def _create_solid_object(
    collection: bpy.types.Collection,
    member_mesh,
    profile_type_id: str,
    interface_ids: tuple[str, ...],
    revision: int,
) -> bpy.types.Object:
    vertices = [_mm_to_m(point) for point in member_mesh.vertices_mm]
    faces = [tuple(face) for face in member_mesh.faces]
    mesh = bpy.data.meshes.new(f"SOLID_{member_mesh.member_id}_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(f"型材_{member_mesh.member_id}", mesh)
    collection.objects.link(obj)
    _tag_object(obj, entity_type="MEMBER_SOLID", entity_id=member_mesh.member_id)
    obj["aludiy_source_id"] = member_mesh.member_id
    obj["aludiy_source_revision"] = revision
    obj["aludiy_profile_type_id"] = profile_type_id
    obj["aludiy_interface_ids"] = json.dumps(interface_ids)
    obj["aludiy_display_mode"] = member_mesh.mode
    obj.data.materials.append(_ensure_material())
    return obj


def _create_node_object(
    collection: bpy.types.Collection,
    node_id: str,
    position_mm: tuple[float, float, float],
) -> bpy.types.Object:
    obj = bpy.data.objects.new(f"节点_{node_id}", None)
    collection.objects.link(obj)
    _tag_object(obj, entity_type="NODE", entity_id=node_id)
    obj.location = _mm_to_m(position_mm)
    obj.empty_display_type = "SPHERE"
    obj.empty_display_size = 0.012
    obj.show_in_front = True
    obj.hide_render = True
    return obj


def rebuild_scene(
    scene: bpy.types.Scene,
    project: Project,
    catalog: ProfileCatalog,
) -> None:
    """Replace all managed cache objects from authoritative project data."""

    _remove_managed_objects(scene)
    axis_collection = ensure_collection(scene, AXIS_COLLECTION)
    solid_collection = ensure_collection(scene, SOLID_COLLECTION)
    ensure_collection(scene, HELPER_COLLECTION)
    for node_id in sorted(project.nodes):
        node = project.nodes[node_id]
        _create_node_object(axis_collection, node.id, node.position_mm)
    for member_id in sorted(project.members):
        member = project.members[member_id]
        profile = catalog.get(member.profile_type_id)
        interface_ids = tuple(sorted(profile.section.interfaces))
        start = project.nodes[member.start_node_id].position_mm
        end = project.nodes[member.end_node_id].position_mm
        _create_axis_object(
            axis_collection,
            member.id,
            start,
            end,
            member.profile_type_id,
            interface_ids,
        )
        member_mesh = derive_member_mesh(
            project,
            member.id,
            catalog,
            mode=settings(scene).solid_display_mode,
        )
        _create_solid_object(
            solid_collection,
            member_mesh,
            member.profile_type_id,
            interface_ids,
            member.revision,
        )
    # Local collection visibility is stored per viewport. Reapply the roles
    # after rebuilding so newly created cache objects appear in the right view.
    from . import view_sync

    view_sync.refresh_view_collections(scene)


def select_entity(
    scene: bpy.types.Scene,
    view_layer: bpy.types.ViewLayer,
    entity_id: str,
) -> None:
    # Newly rebuilt collections must be evaluated before selecting their objects.
    view_layer.update()
    active = None
    for obj in scene.objects:
        if obj.name not in view_layer.objects:
            continue
        object_entity = obj.get("aludiy_entity_id") or obj.get("aludiy_source_id")
        if object_entity == entity_id:
            obj.select_set(True)
            if active is None:
                active = obj
        elif obj.get("aludiy_managed"):
            obj.select_set(False)
    if active is not None:
        view_layer.objects.active = active
