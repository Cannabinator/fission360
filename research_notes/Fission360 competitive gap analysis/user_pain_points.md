# User pain points and wished-for features: Fusion 360 and CAD generally (hobbyist / maker / small shop)

Method caveat: WebSearch returned summaries only. WebFetch failed (DNS errors) for every page, so NO page was read in full, and no direct verbatim quotes were verified from page text. Items in quotation marks below are snippets as reproduced in search-result summaries (semi-verified); everything else is paraphrase. Reddit, Hacker News, G2, TrustRadius and PCMag were not surfaced by search; coverage is thin and mostly forum-based. Sample sizes and vote counts are mostly unknown.

## 1. What do Fusion 360 users complain about most?

### Takeaway
Recurring, documented themes: cloud-only dependence and lock-in, hobbyist-tier restrictions and rising prices, and fragile parametric references. Evidence for performance, crashes, UI churn and years-old bugs was NOT found in this pass. Prevalence cannot be quantified from what was found.

### Cited Findings
- Cloud-only: a user on Autodesk's forum said that because Fusion is cloud-based only, they cannot use it the way they used EAGLE for commercial projects, and noted users on computers not always connected to the internet are affected; Autodesk's answer was that Fusion is cloud-based by design (paraphrase of search summary; thread date not confirmed) — [Autodesk forum: EAGLE dying June 7 2026](https://forums.autodesk.com/t5/eagle-forum/eagle-dying-on-june-7-2026/m-p/12952477/highlight/true); see also [Will Fusion EVER move away from "the cloud"](https://forums.autodesk.com/t5/fusion-support-forum/will-fusion-ever-move-away-from-quot-the-cloud-quot/m-p/9207811) (2019-era thread, older)
- Autodesk is ending sale/support of EAGLE on June 7, 2026, a factor pushing electronics users onto Fusion — [Autodesk forum](https://forums.autodesk.com/t5/eagle-forum/eagle-dying-on-june-7-2026/m-p/12952477/highlight/true)
- Personal-use limits (introduced 2020, older): only 10 editable documents at once (others read-only); 2/2.5/3-axis milling only; extensions, simulation, generative design removed; no collaboration/data management; non-commercial only. Autodesk says STEP, STL, DXF export remain — [Autodesk Free License Changes](https://autodesk.com/support/technical/article/Fusion-360-Free-License-Changes); [Autodesk blog](https://www.autodesk.com/products/fusion-360/blog/?p=18687)
- Hobbyist reactions to the 10-document cap: it "discourages my practice of putting groups of components in different files"; one reported 8 files stuck "still uploading" at the limit; add-in developer errors at the cap (paraphrase/snippet, 2020-2021) — [Autodesk forum: Please Autodesk don't limit personal licenses](https://forums.autodesk.com/t5/fusion-support-forum/please-autodesk-don-t-limit-the-personal-licenses/td-p/9750422); [Maslow CNC forum](https://forums.maslowcnc.com/t/new-limitations-on-fusion-360-for-personal-use/14685); [Autodesk forum: document still uploading](https://forums.autodesk.com/t5/fusion-support/document-is-still-uploading/td-p/12994059)
- Pricing: Fabbaloo reported annual price rising from US$495 to US$545 in 2022 — [Fabbaloo](https://www.fabbaloo.com/news/autodesk-to-raise-fusion-360-pricing). Ondsel (a FreeCAD-ecosystem vendor, biased) claims a 130% rise over 10 years to $690 by Jan 2024 and that features were stripped from the free tier in 2020 — [Ondsel: "autodesk enshittifies fusion 360"](https://ondsel.com/blog/autodesk-enshittifies-fusion-360). A Bambu Lab forum user called Autodesk "predatory and customer-hostile" and claimed a ~200% rise in 2024 to over $650 (unverified single-user claim) — [Bambu forum](https://forum.bambulab.com/t/3d-program-for-modelling/69756?page=4)
- UK reseller notes rebalanced pricing of Fusion and extensions, with existing subscribers price-locked (GBP 385 SRP) until 2027 renewal — [Symetri](https://www.symetri.co.uk/news-events/news/upcoming-changes-to-fusion-360/)
- No perpetual license: forum user complaint that Fusion and Onshape are both cloud-based with no perpetual licence, "always at their mercy" (paraphrase) — [Bambu forum](https://forum.bambulab.com/t/first-time-user-best-cad-software-is/90374?page=2)
- Fragile references: thread "References Repeatedly Lost" (late 2024 by URL ids): ~1,000-operation design; references far back in the timeline broke without edits, suspected edge renaming, warnings appeared after reopening from cloud; fixing yellow warnings cascaded into a day of repair; user asked whether to split design or convert to direct modelling; no official answer seen — [thread 1](https://forums.autodesk.com/t5/fusion-support-forum/references-repeatedly-lost/m-p/13141717/highlight/true), [thread 2](https://forums.autodesk.com/t5/fusion-support-forum/references-repeatedly-lost/m-p/13203525)
- Component restructuring blocked by tangled references, with no tool to visualize or untangle them (older, ~2022) — [Autodesk forum: Rule #1](https://forums.autodesk.com/t5/fusion-design-validate-document/rule-1-restructuring-of-components/m-p/10908804)
- Sketch solver: a user said Fusion "breaks in very strange ways, tangents move to the other side very frequently, projections are lost for no reason" (snippet) — [V1 Engineering forum](https://forum.v1engineering.com/t/time-for-a-change-of-cad/31203)
- Switchers cite Onshape's sketch robustness ("sketches, relations, and projections seem extremely more robust") — [V1 Engineering forum](https://forum.v1engineering.com/t/time-for-a-change-of-cad/31203); one workflow write-up: [Printables: From Fusion to Onshape](https://www.printables.com/article/from-fusion-to-onshape-my-cad-workflow-rebuild-J5EMv45) (not read)
- Capterra has 2026 Fusion reviews but the page could not be fetched; contents unknown — [Capterra](https://capterra.com/p/178416/Fusion-360/reviews/)

### Inferences
- Cloud dependency + document caps + price trajectory are the trust issues a local-first, perpetual/one-time-price competitor could exploit (supported by multiple independent sources but small sample).
- Topological-naming-style breakage is a real, unresolved pain in Fusion too, not just FreeCAD; a robust persistent-ID / re-link UI is a differentiator. Fusion's "re-link projected geometry" option is reportedly better than Onshape's (below).

### Gaps
- No evidence gathered on: large-assembly performance, crashes, UI-change backlash, years-old bugs, data-ownership/ToS fears, save/versioning failures beyond the upload-stuck report, extension paywall sentiment after 2023. Reddit/HN/G2/TrustRadius/PCMag not accessed.

## 2. Top-voted requests on Idea Station / forums

### Takeaway
The legacy IdeaStation is archived (replaced by a Feedback Hub); no current ranked list was found. Historic and Linux data points only.

### Cited Findings
- Sheet metal was the number-one voted IdeaStation idea (2016) and later shipped — [Autodesk: Fusion Forecast Sheetmetal](https://www.autodesk.com/products/fusion-360/blog/fusion-forecast-sheetmetal/); [Aug 8 update](https://www.autodesk.com/products/fusion-360/blog/august-8-update-whats-new/) (older)
- IdeaStation archived, pointing to the Fusion 360 Feedback Hub — [archived IdeaStation](https://forums.autodesk.com/t5/fusion-360-ideastation-archived/idb-p/125/status-key/15)
- Linux idea ("Linux/Ubuntu"): 253 comments, status "Future Consideration"; vote count not visible — [Idea Station: Linux](https://forums.autodesk.com/t5/ideastation-request-a-feature-or/linux/idi-p/4530727); another: [Fusion 360 Linux port](https://forums.autodesk.com/t5/fusion-360-ideastation/fusion-360-linux-port/idi-p/8743014)
- Mesh workflow feedback: users want to stay in Fusion for print pipeline incl. mesh sculpting; Autodesk PM said it would be useful but not an active focus (2021-22); 3MF with colour/textures was planned for H1 2022 (check if shipped) — [Feedback Hub](https://forums.autodesk.com/t5/fusion-360-feedback-hub/open-looking-for-feedback-on-mesh-based-workflows/m-p/11271796)

### Inferences
- Linux demand is long-standing (thread started ~2013 id) and unanswered by Autodesk.

### Gaps
- Current top-voted ideas (drawings, parametric patterns, STEP export quality, API gaps) not found; the Feedback Hub should be browsed directly.

## 3. What users love that a competitor must match

### Takeaway
Thin evidence: the timeline/component-sketch-body model, constraint-based sketching UX, and re-link of projected geometry were praised; integrated CAM/CNC use is cited by makers.

### Cited Findings
- One user: Fusion is their "go-to for both CNC designs and 3D printing designs"; understanding components, sketches, bodies and the timeline was key — [Sienci forum: Fusion vs Onshape](https://forum.sienci.com/t/someone-school-me-on-fusion-vs-onshape/8214)
- A FreeCAD switcher found its constraint tools clunky and much slower than Fusion's (paraphrase) — [V1 Engineering](https://forum.v1engineering.com/t/time-for-a-change-of-cad/31203)
- When an upstream projected item changes, Fusion offers to re-link projected geometry; in Onshape the user must delete and relink manually (paraphrase) — same thread
- Onshape praised for timeline preview ("Final" tick box when editing earlier feature) — same thread
- Free hobbyist tier is regarded by some as hard to beat for complex work — [Capterra/G2 snippets via search, unverified]

### Inferences
- Must-match list (inferred, not vote-ranked): history timeline with rollback/edit, fast sketch constraint UX, projection re-link, CAM integration for CNC hobbyists, a free/cheap hobby tier.

### Gaps
- Marking menu, direct+parametric hybrid, and integrated CAM sentiment not directly sourced.

## 4. Linux CAD users

### Takeaway
No native Fusion build; Autodesk status "Future Consideration" for a decade; users rely on Wine/Proton scripts, Onshape (browser), or FreeCAD.

### Cited Findings
- Autodesk staff said Linux was not the next priority and floated a zero-client/browser route; community has Fusion running under Wine/Proton/DXVK via modified installers — [Native Linux App thread](https://forums.autodesk.com/t5/fusion-support/native-linux-app/td-p/8575740); [Idea Station Linux](https://forums.autodesk.com/t5/ideastation-request-a-feature-or/linux/idi-p/4530727); [MakeTechEasier guide](https://maketecheasier.com/use-fusion-360-on-linux/)
- FreeCAD recommended as most Fusion-like free option, no Wine required; Onshape works in browser but lacks some Fusion features; Plasticity has a Linux build but is more freeform/less parametric (search-summary level) — [AlternativeTo](https://alternativeto.net/software/fusion-360/); [Lemmy thread](https://lemmy.federate.cc/post/51770)
- Onshape terms change removed a free-tier loophole for earning money, while Fusion's startup licence allows it — [next.lemm.ee comment](https://next.lemm.ee/comment/12944535) (unverified)

### Inferences
- A native, local-first Linux parametric CAD with Fusion-like UX fills a clear gap: browser tools are cloud-dependent, FreeCAD has UX friction.

### Gaps
- No r/linux or r/FreeCAD threads read; no specific list of missing features per alternative.

## 5. 3D-printing / maker workflow needs

### Takeaway
Only mesh-workflow evidence found; nothing on 3MF export quality, threads, text/emboss, heat-set inserts, or enclosure workflows.

### Cited Findings
- Fusion can open/inspect/repair STL/OBJ/3MF; mesh workflows moved into Design workspace July 2021 — [Packt](https://www.packtpub.com/product/3d-printing-with-fusion-360/9781803246642)
- Users asked for mesh sculpting inside Fusion; Autodesk not focused on it — [Feedback Hub](https://forums.autodesk.com/t5/fusion-360-feedback-hub/open-looking-for-feedback-on-mesh-based-workflows/m-p/11271796)
- A Bambu forum user calls Onshape easiest learning curve and lightest on hardware for 3D printing — [Bambu forum](https://forum.bambulab.com/t/3d-program-for-modelling/69756?page=4)

### Inferences
- Parametric print helpers (heat-set insert holes, tolerance presets, enclosure generators) are plausible differentiators but unvalidated here.

### Gaps
- All specific maker-workflow requests (threads, text, tolerances, 3MF) unsourced; recommend a follow-up with working fetch access (r/3Dprinting, r/functionalprint, Printables, Fusion Feedback Hub).
