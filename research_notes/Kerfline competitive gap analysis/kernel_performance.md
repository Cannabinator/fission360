# Kernel, robustness, performance and architecture for a Fusion-class CAD modeller

Research limits: the search tool returned snippets only. WebFetch could not reach dev.opencascade.org or newreleases.io (DNS failure), so release notes were not read in full. Items under "Inferences" marked [background] come from general domain knowledge, are not source-verified, and should be checked before use.

## 1. OCCT versions (7.8 / 7.9 / 8.0) and what changed

### Takeaway
OCCT is now at 8.0.x (8.0.1 exists), with 7.9.x as the maintained previous line. The 8.0 cycle is mostly API modernisation (C++17, new geometry evaluation API, std threading) plus reliability fixes, not a new Boolean/fillet engine. Details of modelling-algorithm gains were not retrievable.

### Cited Findings
- OCCT 7.8.0 shipped 4 Dec 2023, a minor release with about 110 improvements over 7.7.0. Data exchange was reorganised into per-format toolkits (e.g. TKXDEGLTF) with a plug-in system for CAD format providers. JeMalloc is cited as giving up to 40% speedup on large files. — [OCCT 7.8.0 released](https://dev.opencascade.org/content/open-cascade-technology-780-released), [Exciting upgrades in 7.8.0](https://dev.opencascade.org/content/exciting-upgrades-coming-occt-780-release)
- A tracker report (Apr 2024) says BRepMesh_IncrementalMesh fails to mesh a conical surface in 7.8.0 but works in 7.6.1, i.e. a meshing regression. — [Mantis 33681](https://tracker.dev.opencascade.org/view.php?id=33681)
- OCCT 7.9.0 has over 250 improvements vs 7.8.0: static analysis, Clang-Format, RTTI/IsKind optimisation, deprecated Handle aliases, NCollection_MapAlgo set operations. — [7.9.0 released](https://dev.opencascade.org/content/open-cascade-technology-790-released)
- 7.9.1 (30+ fixes, precompiled-header delivery, CMake fixes) and 7.9.2 (25+ fixes, move to C++17, modelling bug fixes). — [7.9.1](https://dev.opencascade.org/content/open-cascade-technology-791-released), [7.9.2](https://dev.opencascade.org/content/open-cascade-technology-792-released)
- Open Cascade's commercial Added Value Components 7.9.0 added a USD Exchange import/export component (commercial, not part of open-source OCCT). — [Open Cascade news](https://dev.opencascade.org/node?page=1)
- 8.0.0 went through 3 betas and 5 release candidates, 500+ changes since 7.9.0. RC1 moved resources into /resource; RC2 vcpkg/CMake work; RC3 replaced OCCT math wrappers with std:: and Standard_Mutex with std::mutex; RC4 introduced a redesigned geometry evaluation API (EvalD* returning plain structs instead of virtual D0-D3), new hash maps/collections and a Python migration toolkit; RC5 added Gordon surface construction (GeomFill_Gordon), new extrema packages, return-by-value handle APIs, removed TColGeom packages and fixed thread-safety issues. Pre-C++17 compilers are unsupported. — [8.0.0 release](https://dev.opencascade.org/content/open-cascade-technology-800-release), [RC3](https://dev.opencascade.org/content/open-cascade-technology-800-release-candidate-3), [RC4](https://dev.opencascade.org/content/open-cascade-technology-800-release-candidate-4), [RC5](https://dev.opencascade.org/content/open-cascade-technology-800-release-candidate-5)
- 8.0.1 release notes focus on modelling reliability, shape healing, periodic geometry, meshing, STEP export and "concurrent fillet construction". — [V8.0.1](https://newreleases.io/project/github/Open-Cascade-SAS/OCCT/release/V8.0.1)

### Inferences
- Gordon surfaces (8.0) and concurrent fillet construction (8.0.1) are the notable modelling items found; both are worth testing, but the claim of improved fillet robustness is unverified.
- A product pinned to OCP will lag the newest OCCT; plan the 8.0 API migration (EvalD*, TColGeom removal) as a one-off cost if moving to C++ directly.
- [background] HLR (HLRBRep / HLRAlgo polygon mode) and BOPAlgo parallel mode have existed for years; I found no source for new 7.8-8.0 HLR work.

### Gaps
- Full 7.8/7.9/8.0 changelogs (HLR, Boolean speed, data-exchange changes) were not read; fetch failed.
- No benchmark numbers for Boolean speed per version.

## 2. OCCT strengths/weaknesses vs Parasolid/ACIS (fillets, booleans, meshing, threading, licence)

### Takeaway
No published head-to-head fillet benchmark was found. Evidence is anecdotal: Parasolid is regarded as the robustness leader; OCCT Booleans were slower than a research algorithm that matched Parasolid/ACIS. OCCT is LGPL 2.1 + exception, usable commercially with compliance duties.

### Cited Findings
- A 2024 paper compared a new B-Rep Boolean algorithm against OCCT, Parasolid and ACIS on real CAD models: more efficient than OCCT, roughly on par with Parasolid and ACIS in some cases. — [JCAD 2024](https://www.jcad.cn/en/article/pdf/preview/10.3724/SP.J.1089.2024-00367.pdf)
- Practitioner forum comment ranks Parasolid and Autodesk ShapeManager as having few fillet failures, ACIS-based tools lower (anecdotal). — [McNeel forum](https://discourse.mcneel.com/t/best-software-to-make-fillets-exporting-from-rhino/47429)
- Floating-point error compounds across chained booleans, offsets, shells and fillets in every kernel. — [NovEdge overview](https://novedge.com/blogs/design-news/design-software-history-numerical-robustness-in-geometry-kernels-history-failure-modes-and-engineering-playbook)
- BRepMesh parallelism uses TBB (since 6.4), only when Standard::IsReentrant() is true; the 7.3.0 refactor made edge tessellation parallel and reported up to 10x speedup on a ~93,000-box case. — [Multithreaded BRepMesh](https://dev.opencascade.org/content/multithreaded-brepmeshmesh), [refactoring BRepMesh](https://dev.opencascade.org/content/refactoring-brepmesh)
- Old forum reports of segfaults when meshing faces from user threads ("OCCT is not thread safe", parallel mesh correct only for canonical surfaces); NetGen avoids parallel OCC surface meshing for thread-safety reasons. These are old; current status unverified. — [OCCT threads thread](https://dev.opencascade.org/content/occt-run-separate-threads-multithreading-too-slow), [NGSolve forum](https://forum.ngsolve.org/t/parallel-occt-meshing-how-to-identify-the-bad-face/2134)
- Licence: LGPL 2.1 with OCCT exception, or paid commercial licence from Open Cascade. Proprietary apps must give notice, make OCCT sources available, and allow running with a modified OCCT; static linking or app stores complicate this. — [OCCT repo](https://github.com/Open-Cascade-SAS/OCCT), [Debian copyright](https://metadata.ftp-master.debian.org/changelogs/main/o/opencascade/stable_copyright)

### Inferences
- Building a Fusion competitor on OCCT means owning a fillet/shell/offset failure-mitigation layer (fallbacks, tolerance retries, user-facing diagnostics). This is the main commercial risk.
- Use dynamic linking to keep LGPL compliance simple.
- [background] No sheet-metal, native thread features or PMI-driven drawings in OCCT; these must be built (threads as helical sweeps/cosmetic, sheet metal as a feature layer using unfold maths). Unverified in this research.

### Gaps
- No source on OCCT shell/offset reliability, BSpline fitting/filling G2 quality, XCAF colour/PMI fidelity, or HLR quality.
- No Hacker News / forum user comparisons found.

## 3. Python binding ecosystem (OCP / cadquery-ocp)

### Takeaway
cadquery-ocp 7.9.3.x is current on PyPI-line tracking (Jan-Feb 2026); wheels cover Python 3.10-3.13 (VTK variant) and up to 3.14 (no-VTK variant). OCP lags the newest OCCT 8.x.

### Cited Findings
- PiWheels lists cadquery-ocp 7.9.3.0 (2026-01-03) and 7.9.3.1 (2026-02-15), and cadquery-ocp-novtk 7.9.3.1.1 (2026-05-28). — [piwheels cadquery-ocp](https://www.piwheels.org/project/cadquery-ocp), [novtk](https://www.piwheels.org/project/cadquery-ocp-novtk/)
- Build-system README: 7.9.3.0 VTK wheel uses PyPI vtk 9.5.2 for Python 3.10-3.13; novtk wheel extends to 3.14. For 7.8.1.1 on Python 3.13 a separate cadquery_vtk package was needed. — [ocp-build-system](https://github.com/CadQuery/ocp-build-system)
- Debian python3-ocp 7.9.3.1 depends on OCCT 7.9.2 libs. — [Debian](https://packages.debian.org/sid/ppc64/python3-ocp)
- Rust bindings exist (opencascade-rs). — [gittrend](https://gittrend.io/repo/bschwind/opencascade-rs)

### Inferences
- Prefer the novtk wheel when you have your own renderer: fewer dependency conflicts and broader Python support.

### Gaps
- Did not confirm bundled OCCT version string per wheel or exact manylinux/arm64 availability.

## 4. Alternative kernels and licensing

### Takeaway
Parasolid/D-Cubed are the commercial default (Onshape, Plasticity, Shapr3D-class) but pricing is not public; open Rust kernels are not production-ready, and Fornjot has been shut down.

### Cited Findings
- Siemens licenses Parasolid to 130+ ISVs; no public price list found. — [engineering.com](https://www.engineering.com/parasolid-d-cubed-and-siemens-the-heart-of-your-cad-software-belongs-to-another/)
- Onshape uses Parasolid and D-Cubed licensed from Siemens; servers rebuild geometry from feature lists/FeatureScript, solve assemblies and generate tessellations; clients render triangles in WebGL; edits stored append-only. — [Onshape blog](https://www.onshape.com/en/blog/cloud-native-architecture-empowers-cad-pdm)
- Plasticity is a commercial NURBS modeller on Parasolid; the app dynamically links a commercial kernel under restrictive distribution terms (per early developer statement). — [Plasticity (Wikipedia)](https://en.wikipedia.org/wiki/Plasticity_(software)), [Fabbaloo](https://www.fabbaloo.com/news/plasticity-new-3d-modeling-tool-coming-soon)
- Fornjot: repo archived 19 Jun 2026, project shut down, goals not reached; last crate 0.49.0 (Mar 2024), usable only for simple models. — [Fornjot](https://github.com/hannobraun/fornjot)
- truck (ricosjp): Rust B-rep/NURBS kernel with truck-shapeops booleans; last push reported 3 May 2026; a fork "monstertruck" exists. Robustness unknown. — [truck](https://github.com/ricosjp/truck), [monstertruck](https://docs.rs/monstertruck)

### Inferences
- For a small team, switching kernels early is rarely sensible: the realistic options are OCCT now, with Parasolid evaluated only once there is revenue and a negotiated licence. Keep a kernel-abstraction layer (own Shape/Face IDs, operation wrappers) so a later swap is feasible.
- Do not bet on truck/Fornjot for Fusion-class parts.

### Gaps
- No pricing for Parasolid, ACIS, CGM or Granite; no info on Shapr3D's kernel setup; manifold and SolveSpace NURBS kernel not researched.

## 5. Topological naming

### Takeaway
FreeCAD 1.0 (Nov 2024) is the first stable release with realthunder's TNP mitigation, with more coverage promised. Details of the Onshape/Parasolid ID approach were not found.

### Cited Findings
- FreeCAD 1.0 includes the new naming algorithm based on realthunder's work; it aims to fix references automatically or suggest fixes, with wider application in later versions. — [FreeCAD wiki](https://wiki.freecad.org/Topological_naming_problem/en), [AlternativeTo](https://alternativeto.net/news/2024/11/freecad-1-0-launches-with-enhanced-ui-ux-built-in-assembly-workbench-and-tnp-fixes/)
- Onshape FeatureScript runs inside the geometry engine; no source found for its persistent ID scheme. — [Onshape blog](https://www.onshape.com/en/blog/cloud-native-architecture-empowers-cad-pdm)

### Inferences
- [background] A workable design: each feature records, via BRepTools_History / BRepBuilderAPI_MakeShape::Modified/Generated/IsDeleted, a map from input sub-shapes to outputs; references store (feature id, generation role, index) plus a geometric signature (surface type, area, centroid, normal) as a fallback; show the user a repair dialog when ambiguous. Unverified here.

### Gaps
- No primary realthunder/ickby write-ups, academic papers, or Onshape ID details retrieved.

## 6. Constraint solver

### Takeaway
Little retrieved. PlaneGCS (FreeCAD) offers BFGS, LM and DogLeg; libslvs is GPLv3; D-Cubed is the commercial standard.

### Cited Findings
- A 2023 Tehnicki Vjesnik paper studies PlaneGCS's BFGS, LM, Dogleg, and a DFP addition, comparing solving state, time and iterations. — [Tehnicki Vjesnik](https://hrcak.srce.hr/309254)
- libslvs is SolveSpace's solver library; SolveSpace is GPLv3. — [ALT Linux package](https://packages.altlinux.org/en/sisyphus_e2k/srpms/solvespace/)
- D-Cubed is owned by Siemens and licensed (Onshape uses it). — [Onshape blog](https://www.onshape.com/en/blog/cloud-native-architecture-empowers-cad-pdm)

### Inferences
- GPL solvers (libslvs) conflict with a closed product; PlaneGCS is LGPL [background, unverified]. Writing an own solver on Eigen with graph decomposition and DOF analysis is feasible but needs diagnostics work.

### Gaps
- No benchmarks on large sketches, drag stability, redundancy diagnostics.

## 7. Performance architecture, file formats, rendering

### Takeaway
Only the Onshape split architecture (server-side kernel, tessellation to client) and OCCT meshing parallelism were sourced; the rest is unresearched.

### Cited Findings
- See sections 2 and 4 for Onshape server architecture and BRepMesh threading.

### Inferences
- [background] Keep kernel calls in worker processes (avoids the GIL and isolates kernel crashes), cache tessellation per shape hash, use instancing for repeated parts, and store features as a text/JSON op log in a zip with B-Rep cache for crash recovery. Unverified.

### Gaps
- No sources for FreeCAD/Plasticity architectures, file formats, undo/redo, STEP AP242, Filament/Cycles/Embree rendering costs.

## 8. Simulation/CAM building blocks and licences

### Takeaway
Gmsh is GPL; OpenCAMLib is LGPL (since Aug 2018). CalculiX, GRBL/LinuxCNC licences not verified.

### Cited Findings
- Gmsh is GPL v2+ with a linking exception; historically a commercial licence was offered. — [Gmsh](https://www.gmsh.info), [mailing list](https://onelab.info/pipermail/gmsh/2015/009902.html)
- OpenCAMLib relicensed to LGPL in Aug 2018 (Debian lists LGPL-2.1+) to resolve incompatibility with FreeCAD. — [Debian README](https://metadata.ftp-master.debian.org/changelogs/main/o/opencamlib/stable_README.Debian), [copyright](https://metadata.ftp-master.debian.org/changelogs/main/o/opencamlib/stable_copyright)

### Inferences
- Run GPL tools (Gmsh, CalculiX) as separate processes rather than linking if the product is closed; get legal review.

### Gaps
- CalculiX/FEniCS licences, FreeCAD Path, Libarea, GRBL/LinuxCNC post-processors not covered.
- Sheet metal, thread and HLR capabilities in OCCT: no sources found.
