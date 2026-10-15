from __future__ import annotations

import json
from pathlib import Path

import pytest

from aludiy_core.errors import MissingReferenceError
from aludiy_core.io import create_sample_frame, load_project, save_project


def test_sample_frame_has_four_members_with_expected_lengths() -> None:
    project = create_sample_frame(
        width_mm=1200.0,
        depth_mm=600.0,
        profile_type_id="generic:tslot-2020@0.1",
    )

    assert tuple(project.nodes) == ("N-001", "N-002", "N-003", "N-004")
    assert tuple(project.members) == ("M-001", "M-002", "M-003", "M-004")
    points = {node_id: node.position_mm for node_id, node in project.nodes.items()}
    assert points == {
        "N-001": (0.0, 0.0, 0.0),
        "N-002": (1200.0, 0.0, 0.0),
        "N-003": (1200.0, 600.0, 0.0),
        "N-004": (0.0, 600.0, 0.0),
    }


def test_save_project_is_deterministic_and_ends_with_newline(tmp_path: Path) -> None:
    project = create_sample_frame(1200.0, 600.0, "generic:tslot-2020@0.1")
    first = tmp_path / "first.aludiy.json"
    second = tmp_path / "second.aludiy.json"

    save_project(project, first)
    save_project(project, second)

    assert first.read_bytes() == second.read_bytes()
    assert first.read_bytes().endswith(b"\n")
    assert json.loads(first.read_text(encoding="utf-8"))["members"][0]["id"] == "M-001"


def test_load_project_revalidates_missing_references(tmp_path: Path) -> None:
    path = tmp_path / "broken.aludiy.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "0.1.0",
                "project_id": "P-001",
                "catalog_revision": "alpha-2026.10",
                "nodes": [{"id": "N-001", "position_mm": [0, 0, 0]}],
                "members": [
                    {
                        "id": "M-001",
                        "start_node_id": "N-001",
                        "end_node_id": "N-404",
                        "profile_type_id": "generic:tslot-2020@0.1",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(MissingReferenceError, match="N-404"):
        load_project(path)


def test_catalog_revision_warning_only_reports_mismatch() -> None:
    from aludiy_core.io import catalog_revision_warning

    project = create_sample_frame(1200.0, 600.0, "generic:tslot-2020@0.1")

    assert catalog_revision_warning(project, "alpha-2026.10") is None
    assert catalog_revision_warning(project, "alpha-2026.11") == (
        "项目型材目录版本 alpha-2026.10 与当前目录 alpha-2026.11 不一致；"
        "已保留项目引用，请复核后再替换型材。"
    )
