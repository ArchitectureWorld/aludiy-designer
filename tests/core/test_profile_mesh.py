from __future__ import annotations

from pathlib import Path

import pytest

from aludiy_core.catalog import ProfileCatalog
from aludiy_core.geometry import derive_member_mesh, section_outline_uv
from aludiy_core.errors import ValidationError
from aludiy_core.model import Member, Node, Project

CATALOG_SOURCE = Path(__file__).parents[2] / "catalog" / "profiles"


def make_project(profile_type_id: str) -> Project:
    project = Project(project_id="P-MESH", catalog_revision="alpha-2026.10")
    project.add_node(Node(id="N-A", position_mm=(0.0, 0.0, 0.0)))
    project.add_node(Node(id="N-B", position_mm=(1000.0, 0.0, 0.0)))
    project.add_member(
        Member(
            id="M-001",
            start_node_id="N-A",
            end_node_id="N-B",
            profile_type_id=profile_type_id,
        )
    )
    return project


def test_box_mesh_is_rectangular_envelope() -> None:
    catalog = ProfileCatalog.from_source_directory(CATALOG_SOURCE)
    project = make_project("generic:tslot-2040@0.1")

    mesh = derive_member_mesh(project, "M-001", catalog, mode="BOX")

    assert mesh.mode == "BOX"
    assert len(mesh.vertices_mm) == 8
    assert len(mesh.faces) == 6
    assert min(point[0] for point in mesh.vertices_mm) == pytest.approx(0.0)
    assert max(point[0] for point in mesh.vertices_mm) == pytest.approx(1000.0)


def test_profile_outline_uses_every_semantic_slot() -> None:
    catalog = ProfileCatalog.from_source_directory(CATALOG_SOURCE)
    profile = catalog.get("generic:tslot-2040@0.1")

    outline = section_outline_uv(profile.section, detailed=True)

    # A rectangle contributes 4 corners and every T-slot contributes 8
    # additional vertices. 20x40 has six semantic slots.
    assert len(outline) == 4 + 6 * 8
    assert min(point[0] for point in outline) == pytest.approx(-20.0)
    assert max(point[0] for point in outline) == pytest.approx(20.0)
    assert min(point[1] for point in outline) == pytest.approx(-10.0)
    assert max(point[1] for point in outline) == pytest.approx(10.0)
    assert any(-20.0 < point[0] < 20.0 and -10.0 < point[1] < 10.0 for point in outline)


def test_three_open_profile_leaves_closed_face_without_notch() -> None:
    catalog = ProfileCatalog.from_source_directory(CATALOG_SOURCE)
    profile = catalog.get("generic:tslot-3030-3open@0.1")

    outline = section_outline_uv(profile.section, detailed=True)

    assert len(outline) == 4 + 3 * 8
    bottom_points = [point for point in outline if abs(point[1] + 15.0) < 1.0e-9]
    assert set(bottom_points) == {(-15.0, -15.0), (15.0, -15.0)}


def test_profile_mesh_extrudes_detailed_outline_along_member_axis() -> None:
    catalog = ProfileCatalog.from_source_directory(CATALOG_SOURCE)
    project = make_project("generic:tslot-2020@0.1")

    mesh = derive_member_mesh(project, "M-001", catalog, mode="PROFILE")

    outline_count = 4 + 4 * 8
    assert mesh.mode == "PROFILE"
    assert len(mesh.vertices_mm) == outline_count * 2
    assert len(mesh.faces) == outline_count + 2
    assert min(point[0] for point in mesh.vertices_mm) == pytest.approx(0.0)
    assert max(point[0] for point in mesh.vertices_mm) == pytest.approx(1000.0)


def test_unknown_mesh_mode_is_rejected() -> None:
    catalog = ProfileCatalog.from_source_directory(CATALOG_SOURCE)
    project = make_project("generic:tslot-2020@0.1")

    with pytest.raises(ValidationError, match="unsupported member mesh mode"):
        derive_member_mesh(project, "M-001", catalog, mode="UNKNOWN")  # type: ignore[arg-type]


def _orientation(a, b, c) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _properly_intersects(a, b, c, d) -> bool:
    return (
        _orientation(a, b, c) * _orientation(a, b, d) < 0
        and _orientation(c, d, a) * _orientation(c, d, b) < 0
    )


def test_detailed_outlines_are_simple_ccw_polygons_for_all_catalog_profiles() -> None:
    catalog = ProfileCatalog.from_source_directory(CATALOG_SOURCE)

    for profile in catalog:
        outline = section_outline_uv(profile.section, detailed=True)
        signed_area = sum(
            outline[index][0] * outline[(index + 1) % len(outline)][1]
            - outline[(index + 1) % len(outline)][0] * outline[index][1]
            for index in range(len(outline))
        ) * 0.5
        assert signed_area > 0, profile.profile_type_id

        for first in range(len(outline)):
            first_next = (first + 1) % len(outline)
            for second in range(first + 1, len(outline)):
                second_next = (second + 1) % len(outline)
                if first in {second, second_next} or first_next in {second, second_next}:
                    continue
                if first == 0 and second_next == 0:
                    continue
                assert not _properly_intersects(
                    outline[first],
                    outline[first_next],
                    outline[second],
                    outline[second_next],
                ), (profile.profile_type_id, first, second)
