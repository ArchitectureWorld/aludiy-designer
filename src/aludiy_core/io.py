"""Deterministic project persistence and alpha sample-project factories."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import ValidationError
from .model import Member, Node, Project


def save_project(project: Project, path: str | Path) -> Path:
    """Atomically write an AluDIY project as canonical, human-readable JSON."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    payload = json.dumps(
        project.to_dict(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    temporary.write_text(payload, encoding="utf-8", newline="\n")
    temporary.replace(destination)
    return destination


def load_project(path: str | Path) -> Project:
    source = Path(path)
    try:
        payload: dict[str, Any] = json.loads(source.read_text(encoding="utf-8"))
    except OSError:
        raise
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValidationError(f"invalid project JSON {source}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValidationError("project JSON root must be an object")
    return Project.from_dict(payload)


def catalog_revision_warning(project: Project, active_revision: str) -> str | None:
    """Return an actionable warning when a project uses another catalog revision."""

    current = str(active_revision).strip()
    if project.catalog_revision == current:
        return None
    return (
        f"项目型材目录版本 {project.catalog_revision} 与当前目录 {current} 不一致；"
        "已保留项目引用，请复核后再替换型材。"
    )


def create_sample_frame(
    width_mm: float,
    depth_mm: float,
    profile_type_id: str,
    *,
    project_id: str = "P-SAMPLE-001",
    catalog_revision: str = "alpha-2026.10",
) -> Project:
    """Create a deterministic four-member rectangular XY frame."""

    width = float(width_mm)
    depth = float(depth_mm)
    if width <= 0.0 or depth <= 0.0:
        raise ValidationError("sample frame width and depth must be positive")
    project = Project(project_id=project_id, catalog_revision=catalog_revision)
    node_positions = (
        ("N-001", (0.0, 0.0, 0.0)),
        ("N-002", (width, 0.0, 0.0)),
        ("N-003", (width, depth, 0.0)),
        ("N-004", (0.0, depth, 0.0)),
    )
    for node_id, position in node_positions:
        project.add_node(Node(id=node_id, position_mm=position))
    member_nodes = (
        ("M-001", "N-001", "N-002"),
        ("M-002", "N-002", "N-003"),
        ("M-003", "N-003", "N-004"),
        ("M-004", "N-004", "N-001"),
    )
    for member_id, start_node_id, end_node_id in member_nodes:
        project.add_member(
            Member(
                id=member_id,
                start_node_id=start_node_id,
                end_node_id=end_node_id,
                profile_type_id=profile_type_id,
            )
        )
    return project
