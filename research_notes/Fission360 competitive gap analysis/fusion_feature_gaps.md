# Autodesk Fusion (360) feature inventory vs Fission360 gaps (2026)

NOTE ON SOURCING: WebFetch was blocked in this environment (DNS failures), so only search-result snippets were usable. Cited findings are limited to what snippets confirmed. The detailed per-command inventory in the Inferences sections comes from analyst/training knowledge of Fusion (pre-2026 baseline), NOT verified this session. Treat it as "probable, verify against help.autodesk.com". Ratings: Importance H/M/L for Hobbyist(Hb) / Startup product designer(SU) / Small machine shop(MS). Difficulty on OpenCASCADE (OCCT): 1 trivial ... 5 research-grade.

## Q1. Design-workspace modelling commands Fission360 lacks, ranked

### Takeaway
Confirmed Create-menu solid tools include Rib, Web, Emboss, Hole, Thread, Boundary Fill. Highest-value missing commands are Text (sketch + emboss/extrude), Thread, Rib/Web, Offset Face, Variable-radius/Rule/Full-round fillets, Thicken, Sketch offset/mirror/pattern/ellipse/conic, and 3D sketch. Most are medium difficulty on OCCT.

### Cited Findings
- Rib and Web build thin features from an open sketch profile extruded to the nearest solid faces; Rib extrudes parallel to the sketch plane, Web perpendicular to it. — [Autodesk Web blog](https://www.autodesk.com/products/fusion-360/blog/fusion-360-in-depth-web-command/)
- Emboss raises or recesses a sketch profile relative to faces on a solid by a depth and direction. — [Autodesk help: Solids from sketches](https://help.autodesk.com/cloudhelp/ENU/Fusion-Model/files/SLD-CREATE-SOLID-FROM-SKETCH.htm)
- Thread is under the Create menu; threads default to Cosmetic and can be switched to Modeled in Document Settings. — [Autodesk Threading tech tip](https://www.autodesk.com/products/fusion-360/blog/tech-tip-threading-parts-in-fusion-360/)
- Design > Solid > Create lists Rib, Web, Emboss, Hole, Thread, Boundary Fill among its tools. — [Autodesk help](https://help.autodesk.com/cloudhelp/ENU/Fusion-Model/files/SLD-CREATE-SOLID-FROM-SKETCH.htm)
- July 2026 update added a hub-based Threads Library and Construction Geometry enhancements; Jan 2026 update headlined "Intent Driven Design"; April 2026 added Autodesk Assistant (natural-language to commands). — [Autodesk July 2026](https://www.autodesk.com/products/fusion-360/blog/july-2026-major-product-update-whats-new/), [Jan 2026](https://www.autodesk.com/products/fusion-360/blog/january-2026-product-update-whats-new/), [April 2026](https://www.autodesk.com/products/fusion-360/blog/april-2026-product-update-whats-new/)
- September 2026 major update (v2705.1.11, Sept 3 2026) cites faster performance, more predictable modeling (more consistent lofts between closed profiles), expanded sheet metal and PMI workflows, Scene Lights. — [Autodesk Sept 2026](https://www.autodesk.com/products/fusion-360/blog/september-2026-major-product-update-whats-new/)
- User reviews cite slowness/freezing, learning curve, and weak organic/freeform vs mechanical focus. — [Capterra](https://capterra.com/p/178416/Fusion-360/reviews/)

### Inferences (analyst knowledge, unverified this session)
Ranked gap list (Hb/SU/MS importance; OCCT difficulty):
1. Text (sketch text, then extrude/emboss/cut; fonts): H/H/M; 2 (Font_BRepTextBuilder exists). Also on-face engraving.
2. Thread (cosmetic + modeled; ISO/UNC tables; tap-drill link to Hole): H/H/H; 3 cosmetic=metadata easy, modeled helix sweep+boolean fragile. Cosmetic-first MVP.
3. Sketch tools: offset, mirror, rectangular/circular pattern, ellipse, conic, equation/fit-point curves, slot variants, sketch on any face/offset plane, 3D sketch: H/H/H; 2-3 (offset via BRepOffsetAPI_MakeOffset; 3D sketch needs 3D constraints, 4).
4. Fillet variants: variable radius, full round, rule fillet, setback/G2 continuity, face-edge-chain options: H/H/M; 3 (BRepFilletAPI_MakeFillet supports variable radius; full round and G2 harder).
5. Offset Face / Press-Pull / Move Face / Delete Face / Replace Face / Split Face (direct-edit set): H/H/M; 3-4 (BRepOffsetAPI_MakeOffsetShape, BRepAlgoAPI, ShapeUpgrade; healing after delete face is the hard part).
6. Rib / Web: M/H/M; 3 (derive from extrude-to-body + draft). Lip/Boss/Snap-fit plastics are Design Extension (see Q4).
7. Thicken, Patch, Stitch, Unstitch, Offset surface, Extend, Trim/Untrim surface, Boundary Fill (cells from tools): M/H/M; Stitch/Thicken/Offset 2-3, Patch/Boundary Fill 3, Trim/Untrim 3.
8. Emboss and Decal: M/M/L; 3 (project + offset body) / decal is rendering only.
9. Project to Surface, Wrap onto face: M/M/L; 4.
10. Pipe (path+section), Plane-along-path, Plane-at-angle, Midplane, Tangent plane, Offset curve on surface: M/M/L; 2.
11. Mirror/pattern along path, Pattern on path/curve: M/M/M; 2 (Fission has patterns, extend).
12. Insert: Insert Mesh, Insert SVG, Insert DXF, Decal, Canvas (image reference), Attached canvas: Canvas+SVG+DXF H/H/H; 1-2 (DXF/SVG are very commonly requested by makers/shops).
13. Select menu: window/paint/tangent chain/ selection filters, Select Through: M; 1-2.
14. Inspect: Interference done; missing Curvature Comb, Zebra Analysis, Draft Analysis, Curvature Map Analysis, Isocurve, Accessibility, Section done, Center of mass display, Component Color Cycling: Zebra/Draft/Curvature M/H/L; 2 (shader/ OCCT curvature queries).
15. Modify: Combine/Move done; missing Remove, Replace Face, Physical Material/Appearance assignment, Compute All, Change Parameters (done as params), Align, Delete, Attribute assignment: M; 1-3.
16. Parameters: Fission has user params; missing Favorites, model parameter visibility, configurations (table-driven variants, H/H/M for SU/MS; 4).
17. Sketch: Fit-point & control-point spline done; missing Tangent/Fit Spline curvature display, Offset, Mirror, Circular/Rect pattern, Scale, Break, Extend, Stretch, Sketch Dimensions on arcs/ordinate, Insert text, Fix/Unfix, Intersection curve, Intersect, Project-to-surface, Sketch palette show/hide, Look at, Slice. Importance: Offset/Mirror/Pattern/Extend/Break/Stretch H/H/H; 2.
Top three highest ROI by (importance)/(difficulty): Text, sketch offset/mirror/pattern, Canvas/SVG/DXF insert, variable-radius/full-round fillet, cosmetic thread.

### Gaps
- No page fetched confirming the full 2026 Create/Modify/Construct/Inspect menu contents or exact Rule Fillet semantics; the list above is not source-verified.
- Frequency data (command usage telemetry) is not public; "importance" is judgement from forum/review themes, not measurements.

## Q2. Assemblies in Fusion

### Takeaway
Fusion's model: one document can contain a component tree; bodies are raw solids, components are the unit of assembly and carry their own origin, sketches, timeline-linked features, joints and appearances. Joints (not mates) define relationship and motion, with Joint Origin and As-built Joint. Minimum viable version: components + tree + rigid/revolute/slider/cylindrical/pin-slot/planar/ball joints with limits, ground, and drag-to-test.

### Cited Findings
- As-Built Joint joins components already positioned relative to each other; Rigid motion locks them. — [Autodesk help: As-built joint](https://help.autodesk.com/cloudhelp/ENU/Fusion-Assemble/files/ASM-CREATE-AS-BUILT-JOINT.htm)
- A Rigid Group makes selected components move as one unit with no extra joints; selecting a top-level component can include all children. — [Autodesk blog: Joints vs Mates](https://www.autodesk.com/products/fusion-360/blog/joints-mates-moving-fusion/)
- Rigid groups and as-built rigid joints differ from standard rigid joints (behavior when joined component changes shape); a forum post asks for a tool that auto-creates rigid joints at contact faces, suggesting "contact sets" in the sense of an auto-rigid-contact tool is NOT an existing feature. — [Autodesk Idea Station thread](https://forums.autodesk.com/t5/fusion-360-ideastation-archived/add-many-standard-rigid-joints-at-once-not-the-same-as-quot/idi-p/7143859)
- Autodesk positions Fusion assembly via "Joints vs. Mates" - joints combine position and motion definition. — [Autodesk blog](https://www.autodesk.com/products/fusion-360/blog/joints-mates-moving-fusion/)

### Inferences (analyst knowledge, unverified)
- Fusion joint types: Rigid, Revolute, Slider, Cylindrical, Pin-Slot, Planar, Ball; Joint Origin (snaps to vertex/edge midpoint/face center, offset+angle), Joint Limits (min/max/rest), Drive Joints, Motion Link (gear/rack relationships), Motion Study (Animation workspace / Motion Contact), Contact Sets (Enable Contact Sets / Enable All Contact: collision detection while driving joints), Enable Contact, Interference done in Fission. Ground (fixed) component, Align, Move/Copy of components, Component from bodies, Insert into Current Design, Linked/external references (Insert > Insert into current design links a cloud design; updates by version), Capture Position, Assembly Constraints are not mates (no distance/angle mates; joints cover). Fusion also has BOM table export, Exploded View (Animation), Assemble > Joint, Rigid Group, Drive Joints, Joint Origin, Joint Limits, Joint Between Bodies, Contact Sets.
- Importance: Components+joints H for SU/MS/Hb (multi-part products, enclosures, fixtures); external references M/H/M (team workflows); motion study/contact sets M/M/L; exploded views M/H/M (documentation); BOM M/H/H.
- Difficulty on OCCT: components as TopLoc_Location/ XCAF (XDE) assembly tree 2-3 (OCCT XCAF handles STEP assembly/colors); joint solver is NOT in OCCT: must build a small kinematic constraint solver (3-4). Contact/collision driven motion: use BRepExtrema/ BRepAlgoAPI_Common or mesh collision, 3-4. External references/versioning need backend, 4-5.
- MVP: (1) component tree with per-component location and own body list, (2) STEP/XCAF assembly import/export preserving structure, (3) 4-5 joint types + limits + ground + drag animation, (4) as-built joint (joint from current pose), (5) rigid group, (6) BOM/exploded later.

### Gaps
- Official docs for contact sets, motion links, joint limits were not retrieved (fetch blocked); the claims above are from training knowledge.
- External-reference (linked design) update semantics not verified.

## Q3. Other workspaces: headline capabilities and who uses them

### Takeaway
Most-used by hobbyist/prosumer: Design (parametric solids), Manufacture (CAM, especially 2.5D/3-axis and 3D printing prep), Drawing (2D), Render, and Sheet Metal in lesser degree. Simulation, Generate, Electronics, Plastic are minority features.

### Cited Findings
- Fusion subscription covers design, simulation, collaboration and manufacturing, with advanced features (generative design, advanced simulation, rendering) via cloud compute paid with cloud credits. — [Autodesk news, adsknews](https://adsknews.autodesk.com/en/?p=5144)
- Simulation Extension adds nonlinear static stress, structural buckling, modal frequencies, thermal stress, event simulation, injection moulding simulation, with unlimited cloud solving. — [Autodesk Simulation Extension page](https://www.autodesk.com/in/products/fusion-360/simulation-extension)
- Manufacturing Extension adds 4/5-axis simultaneous machining, sheet-based nesting and fabrication, metals additive; probing: WCS probing is in core, Geometry Probing / Surface Inspection / Part Alignment need the extension; nesting is associative and multi-sheet. — [Autodesk Manufacturing Extension](https://www.autodesk.com/products/fusion-360/manufacturing-extension.html), [Autodesk blog](https://www.autodesk.com/products/fusion-360/blog/fusion-360-machining-extension-beyond-5-axis-machining/)
- Design Extension (formerly Product Design Extension): material-driven design rules (wall thickness, draft, fillet radius), plastic features (bosses, snap features, ribs/webs), geometric patterning across flat/curved surfaces, volumetric lattice on solids or meshes. — [Autodesk Design Extension](https://www.autodesk.com/products/fusion-360/design-extension.html), [Develop3D](https://develop3d.com/cad/new-product-design-extension-added-to-fusion-360/)
- Full-access trial lists four extensions: Manufacturing, Simulation, Design, Signal Integrity. — [Autodesk trial page](https://www.autodesk.com/campaigns/fusion-360/new-trial-download)
- 2026 updates include Altium Project Import, expanded PMI and sheet metal, Fusion Manage BOM cost roll-ups, OPC UA connector for machine data. — [Autodesk July](https://www.autodesk.com/products/fusion-360/blog/july-2026-major-product-update-whats-new/), [Sept](https://www.autodesk.com/products/fusion-360/blog/september-2026-major-product-update-whats-new/), [Release notes](https://help.autodesk.com/cloudhelp/ENU/Fusion-ReleaseNotes/files/FIC-REL-NOTES-INC.htm)
- Reviewers credit integrated CAD/CAM/sim, cloud storage/version control, parametric+direct modeling; criticise performance and organic modeling. — [Capterra](https://capterra.com/p/178416/Fusion-360/reviews/), [Gartner](https://www.gartner.com/reviews/product/fusion-360)

### Inferences (analyst knowledge, unverified)
Per workspace (usage among Hb / SU / MS; OCCT difficulty):
- Surface (Loft, Patch, Trim, Extend, Stitch, Thicken, Ruled, Offset curve network, Sculpt-less): M/H/L; 3. OCCT has solid surface ops; class-A quality and continuity control (G2/G3) is weak.
- Form/T-Spline (Sculpt): M/M/L; 5 (no OCCT equivalent; T-spline is Autodesk-patented; the nearest open options are subdivision surface + conversion to NURBS, very hard).
- Mesh (Insert Mesh, Mesh Repair, Reduce, Remesh, Convert Mesh to BRep, Mesh Section, Shell): M/M/M; 3-4 (conversion to BRep is the hard part; repair/reduce is doable with libraries e.g. CGAL/ OpenMesh).
- Sheet Metal (Flange, Bend, Unfold/Refold, Flat Pattern, Rules/ Sheet Metal Rules table, Corner relief, Hem, DXF export): L/H/H; 4 (no native OCCT sheet metal; needs K-factor unfold model; flat pattern DXF is the key output).
- Plastic (Boss, Rib, Web, Snap fit, Lip/groove, Rest): M/H/L; 2-3 on top of core features.
- Drawing (2D views, section, detail, dimensions, BOM/balloons, title blocks, PDF/DWG export): M/H/H; 3-4 (OCCT HLR via HLRBRep_Algo; dimensioning and annotation UI is the work).
- Render (cloud/local raytrace, appearances, environment, decals, turntable): H(Hb)/M/L; 3 (use a path tracer such as Cycles or three-gpu-pathtracer rather than building one).
- Animation (exploded views, explode stories, camera): M/H/L; 2-3.
- Simulation (static stress, modal, thermal, buckling, nonlinear, shape optimization, event): L/M/M; 4 (meshing via Gmsh/netgen + CalculiX/FEniCS pipeline; static stress linear is the realistic MVP).
- Generate (generative design with Autodesk cloud solver, topology optimization): L/M/L; 5 (cloud-credit feature; open alternatives exist but UX is hard).
- Manufacture (Setup, 2D Adaptive/Pocket/Contour/Face/Drill/Bore/Thread, 3D Adaptive/Pocket Clearing/Parallel/Scallop/Contour, 4/5 axis, turning, probing, jet cutting, additive FFF, post processors, simulate, stock & fixtures, tool libraries, Cloud tool library, Feature recognition, Nesting): H(Hb with CNC routers/mills)/M/H; 4-5 in total (2.5D toolpaths 3-4; 3D adaptive 4; 5-axis 5; post processors are a big job - reuse Autodesk's open post processors?). OCCT gives geometry (offsets, slicing) but not toolpath algorithms. Libraries: OpenCAMLib, libarea, ClipperLib.
- 3D print / Utilities (Make > 3D Print: Print utility, send to slicer, supports, orient; Prusa/Bambu/Cura export, 3MF): H(Hb)/H/L; 1-2. Ships 3MF export - very cheap and high value.
- Electronics (EAGLE-derived schematic/PCB, library, autorouter, 3D PCB sync, Altium import in 2026): M/M/L; 5 (separate product-class). Skip; support STEP export for PCB bodies and ECAD-MCAD via IDF/STEP only.
- Utilities: Add-Ins (Python/C++ API), Scripts, Manage (parameters), Inspect, Make (3D Print, Drawing Export), Product Design.

### Gaps
- Per-workspace actual-user share data is not published; no source retrieved for percentage usage.
- Sept 2026 sheet-metal and PMI specifics not retrieved (search snippets only).

## Q4. Included versus paid (cloud/extension)

### Takeaway
Core subscription includes parametric design, sheet metal, surface, mesh, drawing, basic 2.5/3-axis CAM, basic linear stress simulation, render, electronics; extensions (Manufacturing, Simulation, Design, Signal Integrity, plus Fusion Manage/Machine) gate 4/5-axis, nesting, additive metals, advanced probing, advanced simulation types, plastic features, lattice, and some generative/cloud credit features. Personal-use license is non-commercial with feature trims.

### Cited Findings
- Extensions are add-ons priced monthly/annually and require an existing Fusion subscription; Design Extension functionality is also included in "Autodesk Fusion for Design" bundle alongside Simulation Extension and Fusion Manage. — [Autodesk Design Extension](https://www.autodesk.com/products/fusion-360/design-extension.html)
- Simulation Extension: advanced study types plus unlimited cloud solving. — [Autodesk](https://www.autodesk.com/in/products/fusion-360/simulation-extension)
- Manufacturing Extension: 4/5-axis, nesting, metal additive, advanced probing. — [Autodesk](https://www.autodesk.com/products/fusion-360/manufacturing-extension.html)
- Advanced features (generative design, advanced simulation, rendering) via cloud compute use cloud credits. — [Autodesk news](https://adsknews.autodesk.com/en/?p=5144)
- Autodesk's 2024 blog: hobbyist license is non-commercial only and excludes collaboration, data management, and commercial translators (NX, Catia, SolidWorks, Creo, Inventor); third-party sources report an income cap (~$1,000/yr), 10 active documents, and removal of advanced CAM toolpaths/cloud sim/generative design (unverified dates). — [Autodesk blog 2024](https://www.autodesk.com/products/fusion-360/blog/?p=11774), [Stacksheriff](https://stacksheriff.com/3d-printing/fusion-360-free-personal-license/?format=md)
- STEP export was proposed for removal from personal use, then retained. — [Fabbaloo](https://www.fabbaloo.com/?p=194461)

### Inferences
- Implication for Fission360: an open, free-for-commercial parametric tool can undercut by offering what Autodesk fences (commercial use, many documents, translators, 4-axis-lite CAM).
- Exact current prices were not retrievable (price templates unfilled); do not quote any.

### Gaps
- Current US pricing for each extension and the 2026 contents of the "Fusion for Design" bundle not confirmed.
- Exact 2026 hobbyist license limits (doc cap, income cap) need Autodesk's current page.

## Q5. Moat versus commodity

### Takeaway
Commodity (replicable on OCCT in weeks to months): sketch/solid feature set, fillet/chamfer variants, text, threads (cosmetic), patterns, STEP/IGES IO, measure, rendering via off-the-shelf path tracer, 3MF/print export, basic joints. Moat (hard or non-technical): integrated cloud data/versioning/hubs (Fusion Team, Manage), CAM depth and post library with tool libraries and cloud-sold simulation, T-spline modeling, generative/cloud solvers, robust 3D-parametric kernel (ASM, not OCCT: fewer fillet/boolean failures), EAGLE/Altium ecosystem, add-in ecosystem/API, education distribution, and brand/trust.

### Cited Findings
- Reviewers repeatedly cite the all-in-one CAD+CAM+simulation integration and cloud storage/version control as the main value. — [Capterra](https://capterra.com/p/178416/Fusion-360/reviews/), [Gartner](https://www.gartner.com/reviews/product/fusion-360)
- Autodesk is investing in AI-assisted modeling (Autodesk Assistant, Intent Driven Design) in 2026. — [April 2026](https://www.autodesk.com/products/fusion-360/blog/april-2026-product-update-whats-new/), [Jan 2026](https://www.autodesk.com/products/fusion-360/blog/january-2026-product-update-whats-new/)
- Fusion integrates Altium project import (July 2026), strengthening ECAD-MCAD. — [Autodesk July 2026](https://www.autodesk.com/products/fusion-360/blog/july-2026-major-product-update-whats-new/)
- Reviews report slow performance and weaker organic modeling, i.e. areas where a lean OCCT tool can compete. — [Capterra](https://capterra.com/p/178416/Fusion-360/reviews/)

### Inferences
- Priority for Fission360 (value per effort): (1) sketch/fillet/text/thread completeness, (2) components + joints MVP + assembly STEP, (3) 2D drawings + DXF flat export, (4) 3MF + slicer handoff, (5) scripting API (Python) for community, (6) sheet metal unfold, (7) basic CAM 2.5D (large effort, large shop value), (8) FEA linear static via Gmsh+CalculiX. Defer T-spline, generative, electronics, cloud collab (use git-like versioning of file-based documents as lightweight alternative).
- Stability/robustness of fillets and booleans on OCCT is itself a competitive risk; invest in ShapeFix and failure messaging.

### Gaps
- No independent source quantifying kernel robustness differences (ASM vs OCCT); this is analyst opinion.
- No authoritative market-share/usage data for hobbyist vs pro segments.
