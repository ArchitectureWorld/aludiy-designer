"""Design lengths and explicitly evaluated square-cut reference lengths.

Legacy callers without a catalog and without processing rules retain the old
CSV shape. Processing requires the catalog and refuses pending/invalid rules.
"""
from __future__ import annotations
import csv
from dataclasses import dataclass
from pathlib import Path
from .geometry import member_length_mm
from .model import Project
from .errors import ValidationError

@dataclass(frozen=True, slots=True)
class CutListRow:
    member_id: str
    profile_type_id: str
    start_node_id: str
    end_node_id: str
    system_length_mm: float
    cut_length_mm: float | None = None
    start_setback_mm: float = 0.0
    end_setback_mm: float = 0.0


def cutlist_rows(project: Project, catalog=None) -> tuple[CutListRow, ...]:
    project.validate()
    if project.joints and catalog is None:
        raise ValidationError('计算交接参考长度需要型材目录，不能只导出设计线长度冒充切割长度')
    solution = None
    if catalog is not None:
        from .associations import validate_slot_catalog
        from .joints import solve_cutbacks
        validate_slot_catalog(project, catalog)
        # Even unprocessed rows must refer to real catalog profiles.
        for member in project.members.values():
            catalog.get(member.profile_type_id)
        solution = solve_cutbacks(project, catalog, strict=True)
    rows = []
    for mid, member in sorted(project.members.items()):
        length = member_length_mm(project, mid)
        body = solution.lengths[mid] if solution else None
        rows.append(CutListRow(mid, member.profile_type_id, member.start_node_id,
            member.end_node_id, length, body.cut_length_mm if body else None,
            body.start_setback_mm if body else 0, body.end_setback_mm if body else 0))
    return tuple(rows)


def write_cutlist_csv(project: Project, path: str | Path, catalog=None) -> Path:
    # Preflight ALL rows before touching the destination or its temp file.
    rows = cutlist_rows(project, catalog)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix+'.tmp')
    fields = ['member_id', 'profile_type_id', 'start_node_id', 'end_node_id', 'system_length_mm']
    if catalog is not None:
        fields += ['start_setback_mm', 'end_setback_mm', 'cut_length_mm', 'status']
    with temporary.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            item = {k: getattr(row, k) for k in fields if k != 'status'}
            for k in fields:
                if k.endswith('_mm'):
                    item[k] = f'{item[k]:.3f}'
            if catalog is not None:
                item['status'] = 'reference_only;not_manufacturing_validated'
            writer.writerow(item)
    temporary.replace(destination)
    return destination
