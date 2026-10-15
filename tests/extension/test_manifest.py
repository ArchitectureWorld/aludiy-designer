from __future__ import annotations

from pathlib import Path
import tomllib


EXTENSION = Path(__file__).parents[2] / "extension" / "aludiy_designer"


def test_manifest_targets_blender_5_2_and_declares_required_metadata() -> None:
    payload = tomllib.loads((EXTENSION / "blender_manifest.toml").read_text(encoding="utf-8"))

    assert payload["schema_version"] == "1.0.0"
    assert payload["id"] == "aludiy_designer"
    assert payload["version"] == "0.1.7"
    assert payload["type"] == "add-on"
    assert payload["blender_version_min"] == "5.2.0"
    assert payload["license"] == ["SPDX:GPL-3.0-or-later"]
    assert len(payload["tagline"]) <= 64
    assert not payload["tagline"].endswith(".")


def test_extension_bundles_compiled_catalog_with_five_profiles() -> None:
    import sqlite3

    database = EXTENSION / "resources" / "profile_catalog.sqlite"
    with sqlite3.connect(database) as connection:
        count = connection.execute("SELECT COUNT(*) FROM profiles").fetchone()[0]

    assert count == 5
