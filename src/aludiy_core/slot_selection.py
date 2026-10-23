"""Ephemeral, revision-bound rail selection. Never changes engineering relations."""
from dataclasses import dataclass, asdict
import json

from .errors import ValidationError


def normalize_pairs(pairs):
    """Deterministic deduplication without collapsing different host/slot IDs."""
    result = set()
    for pair in pairs:
        if (not isinstance(pair, (list, tuple)) or len(pair) != 2
                or any(not isinstance(v, str) or not v.strip() for v in pair)):
            raise ValidationError('槽轨选择必须包含有效的主杆和槽位 ID')
        result.add(tuple(pair))
    return tuple(sorted(result))


@dataclass(frozen=True, order=True, slots=True)
class SlotTarget:
    member_id: str
    interface_id: str
    profile_type_id: str
    catalog_revision: str

    def __post_init__(self):
        if any(not isinstance(v, str) or not v.strip() for v in asdict(self).values()):
            raise ValidationError('槽轨选择引用不完整：主杆/槽位/规格/目录版本均不可为空')

    @property
    def key(self):
        return self.member_id, self.interface_id


def _unique(records):
    by_key = {}
    for record in records:
        if not isinstance(record, SlotTarget):
            raise ValidationError('槽轨选择引用类型无效')
        if record.key in by_key and by_key[record.key] != record:
            raise ValidationError('同一槽轨包含不一致的规格或目录版本引用')
        by_key[record.key] = record
    return tuple(by_key[k] for k in sorted(by_key))


def make_target(project, catalog, member_id, interface_id):
    from .associations import slot_reference
    ref = slot_reference(project, member_id, interface_id, catalog)
    return SlotTarget(member_id, interface_id, ref.profile_type_id, ref.catalog_revision)


def decode_targets(value):
    if not value or not value.strip():
        return ()
    try:
        data = json.loads(value)
        if not isinstance(data, list):
            raise ValueError('expected list')
        return _unique(SlotTarget(**item) for item in data)
    except (TypeError, ValueError, KeyError) as exc:
        raise ValidationError('槽轨选择数据无法读取；请清空槽轨选择后重新指定') from exc


def encode_targets(records):
    return json.dumps([asdict(r) for r in _unique(records)], ensure_ascii=False, sort_keys=True)


def select_target(records, target, *, extend=False):
    """Plain click replaces. Shift toggles exactly one Member/Interface identity."""
    old = _unique(records)
    if not extend:
        return (target,)
    if any(r.key == target.key for r in old):
        return tuple(r for r in old if r.key != target.key)
    return _unique(old + (target,))


def validated_pairs(project, catalog, records):
    records = _unique(records)
    for record in records:
        current = make_target(project, catalog, *record.key)
        if current != record:
            raise ValidationError(f'{record.member_id} / {record.interface_id} 已换型或目录改变；请移除并重选，不按同名槽匹配')
    return tuple(r.key for r in records)


def without_missing_hosts(project, records):
    """Only missing hosts are disposable UI state. Never mask catalog mismatch."""
    return tuple(r for r in _unique(records) if r.member_id in project.members)
