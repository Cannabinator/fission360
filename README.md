# Fission360

A parametric, history-based 3D CAD modeller for Linux/Ubuntu, modelled on the
workflow of Autodesk Fusion 360: sketch → constrain/dimension → features →
editable timeline, driven by named parameters.

![Fission360](docs/screenshot.png)

## Install & run (Ubuntu 22.04 / 24.04)

```bash
git clone https://github.com/cannabinator/fission360 && cd fission360
./scripts/install.sh      # venv in ~/.local/share/fission360, app-menu entry, .f3x MIME type
fission360                # or: fission360 part.f3x
```

For development: `./scripts/run-dev.sh` (creates `.venv`, editable install).
Tests: `pytest` (UI smoke test runs when a display is available, e.g. `xvfb-run -a pytest`).

### Remote access from Windows (browser or VNC, for testing)

`scripts/remote.sh` runs the app on a virtual display (Xvfb, software OpenGL)
and serves it with x11vnc + noVNC. Missing packages are installed via apt.
The app runs fullscreen and restarts automatically if you close it.

**Option A – SSH tunnel (default, nothing exposed to the network)**

On the Linux machine:
```bash
./scripts/remote.sh                 # options: --size 1920x1080  --port 6080  [file.f3x]
```
On Windows 11 (PowerShell, OpenSSH is built in):
```powershell
ssh -L 6080:localhost:6080 -L 5900:localhost:5900 user@linux-host
```
Then open <http://localhost:6080/vnc.html?autoconnect=1&resize=scale> in Edge/Chrome,
or connect a VNC client (TightVNC, RealVNC) to `localhost:5900`.

**Option B – direct on a trusted LAN**
```bash
./scripts/remote.sh --public        # prints URL + generated VNC password
```
Open `http://<linux-ip>:6080/vnc.html` from Windows. VNC traffic isn't encrypted,
so use option A on any network you don't fully trust.

Tips: in the browser, middle-drag pans and Shift + middle-drag orbits as usual. If your
mouse lacks a middle button, use right-drag (orbit) and the navigation bar. The noVNC side
panel has clipboard and fullscreen buttons.

Requirements: Python ≥ 3.10 and an OpenGL 3.3 driver (any Mesa/NVIDIA/AMD/Intel driver of the last decade).

## Features

**Modelling workflow (Fusion-style)**
- Parametric **timeline** with rollback marker, drag-to-reorder, suppress, edit, delete; failing features turn red with the reason.
- **Parameters** dialog: user parameters + auto-created model parameters (`d1`, `d2`…), unit-aware expressions (`width/2 + 3 mm`, `30 deg`, `sqrt()`, `sin()`…), dependency tracking, cycle detection, rename-refactoring.
- Live **preview** for every command; the panel is generated from a declarative feature spec.
- Undo/redo for everything (including individual sketch edits), autosave every 2 min, recent files.

**Sketching**
- Line (chained), 2-point & center rectangle, circle, 3-point & center arc, polygon, slot, spline, point.
- Snapping to points/curves, horizontal/vertical inference, optional grid snap; auto-coincident constraints.
- Constraints: coincident, point-on-curve, horizontal, vertical, parallel, perpendicular, collinear, tangent, equal, concentric, midpoint, symmetry, fix.
- Smart dimension tool (length, distance, horizontal/vertical distance, radius, diameter, angle); dimensions accept expressions; over-constraining dimensions become driven (reference) dimensions.
- Live DOF count, fully-constrained geometry turns black (blue = free), direct dragging of geometry, trim, sketch fillet, construction geometry, project body edges.
- Sketch on origin planes, construction planes or any planar face. Profiles (closed regions, including nested ones) are detected automatically and shaded.

**Solid features**: extrude (one side / symmetric / two sides, taper, new body / join / cut / intersect), revolve, sweep, loft, hole (simple / counterbore / countersink), fillet, chamfer, shell, draft, box / cylinder / sphere / torus / coil, rectangular & circular pattern, mirror, combine, move/copy, scale, split body, remove, offset plane, plane at angle, construction axis.

**Inspect**: measure (distance, angle, length, area, radius), section analysis, mass properties per material, interference check.

**Data exchange**: STEP (AP214), IGES, STL, OBJ, BREP export; STEP, IGES, STL, BREP import. Native format `.f3x` (gzipped JSON, versioned).

**UI**: ribbon toolbar, browser tree (origin, bodies, sketches, construction; visibility, rename, appearance, material, isolate), ViewCube with animated views, navigation bar, visual styles, **S** command search, right-click **marking menu**, light/dark themes.

### Mouse & keys
| Action | Input |
|---|---|
| Orbit | Shift + middle drag, right drag, Alt + left drag (pivots on geometry under the cursor) |
| Pan | Middle drag |
| Zoom | Wheel (zooms about the cursor) |
| Fit | F6 / double-click middle |
| Commands | S search · E extrude · F fillet · H hole · M move · I measure · Del delete |
| Sketch | L line · R rectangle · C circle · A arc · D dimension · T trim · P project · X construction · Esc cancel |

## Architecture & technical decisions

```
fission360/
  core/expressions.py   safe AST evaluator with units (no eval) → documents can't run code
  core/parameters.py    parameter table, dependencies, cycle detection
  core/kernel.py        the only module touching OpenCASCADE (OCP bindings)
  core/references.py    persistent face/edge/profile references (topological naming)
  core/features.py      declarative feature specs + rebuild executors
  core/document.py      timeline, incremental rebuild, undo/redo, persistence
  sketch/solver.py      numeric constraint solver
  sketch/model.py       sketch entities, constraints, dimensions
  ui/                   Qt 6 widgets, OpenGL renderer, tools, panels
```

- **Kernel: OpenCASCADE (OCCT)**, the only production-grade open B-rep kernel, via the `cadquery-ocp` wheels (no compiling). Booleans run parallel with fuzzy tolerance and results are cleaned with `UnifySameDomain` so faces split by booleans merge back. Profile detection uses OCCT's General Fuse on a bounding face, which yields Fusion-like region selection for overlapping/nested curves.
- **Incremental rebuild**: every feature has a cumulative fingerprint (its definition + the values of the parameters it uses + everything before it). Only features after the first changed one are recomputed; earlier model states are reused (B-rep handles are immutable, so caching is cheap). Typical parameter changes rebuild in tens of milliseconds.
- **Topological naming**: references store geometric signatures (type, centre, normal/tangent, size) and re-resolve by best match scaled by body size, so fillets/shells/sketch-on-face survive dimension changes. Profiles are referenced by an interior point, the same approach Fusion uses.
- **Constraint solver**: damped Gauss–Newton with *minimum-norm* SVD steps; geometry not pinned by constraints moves as little as possible, which makes dragging feel natural. Dragged points are column-weighted so they stick to the cursor. DOF and per-entity "fully constrained" state come from the Jacobian null space; redundant/conflicting constraints are rejected.
- **Rendering**: OpenGL 3.3 core profile. One VAO per body uploaded on geometry change only; Blinn-Phong key/fill/rim lighting; geometry-shader thick anti-aliased lines (core profile has no wide lines); MSAA; integer-ID picking buffer read in a small window around the cursor with priority vertex > edge > face, so thin edges are easy to hit; clip plane for section analysis; tessellation deflection adapts to model size.
- **UI**: Qt 6 (PySide6) — native on X11 and Wayland, HiDPI aware. Feature dialogs are generated from specs, so adding a feature is a spec entry + one executor function.

## Scope & roadmap

Fission360 covers Fusion 360's core part-design workflow. Not (yet) implemented: assemblies/components & joints, surface/T-spline/mesh workspaces, sheet metal, drawings, CAM, simulation, rendering, cloud collaboration, and history-based (rather than signature-based) topological naming. Next steps: components & joints, 2D drawings from models, sketch offset/mirror/pattern, text, threads, full-history naming via OCCT's `BRepTools_History`.

## License

LGPL-2.1-or-later (compatible with OpenCASCADE's license).
