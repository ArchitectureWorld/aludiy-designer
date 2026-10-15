# Changelog

All notable AluDIY Designer changes are recorded here. The project is in alpha; project-file compatibility is documented per release.

## Unreleased

## 0.1.7-alpha

- Add scoped engineering G movement, screen-space endpoint handles and explicit KEEP/DETACH modes.
- Deduplicate shared nodes during group movement; preserve ordinary Blender G and native deletion shortcuts.
- Preview without persisting data, cancel without split nodes, commit with one-step Undo/Redo.
- Add actual Blender 5.2.2 background and X11/XTest GUI regressions.
- Fix multi-selection synchronization, freshly rebuilt object selection and invalid panel icons.


- Continue toward complete engineering snapping and persistent constraints.

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
