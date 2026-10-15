# Changelog

All notable AluDIY Designer changes are recorded here. The project is in alpha; project-file compatibility is documented per release.

## Unreleased

- Establish the public source repository and GitHub-based Blender update channel.
- Add CI, deterministic package checks, GitHub Releases, and GitHub Pages publication.

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
