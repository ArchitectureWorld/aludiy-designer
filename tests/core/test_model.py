from __future__ import annotations

import pytest

from aludiy_core.errors import DuplicateIdError, MissingReferenceError
from aludiy_core.model import Member, Node, Project


def test_project_round_trip_preserves_nodes_members_and_profile_revision() -> None:
    project = Project(project_id="P-001", catalog_revision="test-2026.10")
    project.add_node(Node(id="N-001", position_mm=(0.0, 0.0, 0.0)))
    project.add_node(Node(id="N-002", position_mm=(1200.0, 0.0, 0.0)))
    project.add_member(
        Member(
            id="M-001",
            start_node_id="N-001",
            end_node_id="N-002",
            profile_type_id="generic:tslot-2020@0.1",
            anchor_ref="PROFILE_ORIGIN",
            roll_deg=0.0,
        )
    )

    restored = Project.from_dict(project.to_dict())

    assert restored == project
    assert restored.members["M-001"].profile_type_id == "generic:tslot-2020@0.1"


def test_member_referencing_missing_node_is_rejected() -> None:
    project = Project(project_id="P-001", catalog_revision="test-2026.10")
    project.add_node(Node(id="N-001", position_mm=(0.0, 0.0, 0.0)))

    with pytest.raises(MissingReferenceError, match="N-404"):
        project.add_member(
            Member(
                id="M-001",
                start_node_id="N-001",
                end_node_id="N-404",
                profile_type_id="generic:tslot-2020@0.1",
            )
        )


def test_duplicate_node_ids_in_serialized_project_are_rejected() -> None:
    payload = {
        "schema_version": "0.1.0",
        "project_id": "P-001",
        "catalog_revision": "test-2026.10",
        "nodes": [
            {"id": "N-001", "position_mm": [0, 0, 0]},
            {"id": "N-001", "position_mm": [10, 0, 0]},
        ],
        "members": [],
    }

    with pytest.raises(DuplicateIdError, match="N-001"):
        Project.from_dict(payload)


def _two_member_chain() -> Project:
    project = Project(project_id="P-DELETE", catalog_revision="test-2026.10")
    project.add_node(Node(id="N-001", position_mm=(0.0, 0.0, 0.0)))
    project.add_node(Node(id="N-002", position_mm=(1000.0, 0.0, 0.0)))
    project.add_node(Node(id="N-003", position_mm=(2000.0, 0.0, 0.0)))
    project.add_member(
        Member(
            id="M-001",
            start_node_id="N-001",
            end_node_id="N-002",
            profile_type_id="generic:tslot-2020@0.1",
        )
    )
    project.add_member(
        Member(
            id="M-002",
            start_node_id="N-002",
            end_node_id="N-003",
            profile_type_id="generic:tslot-2020@0.1",
        )
    )
    return project


def test_remove_member_prunes_only_newly_orphaned_endpoint_nodes() -> None:
    project = _two_member_chain()

    result = project.remove_members(["M-001"])

    assert result.removed_member_ids == ("M-001",)
    assert result.removed_node_ids == ("N-001",)
    assert set(project.members) == {"M-002"}
    assert set(project.nodes) == {"N-002", "N-003"}
    project.validate()


def test_remove_members_deduplicates_ids_and_prunes_chain_nodes() -> None:
    project = _two_member_chain()

    result = project.remove_members(["M-002", "M-001", "M-002"])

    assert result.removed_member_ids == ("M-001", "M-002")
    assert result.removed_node_ids == ("N-001", "N-002", "N-003")
    assert project.members == {}
    assert project.nodes == {}
