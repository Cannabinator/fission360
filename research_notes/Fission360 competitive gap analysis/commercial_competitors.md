# Commercial CAD Competitors and Reference Products (Fusion 360 gap analysis for Fission360)

Note: research budget was ~11 tool calls, mostly search snippets (many aggregators). Prices are third-party unless stated; verify against vendor pages. Date of research: 2026-10-10.

## Onshape: architecture, versioning, FeatureScript, free plan

### Takeaway
Onshape is cloud-native: servers run Parasolid + D-Cubed, the browser gets only triangles, state is persisted continuously (no save, no files). Its admired pieces are the version graph with branch/merge and FeatureScript (built-in features are written in the same language users use). Free plan = public documents only, non-commercial.

### Cited Findings
- Server-side architecture: servers rebuild geometry from feature lists, solve assemblies, compute tessellation; kernel is Siemens Parasolid with D-Cubed solver; client receives triangles rendered via WebGL/OpenGL; microservices on AWS — [Onshape blog](https://www.onshape.com/en/blog/how-does-onshape-really-work)
- 2015 coverage: no install, no local version, no file saving; current material describes continuous persistence of document state — [Architosh 2015](https://architosh.com/2015/03/boston-area-startup-onshape-re-invents-cad-in-the-cloud-and-platform-agnostic/), [Onshape blog](https://www.onshape.com/en/blog/cloud-native-cad-removes-friction-legacy-file-based-systems-collaboration-ai-readiness)
- Branching creates new workspaces for experimentation; merge dialog lets target keep its changes, take source's, or combine, chosen per tab; cannot cherry-pick individual changes within a tab; version graph draws merges explicitly and auto-updates; merge can be undone by restoring the workspace to pre-merge — [Onshape help: merging](https://cad.onshape.com/help/Content/Document/merging.htm)
- Merge is blocked when branches use different FeatureScript versions (update both first) — [Onshape help (zh_TW page)](https://cad.onshape.com/help/zh_TW/Content/Document/merging.htm)
- Forum criticism: no conflict resolution, so merge is really "take all changes from that branch" (older thread, may be outdated) — [Onshape forum](https://forum.onshape.com/discussion/1353/versions-and-branching)
- FeatureScript: Onshape-designed language; built-in features (Extrude, Fillet) are themselves FeatureScript; custom features use same mechanism; can also define custom table types — [FeatureScript guide](https://cad.onshape.com/FsDoc/intro.html), [onshape.com/featurescript](https://onshape.com/featurescript)
- Standard library source is viewable in public document "std"; imported by default into new Feature Studios — [FeatureScript guide](https://cad.onshape.com/FsDoc/index.html)
- Language is proprietary, JavaScript-based but own syntax (per Onshape FAQ as relayed by search tool); a 2016 CIMdata piece calls it "open" — likely means library is viewable — [CIMdata](https://www.cimdata.com/zh/industry-summary-articles/item/6258-onshape-s-featurescript-lets-3d-cad-users-design-faster-with-custom-parametric-features)
- Free plan: unlimited public documents, no private documents, no time limit, no credit card, not for commercial use — [Onshape blog: understand your CAD plan](https://www.onshape.com/it/blog/understand-your-cad-plan)
- Paid pricing (third-party, unverified): Standard ~$1,500/user/yr, Professional ~$2,500 (one Capterra listing $2,100) — [PricingSaaS](https://pricingsaas.com/companies/onshape), [Capterra](https://www.capterra.com.sg/software/164681/onshape)
- Vendor-affiliated reseller (GoEngineer) says Onshape has limited drawing/documentation capability vs SolidWorks — [GoEngineer](https://goengineer.com/onshape-vs-solidworks)

### Inferences
- Because Onshape has no files, versioning is a database property (every edit is a history entry); a local-first CAD can emulate this with an append-only op log + snapshot "versions".
- Whole-tab merge granularity is Onshape's known weak point; a feature-tree-level three-way merge would be a differentiator.
- Writing built-in features in the public extension language (dogfooding) is the key reason FeatureScript is admired and has a large user-feature ecosystem.

### Gaps
- Mate connectors, Variable Studio, configurations, Part Studio vs Assembly details: not researched in this pass (no sourced material fetched). Linux/browser access is implied by browser delivery but not separately sourced.
- Official current Onshape pricing page not reached.

## SolidWorks (incl. Makers / 3DEXPERIENCE), Solid Edge, Inventor

### Takeaway
SolidWorks retains pros through drawings, assemblies, sheet metal/weldments/surfacing breadth, simulation; the hobby route is SolidWorks for Makers at $48/yr (Windows, <$2,000 revenue). Solid Edge has a free tier but terms unconfirmed. Inventor is ~$2,500/yr with no personal free tier.

### Cited Findings
- SolidWorks for Makers: $48 USD/yr (or ~$15/mo), personal-use license delivered via 3DEXPERIENCE; hobbyists with <$2,000/yr revenue; Windows install required; 50% first-year promos via Thingiverse/3Dconnexion — [SolidWorks Thingiverse perk page](https://www.solidworks.com/solution/solidworks-makers/thingiverse.md), [All3DP](https://all3dp.com/1/solidworks-free-download/), [SolidWorks Makers (DE)](https://www.solidworks.com/de/solution/solidworks-makers)
- SolidWorks praised for complex assemblies, simulation, detailed manufacturing drawings, MBD, specialised toolsets (sheet metal, weldments, surfacing, routing, PCB) — [GoEngineer (reseller, biased)](https://www.goengineer.com/en-us/onshape-vs-solidworks-jotform), [All3DP Fusion vs SolidWorks](https://all3dp.com/2/fusion-360-vs-solidworks-cad-software-compared-side-by-side/?critical=1)
- Fusion described as reaching limits with large assemblies, version-control rigor, high-end surfacing, simulation; a forum user rates Fusion surfacing and drawings as good/better than Onshape's — [Onshape forum thread](https://forum.onshape.com/discussion/comment/30223) and search summary above (mixed, forum-level evidence)
- Inventor (US, mid-2026, third-party): ~$305-310/mo, ~$2,440-2,500/yr, ~$7,320-7,505/3yr; no personal free tier found; CDW reseller lists $2,852.84/yr — [ThePricer](https://www.thepricer.org/how-much-does-autodesk-inventor-cost/), [CDW](https://www.cdwg.com/product/autodesk-inventor-professional-2026-new-subscription-annual-1-seat/8330997)
- Solid Edge: Dec 2025 Fabbaloo reports a free maker-oriented version; Student Edition free to students (12-month renewable licence) per 2011 announcements (very dated) — [Fabbaloo](https://www.fabbaloo.com/?p=233429), [Design Engineering 2011](https://www.design-engineering.com/student-edition-of-solid-edge-now-available-free-of-charge-to-all-students-worldwide-145244/)

### Inferences
- "Table stakes" for pros appear to be: robust drawings, big-assembly performance, sheet metal, surfacing, simulation, PDM; a new modeller cannot match them early, so the realistic wedge is the maker/hobbyist and API-driven user.
- The $48 SolidWorks Makers price sets the price anchor: any paid hobby tier must be comparable or free to compete, and Makers is Windows-only (Linux/Mac gap).

### Gaps
- Solid Edge Community Edition licence terms (commercial limits, feature set) unconfirmed; Siemens page surfaced only learning-asset info.
- SolidWorks PDM/configuration/performance specifics: no independent sourced benchmarks found.
- Inventor strengths/weaknesses beyond price not researched.

## Shapr3D and Plasticity

### Takeaway
Shapr3D: iPad/Pencil-first on Parasolid, fast to learn; limits are history/parametric friction, lighter drawings/assemblies, slowness with large models. Plasticity: indie $149 / studio $299 perpetual with 12-month updates, Parasolid-based, loved for direct-edit UX; fillet robustness reports are mixed.

### Cited Findings
- Shapr3D is built on Siemens Parasolid — [Subscribed.fyi](https://subscribed.fyi/shapr3d/reviews/)
- Shapr3D pricing sources disagree (Solo ~$20.83/mo, Studio ~$37.50/mo; Pro $299/yr; €25/user/mo; App Store $37.99/mo); free tier + trial exist — [PricingSaaS](https://pricingsaas.com/companies/shapr3d), [Toolradar](https://toolradar.com/tools/shapr3d/pricing), [Capterra](https://www.capterra.com/p/184498/Shapr3D/pricing/)
- Reviewers highlight iPad + Pencil workflow and fast learning curve; criticisms: parametric history needs planning, parameter management, propagation to copies/mirrors, slowness with large multi-body models, lighter drawings, missing advanced assembly/patterning/automation — [G2](https://www.g2.com/products/Shapr3D/reviews), [Shapr3D forum](https://discourse.shapr3d.com/t/feedback-on-history-based-parametric-version/30980), [Develop3D](https://develop3d.com/reviews/review-shapr3d-ipad-parasoild-modelling/)
- Some users treat Shapr3D as a direct modeller with history hidden — [Shapr3D forum](https://discourse.shapr3d.com/t/shapr3d-still-usable/40040)
- Plasticity: Indie $149 (commercial OK, 2 machines), Studio $299 (4 machines, xNURBS, Align); perpetual licence with 12-month update window; manual updates — [Plasticity docs](https://doc.plasticity.xyz/getting-started/license-types-and-features), [Fabbaloo](https://www.fabbaloo.com/?p=222842)
- Plasticity fillets: some users call them stable/interactive, others report more failures than Rhino and issues with fillets ending at points; kernel is Parasolid (same as SolidWorks/NX) — [McNeel forum](https://discourse.mcneel.com/t/robust-fillets-interacting-and-stable-in-plasticity/159922), [McNeel forum 2](https://discourse.mcneel.com/t/plasticity-new-software/152284?page=15)
- Plasticity has an API site (api.plasticity.xyz) — [Plasticity API](https://api.plasticity.xyz/) (contents not examined)

### Inferences
- Both rely on licensed Parasolid; fillet robustness is a kernel property, so UX (live preview, error feedback, edit order) is the differentiator, not raw capability.
- Direct-edit-first plus optional history is the pattern both users demand; Shapr3D shows retrofitting parametrics is painful, so design the data model with history from day one and expose direct edits as history ops.

### Gaps
- Plasticity gizmo UX, concept-art/mesh workflow: only forum-level evidence; no review fetched. Shapr3D drawings maturity current status not verified.

## Fusion: where it wins, and personal-use limits

### Takeaway
Fusion's edge is integrated CAD+CAM+simulation+electronics at a lower price than Inventor/SolidWorks/Onshape paid, plus a free personal tier; it is weaker on large assemblies, version-control rigor and high-end surfacing per commentators.

### Cited Findings
- Personal use: free for non-commercial; limits include basic CAM, single-user data management, limited electronics, limited manufacturing, no advanced collaboration, no commercial translators — [Autodesk blog](https://www.autodesk.com/products/fusion-360/blog/fusion-for-personal-use-vs-autodesk-fusion/), [Autodesk subscription types](https://www.autodesk.com/products/fusion-360/blog/subscription-types/)
- Third-party claims (unverified): <$1,000/yr revenue, 10 active documents — [Stacksheriff](https://stacksheriff.com/3d-printing/fusion-360-free-personal-license/); 2020 export-format restrictions — [Hackaday](https://hackaday.com/blog/page/2964/?oldid=1726) (dated)
- Fusion commercial ~ $85/mo or $680/yr (third-party, inconsistent) — [Capterra via search](https://www.capterra.com/)

### Inferences
- Fusion beats Onshape on integrated CAM/offline-capable desktop use, SolidWorks on price, Shapr3D/Plasticity on parametric+CAM depth; loses to Onshape on branching and collaboration and to SolidWorks on drawings/large assemblies.
- Fusion's personal-licence restrictions (document cap, export limits) are the opening for a free/open alternative: unrestricted STEP import/export.

### Gaps
- Official Fusion price and personal-use terms not confirmed from primary page.

## Versioning, collaboration, and scripting/API design

### Takeaway
Minimum viable: immutable named versions, branch/merge at the feature-tree level, comments, shareable links; text-based/diffable storage is the open-source route (code CAD + Git). For API: expose one object model, make built-in features use it, ship Python first.

### Cited Findings
- Code CAD (CadQuery/build123d) pairs with Git; build123d docs contrast GUI history with Git as more granular for branching/merging — [build123d docs](https://build123d.readthedocs.io/en/v0.11.1/_sources/introduction.rst.txt)
- PartCAD: package manager for CAD models (CadQuery/build123d/OpenSCAD) aiming to complement Git and substitute PLM — [PartCAD PyPI](https://pypi.org/project/partcad-cli/0.7.15)
- argus-diff geometrically compares STEP/STL/3MF revisions (bodies added/removed/modified, mass/volume deltas); gitcad is experimental git-native B-rep CAD on OpenCASCADE (young projects) — [argus-diff](https://awesome.ecosyste.ms/projects/github.com%2Fmikelmyers%2Fargus-diff)
- FreeCAD .FCStd is a ZIP; uncompressed keeps XML diffable; low-quality source, unverified — via same search result (DiffCAD)
- Fusion API: Python and C++ add-ins, object model language-independent with thin wrappers over C++; scripts + add-ins; first shipped as JavaScript scripting — [Autodesk class handout](https://static.au-uw2-stg.autodesk.com/Class_Handout_MFG225552_Automating_Fusion_360_with_the_API_Patrick_Rainsberry.pdf), [Autodesk blog](https://www.autodesk.com/products/fusion-360/blog/writing-scripts-using-the-new-fusion-360-api-preview/), [adsk on PyPI](https://libraries.io/pypi/adsk)
- FeatureScript: see Onshape section (features and tables defined in the language; std library public).

### Inferences
- Proposed Fission360 MVP versioning: (1) autosaved operation log, (2) named versions/snapshots, (3) branches with three-way merge on feature-tree nodes (improving on Onshape's per-tab all-or-nothing), (4) comments pinned to geometry, (5) read-only share links, (6) human-readable (JSON/XML-like) diffable project format with stable feature IDs so Git works.
- API: Python-first, same API used by built-ins (FeatureScript lesson), parametric user-defined features that appear in the tree and are version-pinned (FeatureScript merge/version mismatch shows the need for explicit API versioning), headless mode for CI, avoid a proprietary language.
- Deliberately skip early: PDM/PLM, simulation depth, cloud-only architecture (a local-first model gives offline use that Fusion/Onshape lack).

### Gaps
- SolidWorks API (VBA/.NET/COM), FreeCAD Python specifics, Onshape REST API: no sourced results in this pass.
- No sourced "table stakes" survey; the list below is inference only.

## Table stakes list (inference, not sourced)
Sketch with constraints and dimensions; extrude/revolve/sweep/loft; fillet/chamfer/shell/draft; patterns/mirror; parametric history with rollback and editable parameters; multi-body and assemblies with joints/mates; STEP/STL/3MF/DXF import-export; 2D drawings with dimensions/BOM; sheet metal (for pro use); undo/redo; units/materials; mesh export for printing; scripting API. Source for emphasis: SolidWorks/Fusion comparisons cited above show drawings, assemblies, sheet metal, surfacing as differentiators pros cite.
