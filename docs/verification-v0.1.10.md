# Verification record — 0.1.10

## Recovery and provenance
The previous temporary v0.1.10 directory was not available in this runtime: only screenshots and 2/11 remote transport fragments survived. This session recovered the complete, previously verified 0.1.9 source from the attached CI source archive (b6573c427e75a029dfde29f754b7c38c0d0ac527), and reconstructed the missing changes. Earlier screenshots/test claims are not used as evidence for this build.

## Executed tests
- Baseline: 155 Python tests passed.
- Red/green: missing association module, host propagation, independent movement, manual node linking, unlink/legacy splitting, serialization, deduplicated movement, host resize, conflict rejection, snapping precision; then partial unlink, independent samples and same-station followers.
- Current Python suite: 175 tests. Run `python tools/sync_core_into_extension.py; pytest -q`.
- Official recovered Blender binary: 5.2.2 LTS, build 2026-09-15, d13f752e3b9c.
- Real Blender backgrounds: original smoke, movement/selection/registration and explicit reconnect safety tests.
- Real Blender Linux/X11: 28 new manual-association checks, 28 existing movement checks, 16 sample-safety checks. The new test includes real Shift-click and G/Ctrl/Undo key events plus direct drawing-command and operator checks. It is not a claim that every check is an end-to-end mouse test.
- New-process reopen comparisons for manual associations, old shared-node movement and independent sample insertion.
- Deterministic same-environment ZIP builds and official extension validation.

Use `bash tools/verify_manual_associations.sh <blender> <absolute-evidence-dir>` for the exact runtime suite. Logs and report JSON are retained in CI. Windows, DPI combinations and large-project performance remain user acceptance.

## Review
No independent reviewer agent was available. Inline source review caught partial unlink preservation and multiple followers at one host station; regression tests were added before their fixes. XTest harness defects (modifier key lifetime and F6 keysym case) were diagnosed without weakening product assertions.

## Release
The remote publishing workflow pins the final tested feature SHA. Publication is complete only after public index and package-size/SHA-256 verification, not merely after a source push. Publishing Preview does not merge the stacked feature branches.
