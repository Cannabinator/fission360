# Open-source / code-first CAD competitors to Fusion 360 (state as of Oct 2026)

Research caveat: WebFetch could not reach most hosts (wiki.freecad.org, docs.dune3d.org, hackster, alternativeto), so findings rest on search-result summaries. Items marked "background knowledge, unsourced" are NOT cited and should be verified before use in the final report.

## FreeCAD: what changed in 1.0 (Nov 2024) and 1.1 (Mar 2026); toponaming; Assembly; funding; Fusion-killer gaps

### Takeaway
FreeCAD 1.0 (18 Nov 2024) made the topological-naming mitigation and a new integrated Assembly workbench its headline; 1.1 (24/25 Mar 2026, 1.1.1 on 15 Apr 2026) is a UX-focused release (previews, draggers, any-workbench datums, Clarify Selection). Toponaming is "mostly" but not fully fixed, and FreeCAD's remaining gap versus Fusion is workflow consistency and polish rather than raw features. Funding is small (about EUR 130k/yr donations).

### Cited Findings
- FreeCAD 1.0 released 18 Nov 2024; toponaming was the main goal — [Search summary of Hackster/LinuxFR coverage](https://hackster.io/news/freecad-hits-1-0-after-two-decades-finally-sees-an-end-to-the-toponaming-problem-7e7ac2df3e63)
- Toponaming described as "mostly gone", still possible to hit issues; maintainers said "not completely solved", fix applied only to Sketcher and PartDesign — [pixls.us write-up](https://discuss.pixls.us/t/freecad-1-0-new-features-and-the-larger-picture/46690); [Hackster](https://hackster.io/news/freecad-hits-1-0-after-two-decades-finally-sees-an-end-to-the-toponaming-problem-7e7ac2df3e63)
- 1.0 Assembly workbench written by the Ondsel team; bottom-up (parts inserted as links, one grounded, rest joined); uses the Ondsel solver — [pixls.us](https://discuss.pixls.us/t/freecad-1-0-new-features-and-the-larger-picture/46690); [Hackaday](https://hackaday.com/blog/page/780/?cat=LDR)
- FreeCAD 1.1: datums/coordinate systems/planes/lines/points usable in any workbench, not only Part Design — [AlternativeTo news via search](https://alternativeto.net/news/2026/3/freecad-1-1-adds-three-point-lighting-part-design-previews-and-major-fem-upgrades)
- 1.1: overhauled Transform tool; three-point lighting; transparent previews of additive/subtractive PartDesign features; interactive 3D draggers for feature values; Clarify Selection tool (temporarily transparent neighbours + list of pickable elements) — same source
- 1.1: FEM multi-frame result visualisation, custom fields via filters, electrostatics and current-conduction solvers; CAM uses "Better Tool Library" — same source
- Release dates: 1.1 on 24 Mar 2026 per wiki (another article says 25 Mar); 1.1.1 maintenance release 15 Apr 2026 — [FreeCAD blog 1.1.1](https://blog.freecad.org/2026/04/15/freecad-1-1-1-released/); [OSArch](https://osarch.org/2026/03/25/freecad-1-1-released/)
- FPA 2025: donations EUR 129,981 vs spend EUR 127,094; income only donations, mostly individuals; monthly maintainer allowance and bug bounty launched; talks with OpenCascade team about a paid position; 2026 budget EUR 230k drawn partly from reserves; report acknowledges 2025 community turmoil incl. developers leaving — [FPA 2025 report](https://fpa.freecad.org/annualreports/2026.html); [blog](https://blog.freecad.org/2026/04/24/2025-annual-report-and-plans-for-2026/)
- 2024 comparison: ~EUR 186k donations, ~EUR 99k expenses — [FPA 2024 report](https://fpa.freecad.org/annualreports/2025.html)
- User complaints (forum/Lemmy anecdotes, dated 2023-2024, low weight): disjointed workflow across workbenches, missing quality-of-life features (chamfer past edge, text wrapped on cylinder), missing common shortcuts, one user left for SolidWorks — [Lemmy/Reddit mirror sample](https://feddit.it/post/3978460/4353488); [woodworker.de thread](https://www.woodworker.de/forum/goto/post?id=1186803)
- G2 user-review summary rates Fusion higher overall and support better; FreeCAD praised for drawings and large models — [G2](https://www.g2.com/compare/autodesk-fusion-vs-freecad)

### Inferences
- Pattern in 1.1 (previews, draggers, any-workbench datums) shows FreeCAD is paying down the "modal / workbench-silo" UX debt incrementally; Fission360 should start with unified datums and live feature previews rather than retrofit.
- Dev turnover plus ~EUR 130k/yr budget implies slow throughput on deep architectural rewrites; a funded, focused product can out-iterate on UX.
- Toponaming fix being scoped to Sketcher + PartDesign means cross-workbench references (Part, Assembly, Draft) remain fragile; Fission360 should make persistent entity IDs (history-based naming with fallback matching) a core document-model service from day one.

### Gaps
- Could not open official 1.0/1.1 release notes: no verified detail on Qt6/OCCT versions, Sketcher/TechDraw/Path-CAM changes in 1.0, or Assembly 1.1 changes.
- No 2025-26 sourced user data on crash/stability or on the "Fusion killer" wish list beyond the anecdotes above (background knowledge, unsourced: commonly cited wants are a single unified workflow, robust assembly with motion, sheet-metal, better sketch/constraint UX, performance, cloud/collab).
- Learning curve, workbench model critique, TechDraw/Path details: not retrieved.

## SolveSpace and libslvs

### Takeaway
SolveSpace is a small GPL-3 parametric CAD whose constraint solver is packaged as a reusable library (libslvs) and python module; development is slow (last stable 3.1, 1 Jun 2022) but its solver is the de facto reusable component (Dune3D, Blender CAD Sketcher).

### Cited Findings
- Stable 3.1 dated 1 Jun 2022; GPL-3.0-or-later; 3.1 notes performance improvements and STL linking — [SolveSpace download page](https://solvespace.com/download.pl); [Wikipedia](https://en.wikipedia.org/wiki/SolveSpace)
- libslvs ships as library in Debian/Ubuntu (3.1+ds1) — [Ubuntu Launchpad](https://code.launchpad.net/ubuntu/+source/solvespace/3.1+ds1-3.1build2)
- Wikipedia notes limitations on ordering of Boolean operations as of 3.0 — [Wikipedia](https://en.wikipedia.org/wiki/SolveSpace)
- Blender add-on CAD Sketcher depends on the solvespace Python module; self-described experimental — [CAD Sketcher repo](https://github.com/VDBStudio/CAD_Sketcher)
- Dune3D = SolveSpace solver/workflow + OpenCASCADE + Horizon EDA UI — [Dune3D docs via search](https://docs.dune3d.org/en/latest/why-another-3d-cad.html)

### Inferences
- Reuse path: libslvs (GPL-3) is embeddable but GPL is a licensing constraint for a closed or non-GPL Fission360; check Fission360's licence before linking. FreeCAD's PlaneGCS is LGPL (background knowledge, unsourced) and is the licence-friendlier 2D option.

### Gaps
- No sourced statement on why users love the solver (background knowledge, unsourced: fast, robust, handles 3D constraints, under/over-constrained diagnostics with DOF count), nor on solver limits (e.g. no NURBS-surface constraints).
- Repo activity/commit cadence not retrieved.

## CadQuery / build123d / viewers (CQ-editor, ocp-vscode)

### Takeaway
Both are Python on OCCT (via OCP). build123d is positioned as the evolution of CadQuery (context managers / algebra mode instead of fluent chaining; Apache-2.0 vs CadQuery's LGPL-ish/GPL claim in source, see conflict) and is described in its docs as the most supported code-CAD framework. A Python scripting layer is a proven, cheap-to-adopt differentiator.

### Cited Findings
- build123d described as evolution of CadQuery replacing fluent API with stateful context managers; build123d Apache-2.0; CadQuery stated as GPL-3.0-or-later by one aggregator (conflicting with CadQuery's actual licence being Apache-2.0 per background knowledge; verify) — [search summary of build123d docs](https://build123d.readthedocs.io/_/downloads/en/latest/epub/)
- Ecosystem: ocp-vscode viewer, cq-editor (PyQt) and a build123d-friendly fork, Yet Another CAD Viewer (web) — [build123d external tools](https://build123d.readthedocs.io/en/latest/external.html); [vscode-ocp-cad-viewer](https://github.com/bernhard-42/vscode-ocp-cad-viewer)
- HN user journey OpenSCAD -> CadQuery -> build123d: OpenSCAD simple but hard to scale, CadQuery hard to reason about due to state tracking, build123d preferred for explicit algebra mode and interactive visualiser; but code is more bloated than OpenSCAD — [HN comments by wiw2](https://news.ycombinator.com/threads?id=wiw2)
- Star counts disagree across sources (CadQuery ~5.2k vs build123d ~2.6k in a Sep 2026 article); not comparable — [libhunt](https://www.libhunt.com/compare-cadquery-vs-SolidPython); [Brightcoding](https://blog.brightcoding.dev/2026/09/21/gumyrbuild123d-pythonic-cad-for-parametric-3d-modeling)
- Both export STEP; used in 2026 AI/agentic CAD benchmarks — HN thread above

### Inferences
- Fission360's Python API should expose the document model so a script can create features that also appear in the GUI timeline (the thing CadQuery/build123d lack: a GUI/history). Mirror build123d's explicit-algebra style (immutable shapes, operators) rather than fluent chaining.
- Code-CAD is also the natural LLM interface; an agent-friendly API is cheap leverage.

### Gaps
- Release cadence, issue activity, and CadQuery's real licence not verified.

## Dune3D, Plasticity, Blender add-ons, other open projects

### Takeaway
Dune3D proves a small team can ship a SolveSpace-style parametric modeler on OCCT with strong UI polish; Plasticity shows direct-modelling/artist UX sells commercially; Fornjot is dead; OpenSCAD got a major speed-up from Manifold.

### Cited Findings
- Dune3D author left FreeCAD citing toponaming and a modal 2D-only sketcher with no 3D constraints — [Hackaday](https://hackaday.com/tag/dune3d/)
- Dune3D 1.3.0: bitmap import, pipe groups, mirror groups, curvature combs, constraint preview; STEP import for reference, STEP/STL export; GPL-3.0 — [Flathub listing](https://flathub.org/az/apps/org.dune3d.dune3d)
- Dune3D 1.4.0 (timed for FOSDEM, ~Jan/Feb 2026): DXF export, improved constraining workflow, navigation cube — [relayed announcement](https://hackers.pub/@karotte@chaos.social/019c0705-34a1-763a-8db3-6968b8ed6ae3/shares)
- Plasticity: commercial, Parasolid kernel (moved from C3D), perpetual licence, Indie USD 175 / Studio USD 299 with 12 months of updates, UI modelled on Blender's polygon modeller, direct NURBS editing for artists; no longer open source — [Plasticity buy page](https://www.plasticity.xyz/buy); [Wikipedia](https://en.wikipedia.org/wiki/Plasticity_(software)); [Digital Production](https://digitalproduction.com/2023/10/04/plasticity-3d-cad-for-artists/)
- CAD Sketcher (Blender): SolveSpace-based constraint sketcher, extrude to solids, non-destructive; Blender's mesh basis limits mechanical use — [repo](https://github.com/VDBStudio/CAD_Sketcher); [Blender Artists](https://blenderartists.org/t/geometry-sketcher-constraint-solver/1328479/)
- Fornjot (Rust kernel/CAD) archived 19 Jun 2026; goals never reached; last crate 0.49.0 Mar 2024 — [GitHub](https://github.com/hannobraun/fornjot)
- OpenSCAD: Manifold backend became default in dev snapshots 17 Aug 2025; one user saw 51 s vs 12.5 min vs CGAL — [OpenSCAD Mastodon](https://fosstodon.org/@OpenSCAD/113256867413539398); [openscad list](https://lists.openscad.org/empathy/thread/TMJEJCZINIJNYJX2YF7IDNBAPQY66KIF)

### Inferences
- Highest delight per cost (from the above): live feature preview and on-canvas draggers (FreeCAD 1.1), Clarify-Selection style disambiguation, constraint preview and DOF feedback (Dune3D), navigation cube, curvature combs, 3D constraints in the sketcher, unified datums available everywhere.
- Lesson from Fornjot: building a B-rep kernel from scratch is a multi-year trap; build on OCCT (or Truck) and invest in UX/document model.
- Lesson from OpenSCAD: mesh-only CSG tops out; Manifold shows modern mesh booleans are fast, relevant for a mesh fallback/preview path.

### Gaps
- Truck, ImplicitCAD: not found (no sourced status). Dune3D community size, release cadence beyond 1.3/1.4, Plasticity reviews 2025-26, HN/Reddit sentiment: not retrieved.

## Architectural decisions that caused long-term pain; reusable components

### Takeaway
Evidence supports: FreeCAD's workbench/modal model and name-based references produced toponaming and fragmented workflows; Dune3D's author explicitly left over those. Reusable pieces are licence-dependent.

### Cited Findings
- Fix of toponaming limited to Sketcher/PartDesign (see FreeCAD section); 1.1 releasing datums for all workbenches indicates earlier siloing — [AlternativeTo via search](https://alternativeto.net/news/2026/3/freecad-1-1-adds-three-point-lighting-part-design-previews-and-major-fem-upgrades)
- Assembly bolted on late via Ondsel team with own solver — [pixls.us](https://discuss.pixls.us/t/freecad-1-0-new-features-and-the-larger-picture/46690)
- SolveSpace solver reused by Dune3D and CAD Sketcher (GPL-3) — sources above
- build123d Apache-2.0 (permissive) — [build123d docs](https://build123d.readthedocs.io/_/downloads/en/latest/epub/)

### Inferences
- Avoid: separate Part vs Part Design object models, mode-switching workbenches, string-based topological names, and a late-added assembly solver separate from the sketch solver. Prefer one document model, one constraint-solver service (2D+3D), persistent entity IDs, Python API on the same model.
- Reuse candidates (verify licences): libslvs (GPL-3), PlaneGCS (background knowledge: LGPL, unsourced), OCCT (LGPL-2.1 with exception, background knowledge), build123d/OCP patterns (Apache-2.0), ezdxf (MIT, background knowledge, unsourced), Manifold (Apache-2.0, background knowledge).

### Gaps
- No sourced licence verification for PlaneGCS, ezdxf, OCCT, Manifold; no sourced analysis of Part vs PartDesign pain; verify before reporting.
