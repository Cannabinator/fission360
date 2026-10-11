# Third-party software and notices

Fission360 is licensed under the GNU LGPL 2.1 or later (see `LICENSE`). It does **not** bundle any third-party
code or fonts; the packages below are installed separately (by `pip` / `apt`) and linked dynamically.

| Component | Licence | Used for |
|---|---|---|
| OpenCASCADE Technology (via `cadquery-ocp` wheels, Apache-2.0 bindings) | LGPL-2.1 with the OCCT exception | B-rep kernel: booleans, fillets, STEP/IGES/STL, HLR drawing views |
| PySide6 / Qt 6 / shiboken6 | LGPL-3.0 (or GPL / commercial) | User interface, OpenGL widget |
| PyOpenGL | BSD-3-Clause | OpenGL bindings |
| NumPy | BSD-3-Clause (and others, see NumPy) | Numerics |
| pytest (development only) | MIT | Tests |
| DejaVu fonts (`fonts-dejavu-core`, installed by `scripts/install.sh`) | Bitstream Vera / public-domain terms | Default font for sketch text; not distributed with this repository |

Qt and PySide6 are used under the LGPL-3.0, which the "or later" clause of the project licence is compatible with.
If you redistribute a bundled build, keep Qt and PySide6 dynamically linked and provide their licence texts.

## What was written from scratch

All source files, the icons (inline SVG in `fission360/ui/icons.py`, `packaging/fission360.svg`) and the screenshot are
original to this project. Standards data (ISO 261 / ASME B1.1 thread sizes, ISO paper sizes, material densities) are
published engineering facts, not copyrighted expression. The DXF, SVG, STEP and 3MF readers/writers implement public
file-format specifications; no vendor SDK or sample code is included.

## Trademarks

"Autodesk" and "Fusion 360" are trademarks of Autodesk, Inc. Fission360 is an independent open-source project and is
**not affiliated with, endorsed by or sponsored by Autodesk**. Fusion 360 is named only to describe the workflow this
project is modelled on (nominative use). Other product names belong to their owners.
