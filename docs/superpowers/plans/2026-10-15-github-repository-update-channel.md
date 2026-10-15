# GitHub Repository and Blender Update Channel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import the current v0.1.5 source into the public GitHub repository and add tested CI, release, GitHub Pages, and Blender remote-update automation.

**Architecture:** Keep the Python/Blender source tree unchanged while making release metadata manifest-driven. A small site builder prepares the static Pages directory; Blender 5.2.2 generates the official repository index during tagged releases.

**Tech Stack:** Python 3.11+, pytest, Blender Extension manifest, GitHub Actions, GitHub Pages, GitHub CLI.

**Spec:** `docs/superpowers/specs/2026-10-15-github-repository-update-channel-design.md`

## Global Constraints

- Repository: `ArchitectureWorld/aludiy-designer`.
- Default branch: `main`.
- Extension ID: `aludiy_designer`.
- Minimum Blender version: `5.2.0`.
- Release Blender CLI: `5.2.2`.
- License: `GPL-3.0-or-later`.
- Do not add unlicensed supplier CAD files, credentials, user data, or purchase prices.

## Review Focus

- A tag with the wrong version must fail before publishing.
- Package naming must follow the manifest version without manual duplication.
- The Pages site must expose a ZIP ending in `.zip` and a stable progress page.
- CI must catch source/vendor drift and package nondeterminism.
- Release reruns must update an existing GitHub Release rather than fail destructively.

---

### Task 1: Manifest-driven release metadata

**Files:**
- Create: `tools/release_meta.py`
- Modify: `tools/build_extension.py`
- Modify: `tests/extension/test_package.py`
- Create: `tests/extension/test_release_meta.py`

- [ ] Write failing tests for manifest version parsing, tag validation, and dynamic package naming.
- [ ] Run the focused tests and confirm they fail for missing interfaces.
- [ ] Implement release metadata helpers and remove hard-coded package version.
- [ ] Run focused tests and the full suite.
- [ ] Commit.

### Task 2: Static repository site builder

**Files:**
- Create: `tools/build_pages_site.py`
- Create: `tests/extension/test_pages_site.py`
- Create: `docs/progress/index.html`

- [ ] Write failing tests for package copy, stable progress URL, `.nojekyll`, and SHA file generation.
- [ ] Run the focused tests and confirm failure.
- [ ] Implement the deterministic site builder.
- [ ] Run focused tests and the full suite.
- [ ] Commit.

### Task 3: GitHub CI and release workflows

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/release.yml`
- Create: `tests/extension/test_github_workflows.py`

- [ ] Write static contract tests for triggers, permissions, official Pages actions, Blender server generation, and release upload.
- [ ] Run the focused test and confirm failure.
- [ ] Add CI and tagged-release workflows.
- [ ] Run focused tests and the full suite.
- [ ] Commit.

### Task 4: Public repository documentation and licensing

**Files:**
- Create: `LICENSE`
- Create: `CHANGELOG.md`
- Modify: `README.md`
- Modify: `.gitignore`

- [ ] Add repository, remote update, migration, Pages enablement, and release instructions.
- [ ] Add root GPL license and changelog.
- [ ] Run full tests and deterministic builds twice.
- [ ] Commit.

### Task 5: Publish the baseline snapshot to GitHub

**Files:** all tracked repository files.

- [ ] Verify local branch is clean and full tests pass.
- [ ] Initialize `main` in the empty GitHub repository.
- [ ] Upload the source snapshot, workflows, binary catalog cache, and current package.
- [ ] Verify GitHub file tree and workflow presence.
- [ ] Report the one-time Pages setting still required from the user.
