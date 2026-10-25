# Joint Scheme Editor Phase 1 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to execute each task and retain evidence in the ledger. User has expressly authorized implementation and Preview publication.

**Goal:** Ship v0.1.20 tested junction recipe preview for 2/3 selected members.
**Architecture:** Pure core choices over current ButtJoint rules; isolated GPU preview in native operator dialog; atomic commit via existing adapter.
**Tech Stack:** Python 3.11+, Blender 5.2.2; no added runtime dependencies.
**Spec:** docs/junction-roadmap-v1.0.md, First Phase.

## Global constraints
Axes/nodes/associations unchanged; preview read-only; no schema bump; preserve other joints and native Undo; no manufacturing claim.
## Review Focus
Empty selection/scene; existing endpoint external dependency; oversized profiles causing branch-branch collision; stale project/selection during popup; exception/cancel leaves overlays or data dirty.

### Task 1 — core
Create src/aludiy_core/joint_editor.py; extend joints.py with scoped rectangular-envelope collision guard. APIs joint_choices(project,catalog,member_ids,gap_mm) returning immutable options; apply_joint_choice(...host_member_id...) validates one option and returns JointChange.
- [x] Write core regressions, observe failures.
- [x] Implement deterministic choices, local replacement, bounds and validation.
- [x] All new and existing core tests pass.
### Task 2 — native preview editor
Create extension/aludiy_designer/joint_editor.py with native invoke_props_dialog, host choices/gap/view mode; POST_PIXEL local actual-envelope preview. No project writes during draw/check. Confirm calls existing transactional adapter after stale guards; cancel tears down. Integrate with sidebar/middle menu and lifecycle.
- [x] Add actual Blender invocation and cancellation/regression probes; observe failure before implementation.
- [x] Implement and run cold startup, preview, confirm, undo/redo, data preservation and save/reopen at UI scale1/1.5.
### Task 3 — review and release
- [ ] Full Python retained suites, real Blender old features, isolated install-over-install, deterministic builds and official validate.
- [ ] Whole-diff review; fix critical/important issues with regression evidence.
- [ ] Pin tested source, publish Preview, fetch public index/ZIP and compare hash/size/source.
- [ ] Deliver dashboard, roadmap, screenshot, test .blend, ZIP/source and evidence.
