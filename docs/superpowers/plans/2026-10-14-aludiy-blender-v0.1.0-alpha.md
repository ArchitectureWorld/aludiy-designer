# AluDIY Designer v0.1.0-alpha Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver an installable Blender 5.2 LTS alpha that creates precise line-driven aluminum members, derives linked 3D envelope solids, and round-trips structured project data.

**Architecture:** A pure-Python `aludiy_core` owns domain data, catalog lookup, input parsing and geometry derivation. A thin Blender extension adapts that model into axis and solid cache objects, provides operators/panels, and manages two linked 3D views. Catalog source JSON is validated and compiled to a local SQLite database.

**Tech Stack:** Python 3.11+, pytest, stdlib dataclasses/JSON/SQLite/TOML, Blender 5.2.2 LTS Python API.

**Spec:** `docs/superpowers/specs/2026-10-14-aludiy-blender-v0.1.0-alpha-design.md`

## Global Constraints

- Target Blender `5.2.2 LTS`; manifest minimum is `5.2.0`.
- Engineering coordinates and dimensions are stored in millimeters; Blender adapter converts to meters.
- `aludiy_core` must not import `bpy`.
- Stable entity IDs and structured project/catalog data are authoritative; generated Blender meshes are caches.
- The alpha supports straight members on an XY work plane and simplified rectangular section envelopes only.
- No AI, web commerce, automatic joint solving, structural analysis or direct generated-mesh editing.
- The Blender extension manifest license is `SPDX:GPL-3.0-or-later`.

## Review Focus

- Malformed or unsafe numeric expressions must fail without evaluation side effects.
- Duplicate IDs and references to missing nodes/profiles must be rejected deterministically.
- Zero-length and near-zero-length members must never generate geometry.
- Millimeter-to-meter conversion must be applied exactly once at the Blender boundary.
- Catalog/profile switching must not retain interface IDs that do not exist on the replacement profile.

---

### Task 1: Engineering model and versioned profile catalog

**Files:**
- Create: `pyproject.toml`
- Create: `src/aludiy_core/__init__.py`
- Create: `src/aludiy_core/errors.py`
- Create: `src/aludiy_core/model.py`
- Create: `src/aludiy_core/catalog.py`
- Create: `tools/build_catalog.py`
- Create: `catalog/schema/*.schema.json`
- Create: `catalog/profiles/*.json`
- Test: `tests/core/test_model.py`
- Test: `tests/core/test_catalog.py`

**Interfaces:**
- Produces: `Node`, `Member`, `Project`, `SectionDefinition`, `InterfaceDefinition`, `ProfileType`, `ProfileCatalog`, `compile_catalog(source_dir, sqlite_path)`.

- [ ] Write failing tests for stable project validation, missing references, duplicate IDs, five profile records and 2040 six-slot semantics.
- [ ] Run `pytest tests/core/test_model.py tests/core/test_catalog.py -v` and verify failure because modules do not exist.
- [ ] Implement the minimal dataclasses, validation, JSON round-trip, source catalog loader and SQLite compiler/reader.
- [ ] Run task tests and the full `pytest` suite; verify all pass.
- [ ] Commit `feat: add engineering model and profile catalog`.

### Task 2: Precise input and member geometry derivation

**Files:**
- Create: `src/aludiy_core/units.py`
- Create: `src/aludiy_core/geometry.py`
- Modify: `src/aludiy_core/model.py`
- Test: `tests/core/test_units.py`
- Test: `tests/core/test_geometry.py`

**Interfaces:**
- Consumes: Task 1 `Project`, `Member`, `ProfileCatalog`.
- Produces: `parse_length_mm(text)`, `parse_polar(text)`, `resize_member(project, member_id, length_mm, anchor)`, `derive_member_envelope(project, member_id, catalog)`.

- [ ] Write failing tests for unit expressions, unsafe expressions, polar input, all three fixed-end modes, zero-length rejection and a 2040 rotated envelope.
- [ ] Run task tests and verify expected missing-symbol failures.
- [ ] Implement a restricted AST evaluator, vector operations, resize propagation and deterministic envelope descriptor.
- [ ] Run task tests and the full suite; verify all pass.
- [ ] Commit `feat: add precise input and member geometry`.

### Task 3: Project I/O and cut-list output

**Files:**
- Create: `src/aludiy_core/io.py`
- Create: `src/aludiy_core/cutlist.py`
- Test: `tests/core/test_io.py`
- Test: `tests/core/test_cutlist.py`

**Interfaces:**
- Consumes: Tasks 1-2 project and geometry interfaces.
- Produces: `save_project`, `load_project`, `write_cutlist_csv`, `create_sample_frame`.

- [ ] Write failing tests for deterministic JSON, load validation, a four-member 1200 × 600 frame and cut-list lengths.
- [ ] Run task tests and verify missing-symbol failures.
- [ ] Implement minimal deterministic I/O, sample-frame factory and CSV writer.
- [ ] Run task tests and full suite; verify all pass.
- [ ] Commit `feat: add project persistence and cut list`.

### Task 4: Blender 5.2 extension adapter and user operations

**Files:**
- Create: `extension/aludiy_designer/blender_manifest.toml`
- Create: `extension/aludiy_designer/__init__.py`
- Create: `extension/aludiy_designer/runtime.py`
- Create: `extension/aludiy_designer/scene_adapter.py`
- Create: `extension/aludiy_designer/operators.py`
- Create: `extension/aludiy_designer/panels.py`
- Create: `extension/aludiy_designer/view_sync.py`
- Create: `extension/aludiy_designer/vendor/aludiy_core/*`
- Create: `tools/sync_core_into_extension.py`
- Test: `tests/extension/test_manifest.py`
- Test: `tests/extension/test_static_contract.py`

**Interfaces:**
- Consumes: all `aludiy_core` APIs from Tasks 1-3.
- Produces: installable extension with register/unregister, workspace setup, sample frame, rebuild, exact member edit, JSON import/export and cut-list export operators.

- [ ] Write failing manifest/package/static-contract tests, including minimum Blender version, registration symbols and absence of `bpy` in vendored core.
- [ ] Run tests and verify failure because extension files do not exist.
- [ ] Implement extension registration, scene JSON storage, axis/solid cache generation, panels/operators, selection linking and guarded dual-view synchronization.
- [ ] Synchronize the pure core into the extension and run static compilation.
- [ ] Run task tests and full suite; verify all pass.
- [ ] Commit `feat: add Blender extension experience`.

### Task 5: Package, documentation and acceptance artifact

**Files:**
- Create: `docs/acceptance/v0.1.0-alpha.md`
- Create: `tools/build_extension.py`
- Modify: `README.md`
- Create: `tests/extension/test_package.py`

**Interfaces:**
- Consumes: Task 4 extension directory.
- Produces: `dist/aludiy_designer-0.1.0.zip`, setup instructions and acceptance checklist.

- [ ] Write a failing package test that checks root manifest, root `__init__.py`, vendored core and no test/cache files.
- [ ] Run it and verify failure because the ZIP does not exist.
- [ ] Implement deterministic ZIP packaging and concise Blender 5.2.2 installation/acceptance instructions.
- [ ] Run `python tools/build_extension.py`, package tests, `python -m compileall`, and the full `pytest` suite.
- [ ] Commit `build: package v0.1.0-alpha extension`.
