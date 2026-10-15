from __future__ import annotations

import csv
from pathlib import Path

from aludiy_core.cutlist import cutlist_rows, write_cutlist_csv
from aludiy_core.io import create_sample_frame


def test_cutlist_rows_are_sorted_and_use_system_lengths() -> None:
    project = create_sample_frame(1200.0, 600.0, "generic:tslot-2020@0.1")

    rows = cutlist_rows(project)

    assert [row.member_id for row in rows] == ["M-001", "M-002", "M-003", "M-004"]
    assert [row.system_length_mm for row in rows] == [1200.0, 600.0, 1200.0, 600.0]


def test_write_cutlist_csv_has_stable_header_and_values(tmp_path: Path) -> None:
    project = create_sample_frame(1200.0, 600.0, "generic:tslot-2020@0.1")
    path = tmp_path / "cutlist.csv"

    write_cutlist_csv(project, path)

    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0]) == [
        "member_id",
        "profile_type_id",
        "start_node_id",
        "end_node_id",
        "system_length_mm",
    ]
    assert rows[0]["system_length_mm"] == "1200.000"
    assert rows[1]["system_length_mm"] == "600.000"
