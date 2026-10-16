from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[2]
CI = ROOT / ".github" / "workflows" / "ci.yml"
RELEASE = ROOT / ".github" / "workflows" / "release.yml"


def test_ci_workflow_runs_tests_and_checks_deterministic_package() -> None:
    text = CI.read_text(encoding="utf-8")
    assert "pull_request:" in text
    assert "python tools/build_extension.py" in text
    assert "python tools/sync_core_into_extension.py" in text
    assert text.index("python tools/sync_core_into_extension.py") < text.index("pytest -q")
    assert "pytest -q" in text
    assert "cmp" in text
    assert "actions/setup-python@v5" in text


def test_release_workflow_publishes_blender_repository_pages_and_release_assets() -> None:
    text = RELEASE.read_text(encoding="utf-8")
    assert "tags:" in text and "v*" in text
    assert "contents: write" in text
    assert "pages: write" in text
    assert "id-token: write" in text
    assert "release_meta.py validate-tag" in text
    assert "python tools/sync_core_into_extension.py" in text
    assert text.index("python tools/sync_core_into_extension.py") < text.index("pytest -q")
    assert "extension server-generate" in text
    assert "actions/configure-pages@v5" in text
    assert "actions/upload-pages-artifact@v4" in text
    assert "actions/deploy-pages@v4" in text
    assert "gh release upload" in text and "--clobber" in text
    assert 'BLENDER_VERSION: "5.2.2"' in text
    assert 'blender-${BLENDER_VERSION}-linux-x64.tar.xz' in text
