"""Alpha cut-list output based on member system lengths."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .geometry import member_length_mm
from .model import Project


@dataclass(frozen=True, slots=True)
class CutListRow:
    member_id: str
    profile_type_id: str
    start_node_id: str
    end_node_id: str
    system_length_mm: float


def cutlist_rows(project: Project) -> tuple[CutListRow, ...]:
    project.validate()
    return tuple(
        CutListRow(
            member_id=member.id,
            profile_type_id=member.profile_type_id,
            start_node_id=member.start_node_id,
            end_node_id=member.end_node_id,
            system_length_mm=member_length_mm(project, member.id),
        )
        for member in (project.members[key] for key in sorted(project.members))
    )


def write_cutlist_csv(project: Project, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    fieldnames = (
        "member_id",
        "profile_type_id",
        "start_node_id",
        "end_node_id",
        "system_length_mm",
    )
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in cutlist_rows(project):
            writer.writerow(
                {
                    "member_id": row.member_id,
                    "profile_type_id": row.profile_type_id,
                    "start_node_id": row.start_node_id,
                    "end_node_id": row.end_node_id,
                    "system_length_mm": f"{row.system_length_mm:.3f}",
                }
            )
    temporary.replace(destination)
    return destination
