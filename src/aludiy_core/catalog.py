"""Versioned profile catalog loading and SQLite compilation."""

from __future__ import annotations

from collections.abc import Iterator
import json
from pathlib import Path
import sqlite3
from typing import Any

from .errors import CatalogError, DuplicateIdError
from .model import ProfileType


class ProfileCatalog:
    def __init__(self, profiles: dict[str, ProfileType]) -> None:
        self._profiles = dict(profiles)

    def __len__(self) -> int:
        return len(self._profiles)

    def __iter__(self) -> Iterator[ProfileType]:
        for profile_id in sorted(self._profiles):
            yield self._profiles[profile_id]

    def profile_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._profiles))

    def get(self, profile_type_id: str) -> ProfileType:
        try:
            return self._profiles[profile_type_id]
        except KeyError as exc:
            raise CatalogError(f"unknown profile type {profile_type_id}") from exc

    @classmethod
    def from_source_directory(cls, source_dir: str | Path) -> "ProfileCatalog":
        directory = Path(source_dir)
        if not directory.is_dir():
            raise CatalogError(f"profile source directory does not exist: {directory}")
        profiles: dict[str, ProfileType] = {}
        for path in sorted(directory.glob("*.json")):
            try:
                payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
                profile = ProfileType.from_dict(payload)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise CatalogError(f"invalid profile source {path}: {exc}") from exc
            if profile.profile_type_id in profiles:
                raise DuplicateIdError(
                    f"duplicate profile type {profile.profile_type_id} in {path}"
                )
            profiles[profile.profile_type_id] = profile
        if not profiles:
            raise CatalogError(f"no profile JSON files found in {directory}")
        return cls(profiles)

    @classmethod
    def from_sqlite(cls, database_path: str | Path) -> "ProfileCatalog":
        path = Path(database_path)
        if not path.is_file():
            raise CatalogError(f"compiled catalog does not exist: {path}")
        try:
            with sqlite3.connect(path) as connection:
                rows = connection.execute(
                    "SELECT profile_type_id, payload_json FROM profiles ORDER BY profile_type_id"
                ).fetchall()
        except sqlite3.Error as exc:
            raise CatalogError(f"cannot read compiled catalog {path}: {exc}") from exc
        profiles: dict[str, ProfileType] = {}
        for profile_id, payload_json in rows:
            profile = ProfileType.from_dict(json.loads(payload_json))
            if profile.profile_type_id != profile_id:
                raise CatalogError(
                    f"compiled profile key {profile_id} does not match payload {profile.profile_type_id}"
                )
            profiles[profile_id] = profile
        if not profiles:
            raise CatalogError(f"compiled catalog contains no profiles: {path}")
        return cls(profiles)


def compile_catalog(source_dir: str | Path, sqlite_path: str | Path) -> Path:
    """Validate source packages and atomically compile them into SQLite."""

    catalog = ProfileCatalog.from_source_directory(source_dir)
    destination = Path(sqlite_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    try:
        with sqlite3.connect(temporary) as connection:
            connection.executescript(
                """
                PRAGMA user_version = 1;
                CREATE TABLE metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE profiles (
                    profile_type_id TEXT PRIMARY KEY,
                    catalog_revision TEXT NOT NULL,
                    supplier_id TEXT NOT NULL,
                    supplier_sku TEXT NOT NULL,
                    width_mm REAL NOT NULL,
                    height_mm REAL NOT NULL,
                    payload_json TEXT NOT NULL
                );
                """
            )
            connection.execute(
                "INSERT INTO metadata(key, value) VALUES (?, ?)",
                ("schema_version", "0.1.0"),
            )
            for profile in catalog:
                connection.execute(
                    """
                    INSERT INTO profiles(
                        profile_type_id, catalog_revision, supplier_id,
                        supplier_sku, width_mm, height_mm, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        profile.profile_type_id,
                        profile.catalog_revision,
                        profile.supplier_id,
                        profile.supplier_sku,
                        profile.section.width_mm,
                        profile.section.height_mm,
                        json.dumps(
                            profile.to_dict(),
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    ),
                )
            connection.commit()
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination
