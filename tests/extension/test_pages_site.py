from __future__ import annotations

import hashlib
from pathlib import Path

from tools.build_pages_site import latest_progress_page, prepare_pages_site


def test_latest_progress_page_uses_numeric_version_order(tmp_path: Path) -> None:
    progress = tmp_path / "progress"
    progress.mkdir()
    (progress / "v0.1.9-alpha.html").write_text("old", encoding="utf-8")
    (progress / "v0.1.10-alpha.html").write_text("new", encoding="utf-8")
    (progress / "index.html").write_text("alias", encoding="utf-8")

    assert latest_progress_page(progress).name == "v0.1.10-alpha.html"


def test_prepare_pages_site_copies_package_dashboard_and_checksum(tmp_path: Path) -> None:
    package = tmp_path / "aludiy_designer-0.1.5.zip"
    package.write_bytes(b"extension-package")
    dashboard = tmp_path / "v0.1.5-alpha.html"
    dashboard.write_text("<html>progress</html>", encoding="utf-8")
    output = tmp_path / "site"

    artifacts = prepare_pages_site(package, dashboard, output)

    copied_package = output / package.name
    assert copied_package.read_bytes() == b"extension-package"
    assert (output / "progress" / "index.html").read_text(encoding="utf-8") == "<html>progress</html>"
    assert (output / ".nojekyll").read_text(encoding="utf-8") == ""
    expected_sha = hashlib.sha256(b"extension-package").hexdigest()
    assert (output / "SHA256SUMS.txt").read_text(encoding="utf-8") == (
        f"{expected_sha}  {package.name}\n"
    )
    assert artifacts.package == copied_package
    assert artifacts.progress_index == output / "progress" / "index.html"
