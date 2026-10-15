from __future__ import annotations

from pathlib import Path

import pytest

from aludiy_core.catalog import ProfileCatalog
from aludiy_core.errors import ValidationError
from aludiy_core.geometry import (
    derive_member_envelope,
    member_length_mm,
    resize_member,
)
from aludiy_core.model import Member, Node, Project


CATALOG_SOURCE = Path(__file__).parents[2] / "catalog" / "profiles"


def make_project(*, roll_deg: float = 0.0, profile: str = "generic:tslot-2020@0.1") -> Project:
    project = Project(project_id="P-001", catalog_revision="alpha-2026.10")
    project.add_node(Node(id="N-A", position_mm=(0.0, 0.0, 0.0)))
    project.add_node(Node(id="N-B", position_mm=(1200.0, 0.0, 0.0)))
    project.add_member(
        Member(
            id="M-001",
            start_node_id="N-A",
            end_node_id="N-B",
            profile_type_id=profile,
            roll_deg=roll_deg,
        )
    )
    return project


def test_resize_member_with_start_anchor_keeps_start_and_moves_end() -> None:
    project = make_project()

    resize_member(project, "M-001", 1500.0, anchor="START")

    assert project.nodes["N-A"].position_mm == pytest.approx((0.0, 0.0, 0.0))
    assert project.nodes["N-B"].position_mm == pytest.approx((1500.0, 0.0, 0.0))
    assert project.members["M-001"].revision == 2


def test_resize_member_with_end_anchor_keeps_end_and_moves_start() -> None:
    project = make_project()

    resize_member(project, "M-001", 1500.0, anchor="END")

    assert project.nodes["N-A"].position_mm == pytest.approx((-300.0, 0.0, 0.0))
    assert project.nodes["N-B"].position_mm == pytest.approx((1200.0, 0.0, 0.0))


def test_resize_member_with_center_anchor_keeps_center() -> None:
    project = make_project()

    resize_member(project, "M-001", 1500.0, anchor="CENTER")

    assert project.nodes["N-A"].position_mm == pytest.approx((-150.0, 0.0, 0.0))
    assert project.nodes["N-B"].position_mm == pytest.approx((1350.0, 0.0, 0.0))
    assert member_length_mm(project, "M-001") == pytest.approx(1500.0)


def test_zero_length_member_is_rejected_before_persistence() -> None:
    project = Project(project_id="P-001", catalog_revision="alpha-2026.10")
    project.add_node(Node(id="N-A", position_mm=(0.0, 0.0, 0.0)))
    project.add_node(Node(id="N-B", position_mm=(0.0, 0.0, 0.0)))

    with pytest.raises(ValidationError, match="zero-length"):
        project.add_member(
            Member(
                id="M-001",
                start_node_id="N-A",
                end_node_id="N-B",
                profile_type_id="generic:tslot-2020@0.1",
            )
        )


def test_2040_roll_90_rotates_cross_section_world_extents() -> None:
    catalog = ProfileCatalog.from_source_directory(CATALOG_SOURCE)
    project = make_project(roll_deg=90.0, profile="generic:tslot-2040@0.1")

    envelope = derive_member_envelope(project, "M-001", catalog)

    assert envelope.length_mm == pytest.approx(1200.0)
    assert envelope.section_width_mm == pytest.approx(40.0)
    assert envelope.section_height_mm == pytest.approx(20.0)
    assert envelope.world_half_extents_mm == pytest.approx((600.0, 10.0, 20.0))
