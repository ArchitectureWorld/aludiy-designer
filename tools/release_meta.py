#!/usr/bin/env python3
"""Read Blender extension release metadata and validate release tags."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import tomllib


@dataclass(frozen=True, slots=True)
class ReleaseMetadata:
    extension_id: str
    version: str
    blender_version_min: str


def read_manifest_metadata(manifest_path: Path) -> ReleaseMetadata:
    with manifest_path.open("rb") as handle:
        manifest = tomllib.load(handle)
    try:
        return ReleaseMetadata(
            extension_id=str(manifest["id"]),
            version=str(manifest["version"]),
            blender_version_min=str(manifest["blender_version_min"]),
        )
    except KeyError as exc:
        raise ValueError(f"Missing required manifest key: {exc.args[0]}") from exc


def extension_package_name(manifest_path: Path) -> str:
    metadata = read_manifest_metadata(manifest_path)
    return f"{metadata.extension_id}-{metadata.version}.zip"


def validate_release_tag(tag: str, version: str) -> None:
    pattern = rf"^v{re.escape(version)}(?:-(?:alpha|beta|rc\d+))?$"
    if re.fullmatch(pattern, tag) is None:
        raise ValueError(
            f"Release tag {tag!r} does not match manifest version {version!r}; "
            f"expected v{version}, v{version}-alpha, v{version}-beta, or v{version}-rcN"
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("extension/aludiy_designer/blender_manifest.toml"),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("version")
    subparsers.add_parser("package-name")
    validate = subparsers.add_parser("validate-tag")
    validate.add_argument("tag")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    metadata = read_manifest_metadata(args.manifest)
    if args.command == "version":
        print(metadata.version)
    elif args.command == "package-name":
        print(extension_package_name(args.manifest))
    elif args.command == "validate-tag":
        validate_release_tag(args.tag, metadata.version)
        print(f"{args.tag} matches manifest version {metadata.version}")


if __name__ == "__main__":
    main()
