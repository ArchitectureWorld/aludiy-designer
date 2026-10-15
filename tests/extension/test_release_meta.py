from __future__ import annotations

from pathlib import Path

import pytest

from tools.release_meta import (
    extension_package_name,
    read_manifest_metadata,
    validate_release_tag,
)


def _write_manifest(path: Path, *, extension_id: str = "aludiy_designer", version: str = "0.2.0") -> None:
    path.write_text(
        "\n".join(
            [
                'schema_version = "1.0.0"',
                f'id = "{extension_id}"',
                f'version = "{version}"',
                'name = "AluDIY Designer"',
                'tagline = "Line-driven design"',
                'maintainer = "ArchitectureWorld"',
                'type = "add-on"',
                'license = ["SPDX:GPL-3.0-or-later"]',
                'blender_version_min = "5.2.0"',
            ]
        ),
        encoding="utf-8",
    )


def test_manifest_metadata_drives_extension_package_name(tmp_path: Path) -> None:
    manifest = tmp_path / "blender_manifest.toml"
    _write_manifest(manifest, extension_id="test_extension", version="2.3.4")

    metadata = read_manifest_metadata(manifest)

    assert metadata.extension_id == "test_extension"
    assert metadata.version == "2.3.4"
    assert metadata.blender_version_min == "5.2.0"
    assert extension_package_name(manifest) == "test_extension-2.3.4.zip"


@pytest.mark.parametrize("tag", ["v0.1.5", "v0.1.5-alpha", "v0.1.5-beta", "v0.1.5-rc1"])
def test_release_tag_accepts_manifest_version(tag: str) -> None:
    validate_release_tag(tag, "0.1.5")


@pytest.mark.parametrize("tag", ["0.1.5-alpha", "v0.1.6-alpha", "v0.1.5-preview", "v0.1.5-rc"])
def test_release_tag_rejects_mismatched_or_unsupported_tags(tag: str) -> None:
    with pytest.raises(ValueError, match="0.1.5"):
        validate_release_tag(tag, "0.1.5")
