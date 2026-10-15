# AluDIY Designer v0.1.0-alpha Design

## Status

Approved for implementation on 2026-10-14. This specification consolidates the line-driven, profile-semantic, dual-view and precise-input prototypes into the first executable Blender experience.

## Goal

Build an installable Blender 5.2.2 LTS extension that lets a user create and edit aluminum-extrusion members as precise engineering lines while a linked 3D representation updates from the same project data.

The alpha proves one vertical slice:

1. load a versioned local profile catalog;
2. create nodes and line-based members with exact millimeter input;
3. derive simplified 3D solids from profile section metadata;
4. show line and solid views side-by-side with linked selection and optional camera synchronization;
5. save and reload the project as structured JSON.

## Product Boundary

### Included

- Blender Extension package targeting Blender 5.2.2 LTS.
- Independent pure-Python engineering core with no `bpy` dependency.
- Stable IDs for projects, nodes, members, profiles and semantic interfaces.
- Local catalog source files compiled to SQLite for runtime lookup.
- Five test profile types: 2020 four-slot, 2040 six-slot, 3030 four-slot, 3060 six-slot and 3030 three-slot.
- Millimeter-based precise value parser: plain numbers, `mm`, `cm`, `m`, addition/subtraction and `@length<angle` polar input.
- Two-click member drawing on an XY work plane, with typed length override.
- Sample rectangular frame generation.
- Member length editing with fixed start, fixed end or fixed center behavior.
- Simplified rectangular-envelope 3D solids and semantic slot metadata.
- A dedicated `ALU DIY` workspace setup with line and solid 3D view areas.
- Project JSON export/import and deterministic regeneration.
- Basic cut list CSV with member ID, profile ID and system length.

### Excluded

- AI design, web editor, quotation, inventory, payment and ordering.
- Exact supplier DXF/STEP geometry, detailed T-slot meshes and manufacturing output.
- Automatic joint solving, retreat, miter, drilling, tapping or connector placement.
- Structural verification, arbitrary-angle frames, curved members or panel systems.
- Multi-user collaboration and remote catalog synchronization.
- Direct editing of generated meshes.

## Version Baseline

- Blender runtime: `5.2.2 LTS`.
- Extension minimum Blender version: `5.2.0`.
- Python core: Python `>=3.11`; tests run on the available Python 3.13 environment.
- Extension version: `0.1.0`.

## Architecture

```text
profile source packages (JSON)
          │ validate / compile
          ▼
profile_catalog.sqlite ───────────────┐
                                      │
project.aludiy.json ── aludiy_core ───┼── Blender extension adapters
                                      │          ├─ line objects
                                      │          ├─ solid cache objects
                                      │          ├─ panels/operators
                                      │          └─ dual-view synchronization
                                      │
                                      └── cut-list CSV
```

### Authority Rules

- The external catalog source package is authoritative for profile types and semantic interfaces.
- `Project` in the engineering core is authoritative for nodes and members.
- Blender line and solid objects are views/caches identified by stable entity IDs.
- Generated mesh topology, Blender object names and mesh edge/face indices are never authoritative.
- Millimeters are authoritative in engineering data. Blender locations are converted to meters at the adapter boundary.

## Domain Model

### `Node`

- `id: str`
- `position_mm: tuple[float, float, float]`

### `Member`

- `id: str`
- `start_node_id: str`
- `end_node_id: str`
- `profile_type_id: str`
- `anchor_ref: str`
- `roll_deg: float`
- `revision: int`

A member is the engineering meaning of a line. Its length is derived from its referenced nodes.

### `SectionDefinition`

Alpha representation:

- `section_id`
- `width_mm`
- `height_mm`
- `origin_uv_mm`
- semantic faces and interfaces
- source revision and geometry hash

Exact contour loops are deferred, but the schema reserves a `representations` section for later DXF and normalized contour files.

### `InterfaceDefinition`

- stable ID such as `FACE_PV.S0`
- host face ID
- interface kind such as `T_SLOT_RAIL`
- interface standard ID
- section-local center coordinates
- outward normal and face tangent
- lane index and lane count

Runtime references use `member_id + interface_id + station_mm`.

## Precise Input

The core parser accepts:

- `1200` → `1200 mm`
- `1200mm` → `1200 mm`
- `120cm` → `1200 mm`
- `1.2m` → `1200 mm`
- `600+20` → `620 mm`
- `@1200<30` → polar input with length `1200 mm` and angle `30°`

The expression grammar supports decimal numbers, units, parentheses, unary signs and `+ - * /`. It rejects names, function calls and non-finite values.

Length edits always declare one anchor mode:

- `START`: keep start node fixed;
- `END`: keep end node fixed;
- `CENTER`: move both endpoints equally.

## Blender Representation

### Collections

- `ALUDIY_AXES`: line objects and node markers.
- `ALUDIY_SOLIDS`: generated extrusion envelope meshes.
- `ALUDIY_HELPERS`: temporary drawing and diagnostics.

### Object Identity

Axis object:

```text
aludiy_entity_type = "MEMBER_AXIS"
aludiy_entity_id = "M-001"
```

Solid object:

```text
aludiy_entity_type = "MEMBER_SOLID"
aludiy_source_id = "M-001"
aludiy_source_revision = 1
```

### Workspace

The setup operator creates or configures an `ALU DIY` workspace with two `VIEW_3D` areas:

- left: line view, orthographic/wire overlay;
- right: solid view, perspective/solid shading.

The same engineering project feeds both. Selection is mirrored by member ID. View synchronization can be set to:

- `FULL`: direction, center and distance;
- `ORIENTATION`: direction and center only;
- `OFF`.

## User Experience Acceptance

A tester can:

1. install the extension from ZIP in Blender 5.2.2 LTS;
2. run **Setup ALU DIY Workspace**;
3. run **Create 1200 × 600 Sample Frame** and see four line members and four solid members;
4. select either a line or solid representation and see the corresponding representation selected;
5. edit one member to `1500 mm`, choose `START`, and rebuild; the linked node, line and solid update;
6. create a new member by two clicks and type an exact length before confirmation;
7. switch a member from 2020 to 2040 and see the envelope and semantic interface list change;
8. export project JSON and cut-list CSV;
9. reload the JSON and regenerate equivalent objects.

## Error Handling

- Missing catalog/profile: report error and do not silently substitute.
- Zero-length member: reject before persistence or geometry generation.
- Invalid numeric expression: retain prior value and show an actionable message.
- Duplicate stable ID: reject loading the project.
- Catalog revision mismatch: warn and keep the project snapshot reference.
- Blender cache object edited or deleted: rebuild it from engineering data.

## Licensing Boundary

The installable Blender extension manifest uses `GPL-3.0-or-later`, consistent with Blender extension distribution expectations. No remote repository publication is performed in this alpha. The independent core boundary remains explicit so later service/API separation can be evaluated before commercial distribution.

## References

- Blender 5.2 LTS releases: https://www.blender.org/releases/5-2/
- Blender extension creation: https://docs.blender.org/manual/en/5.2/advanced/extensions/getting_started.html
- Prior interactive prototypes: `docs/prototypes/`
