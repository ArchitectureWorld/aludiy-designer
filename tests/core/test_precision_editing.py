from __future__ import annotations

import copy

import pytest

from aludiy_core.errors import ValidationError
from aludiy_core.geometry import move_node, resize_member, translate_member
from aludiy_core.model import Member, Node, Project


def connected_project() -> Project:
    project = Project(project_id="P-EDIT", catalog_revision="alpha-2026.10")
    for node_id, position in (
        ("N-A", (0.0, 0.0, 0.0)),
        ("N-B", (1000.0, 0.0, 0.0)),
        ("N-C", (1000.0, 600.0, 0.0)),
        ("N-D", (1000.0, 0.0, 800.0)),
    ):
        project.add_node(Node(id=node_id, position_mm=position))
    project.add_member(Member("M-AB", "N-A", "N-B", "generic:tslot-2020@0.1"))
    project.add_member(Member("M-BC", "N-B", "N-C", "generic:tslot-2020@0.1"))
    project.add_member(Member("M-BD", "N-B", "N-D", "generic:tslot-2020@0.1"))
    return project


def test_move_node_updates_position_and_all_incident_member_revisions_once() -> None:
    project = connected_project()

    result = move_node(project, "N-B", (1200.0, 50.0, 25.0))

    assert project.nodes["N-B"].position_mm == pytest.approx((1200.0, 50.0, 25.0))
    assert result.moved_node_ids == ("N-B",)
    assert result.affected_member_ids == ("M-AB", "M-BC", "M-BD")
    assert {member_id: project.members[member_id].revision for member_id in project.members} == {
        "M-AB": 2,
        "M-BC": 2,
        "M-BD": 2,
    }


def test_move_node_rejects_zero_length_without_partial_mutation() -> None:
    project = connected_project()
    before = copy.deepcopy(project.to_dict())

    with pytest.raises(ValidationError, match="zero-length"):
        move_node(project, "N-B", (0.0, 0.0, 0.0))

    assert project.to_dict() == before


def test_translate_member_moves_both_nodes_and_propagates_to_connected_members() -> None:
    project = connected_project()

    result = translate_member(project, "M-AB", (-100.0, 25.0, 300.0))

    assert project.nodes["N-A"].position_mm == pytest.approx((-100.0, 25.0, 300.0))
    assert project.nodes["N-B"].position_mm == pytest.approx((900.0, 25.0, 300.0))
    assert project.nodes["N-C"].position_mm == pytest.approx((1000.0, 600.0, 0.0))
    assert result.moved_node_ids == ("N-A", "N-B")
    assert result.affected_member_ids == ("M-AB", "M-BC", "M-BD")
    assert project.members["M-AB"].revision == 2
    assert project.members["M-BC"].revision == 2
    assert project.members["M-BD"].revision == 2


def test_resize_member_increments_revisions_for_members_connected_to_moved_endpoint() -> None:
    project = connected_project()

    result = resize_member(project, "M-AB", 1500.0, anchor="START")

    assert project.nodes["N-A"].position_mm == pytest.approx((0.0, 0.0, 0.0))
    assert project.nodes["N-B"].position_mm == pytest.approx((1500.0, 0.0, 0.0))
    assert result.moved_node_ids == ("N-B",)
    assert result.affected_member_ids == ("M-AB", "M-BC", "M-BD")
    assert project.members["M-AB"].revision == 2
    assert project.members["M-BC"].revision == 2
    assert project.members["M-BD"].revision == 2


def test_resize_member_center_moves_both_nodes_but_revisions_increment_once() -> None:
    project = connected_project()

    result = resize_member(project, "M-AB", 1400.0, anchor="CENTER")

    assert result.moved_node_ids == ("N-A", "N-B")
    assert result.affected_member_ids == ("M-AB", "M-BC", "M-BD")
    assert project.members["M-AB"].revision == 2
    assert project.members["M-BC"].revision == 2
    assert project.members["M-BD"].revision == 2


def test_noop_move_does_not_bump_revision() -> None:
    project = connected_project()

    result = move_node(project, "N-B", (1000.0, 0.0, 0.0))

    assert result.moved_node_ids == ()
    assert result.affected_member_ids == ()
    assert all(member.revision == 1 for member in project.members.values())
