from __future__ import annotations

from pathlib import Path
import tomllib


EXTENSION = Path(__file__).parents[2] / "extension" / "aludiy_designer"


def test_manifest_targets_blender_5_2_and_declares_required_metadata() -> None:
    payload = tomllib.loads((EXTENSION / "blender_manifest.toml").read_text(encoding="utf-8"))

    assert payload["schema_version"] == "1.0.0"
    assert payload["id"] == "aludiy_designer"
    assert payload["version"] == "0.1.5"
    assert payload["type"] == "add-on"
    assert payload["blender_version_min"] == "5.2.0"
    assert payload["license"] == ["SPDX:GPL-3.0-or-later"]
    assert len(payload["tagline"]) <= 64
    assert not payload["tagline"].endswith(".")


def test_profile_sources_compile_to_catalog_with_five_profiles(tmp_path: Path) -> None:
    import sqlite3

    from aludiy_core.catalog import compile_catalog

    root = Path(__file__).parents[2]
    database = tmp_path / "profile_catalog.sqlite"
    compile_catalog(root / "catalog" / "profiles", database)
    with sqlite3.connect(database) as connection:
        count = connection.execute("SELECT COUNT(*) FROM profiles").fetchone()[0]

    assert count == 5
