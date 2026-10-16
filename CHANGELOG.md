# Changelog

All notable AluDIY Designer changes are recorded here. The project is in alpha; project-file compatibility is documented per release.

## Unreleased

## 0.1.11-alpha

- Share geometry-only endpoint, midpoint, perpendicular-foot and member-axis snap candidates between drawing and G.
- Pick elevated rod-body points directly when beginning a line; Ctrl toggles snapping and Tab cycles explicit candidates.
- Add explicit Shift+axis plane locks to drawing; numeric lengths remain double-precision and override snap position/markers.
- Share the viewport ray/projection unit boundary to eliminate sub-micrometre differences between drawing and movement.
- Mirror drawing target feedback to both views while preventing sidebar/other-view clicks from creating geometry.
- Preserve independent new endpoints and existing manual associations; no schema upgrade.
- Record the user's basic acceptance of 0.1.10. Add real drawing/movement/association/Undo/reopen verification.

## 0.1.10-alpha

- Highlight every selected engineering member/node in both viewports with deduplicated counts and separate affected-object dashes.
- G and new drawing/sample endpoints position without automatic association; existing shared nodes remain intact.
- Explicit multi-selection Create/Remove Associations; coincident endpoint groups and one-way host-axis attachments with normalized station.
- Preserve unrelated relationships during partial unlink; reject ambiguous hosts, cycles and conflicting moves atomically.
- Keep authoritative snap coordinates in float64 through confirmation; no float32 roundtrip join mismatch.
- Association files use schema 0.2.0; keep a separate backup before opening in older plugins.


## 0.1.9-alpha

- Default G endpoint snapping with confirmed shared-node reconnection, including zero-displacement joins.
- Hold Ctrl during G for temporary free movement; keep old connection mode separate from snapping.
- Add cursor-nearest source anchor, Tab candidate cycling, connect-to-target picker and configurable ground elevation (placement only).
- Preserve exact numeric displacement, axis restrictions, selection on cancel, transactional preview, Undo/Redo and normal-object native G.
- Add pure-core, actual Blender backend and X11 keyboard/mouse reconnection regressions.


- v0.1.9 planned: shared engineering snapping for drawing and G movement; distinguish location from connection.

## 0.1.8-alpha

- Fix destructive sample generation: append a four-member XY frame at the 3D cursor instead of replacing the current project.
- Preserve existing project metadata, IDs, coordinates, member parameters and shared-node topology; allocate new IDs without auto-welding coincident nodes.
- Reuse transactional cache regeneration and rollback; add explicit confirmation before resetting non-empty engineering projects.
- Add sample preservation, repeat insertion, invalid input, failure rollback and real Blender undo/confirmation/reopen regressions.
- Record G movement and JSON exchange as user simple-scenario acceptance, not comprehensive acceptance; update the visual roadmap.

## 0.1.7-alpha

- Add scoped engineering G movement, screen-space endpoint handles and explicit KEEP/DETACH modes.
- Deduplicate shared nodes during group movement; preserve ordinary Blender G and native deletion shortcuts.
- Preview without persisting data, cancel without split nodes, commit with one-step Undo/Redo.
- Add actual Blender 5.2.2 background and X11/XTest GUI regressions.
- Fix multi-selection synchronization, freshly rebuilt object selection and invalid panel icons.

## 0.1.6-alpha

- Add exact XYZ editing for selected engineering nodes.
- Add exact start/end coordinate editing and XYZ translation for selected members.
- Propagate shared-node edits to all connected members and update their revisions.
- Add selected-member reference dimensions and selected-node coordinate feedback in the line view.
- Add the first GitHub Pages / Blender remote extension repository release pipeline.

## 0.1.5-alpha

- Add engineering-member deletion through `Ctrl + Shift + Delete`.
- Keep Blender's native `X`, `Delete`, and `Shift + Delete` behavior unchanged.
- Delete the linked engineering line and solid together, preserve shared nodes, and clean isolated nodes.

## 0.1.4-alpha

- Add XY, XZ, and YZ construction planes.
- Add X/Y/Z world-axis locking and vertical-column drawing.
- Add screen-space snapping for nodes at arbitrary elevations.

## 0.1.3-alpha

- Make optional viewport services fail safely without hiding the core N-panel.
- Add extension startup diagnostics.

## 0.1.2-alpha

- Add start-green/end-red engineering-line direction feedback.
- Add Rhino-style crosshair, coordinates, length, angle, and snap feedback while drawing.

## 0.1.1-alpha

- Add full dual-view rotation/zoom synchronization.
- Separate the line view from the solid view.
- Add BOX and semantic T-slot detail display modes.

## 0.1.0-alpha

- Add the independent engineering core, profile catalog, precise input parser, dual-view Blender extension, JSON project exchange, and basic cut-list output.
