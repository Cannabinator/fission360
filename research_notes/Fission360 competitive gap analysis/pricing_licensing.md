# Autodesk Fusion pricing/licensing changes and the opening for a Linux-native, local-first, open-licence CAD

Research caveat: the fetch tool could not reach autodesk.com/all3dp.com (DNS failure), so findings rest on search-result summaries of Autodesk pages, forums and third-party guides. Items from my own background knowledge are labelled "unsourced" and kept out of Cited Findings.

## 1. Current Fusion plans/prices and how they changed 2019-2026

### Takeaway
Commercial Fusion is $680/yr ($85/mo, $2,040/3yr) since 30 Jan 2024, when "Fusion 360" was also renamed "Autodesk Fusion" and add-on extensions were repriced. Free personal use has been progressively stripped (Oct 2020 / Jan 2021 changes). I found no confirmed 2025-26 base-price rise; figures for 2026 come from third-party guides.

### Cited Findings
- Effective 30 Jan 2024 prices rose to $85/mo, $680/yr, $2,040/3yr (SRP); existing annual subscribers locked at $490 until 2027 renewal; Fusion Team price rose to $195; "no changes... to Autodesk Fusion for personal use currently"; some extensions got cheaper (e.g. $1,600 -> $1,465) — [Autodesk blog via search](https://www.autodesk.com/products/fusion-360/blog/?p=63902); [Polish forum summary](https://www.cnc.info.pl/fusion360-podwyzki-subskrypcji-t121177.html)
- Renewal confusion for 3-year subscribers: at expiry choose annual at locked price or full price for another 3 years — [Autodesk forum](https://forums.autodesk.com/t5/fusion-support-forum/fusion-legacy-price-increase-help/m-p/13031818)
- Earlier rise: a 3-year plan from US$1,410 to US$1,555 (~10%); date not shown in results — [Fabbaloo](https://www.fabbaloo.com/news/autodesk-to-raise-fusion-360-pricing)
- Rename: effective 30 Jan 2024 "Autodesk Fusion 360" became "Autodesk Fusion"; Fusion 360 Manage with Upchain became Fusion Manage on 26 Mar 2024 — [Wikipedia](https://en.wikipedia.org/wiki/Autodesk_Fusion), [Symetri](https://www.symetri.co.uk/news-events/news/upcoming-changes-to-fusion-360/), [Autodesk blog](https://www.autodesk.com/products/fusion-360/blog/?p=67339)
- 2026 bundles per third-party guides: Fusion for Manufacturing $2,040/yr (core + Manufacturing Extension); Fusion for Design $2,190/yr (core + Design + Simulation extensions + Fusion Manage); standalone Manufacturing extension $1,465/yr; Design extension ~$595/yr (one guide); 4-for-3 offer on annual commercial plans through 31 Jan 2027; 30-day trial — [mfgrobots](https://www.mfgrobots.com/Article/mfg/it/53531.html), [Toolradar](https://toolradar.com/tools/autodesk-fusion/pricing). Figures are not verified on Autodesk's own page.
- 2020 personal-use cuts (per customer email/forum quotes): probing, 3+2/multi-axis milling, rapid moves, auto tool change removed; drawing multi-sheet/templates/output limited; cloud rendering and public-link downloads removed; exports F3Z, DWG, DXF, IGES, SAT and STEP listed as removed (note: Autodesk's later support page says STEP export remains); simulation/FEA/generative design removed; 10 active editable documents cap — [Snapmaker forum](https://forum.snapmaker.com/t/fusion-360-features-removed/9392), [OneFinity forum](https://forum.onefinitycnc.com/t/major-changes-to-fusion-360-for-hobby-use/874), [Carbide3D forum](https://community.carbide3d.com/t/autodesk-changing-hobbyist-terms-of-use/25927/10)
- 10-document limit: effective 19 Jan 2021 per Autodesk support; it caps concurrently *editable* docs (others read-only, switchable), uploads/creation unlimited; STEP export remains — [Autodesk support](https://autodesk.com/support/technical/article/Fusion-360-Free-License-Changes), [Autodesk blog](https://www.autodesk.com/products/fusion-360/blog/the-10-document-limit-for-personal-use-explained-in-7-steps/)
- Startups: eligibility per Autodesk India page: <3 yrs old, <=10 employees, <$100k revenue, own physical product; 1-yr terms renewable. Price conflicts: free 1-yr vs ~$150 for 3 years — [Autodesk startups](https://www-pt.autodesk.com/in/products/fusion-360/startups), [Vagon](https://vagon.io/blog/fusion-360-pricing)
- Education: free for students/educators via SheerID verification — [HP Academy](https://hpacademy.com/technical-articles/how-to-get-fusion-360-for-free)

### Inferences
- Pattern: a stable core price with rising add-on/bundle upsell (simulation, advanced CAM) and shrinking free tier; the hobbyist-to-pro gap is $0 -> $680.
- Unsourced background: the cuts were announced Sept 2020 and the 10-doc date slipped from Oct 2020 to Jan 2021 after backlash; the 2019 baseline was a free hobbyist/startup tier with nearly full features.

### Gaps
- Exact 2025-26 US list prices and any 2025 increase: no Autodesk page retrieved; search found none.
- Fusion Team/Hub changes, cloud limits/credits (generative/simulation cloud credits): not found.
- Exact original announcement date of 2020 changes: not confirmed.

## 2. Personal-use licence terms and the revenue limit

### Takeaway
Free only for home-based non-commercial use, under $1,000 annual revenue, 3-year renewable term; users perceive it as a trap for side-hustle sellers and benchmark it poorly versus Onshape/SolidWorks Makers.

### Cited Findings
- Autodesk pages: individuals earning <$1,000/yr, not for primary employment, company environments, commercial training; Canadian page phrases it as >$1,000 or commercial projects must convert — [Autodesk personal](https://autodesk.com/products/fusion-360/personal), [CA page](https://www.autodesk.com/ca-en/products/fusion-360/personal)
- 3-year term, must reapply; third-party claim of renewal only with <30 days left (unverified) — [Autodesk blog](https://www.autodesk.com/products/fusion-360/blog/?p=18687), [Vagon](https://vagon.io/blog/fusion-360-pricing)
- Forum reaction: "Please Autodesk don't limit the personal licenses" thread — [Autodesk forum](https://forums.autodesk.com/t5/fusion-support-forum/please-autodesk-don-t-limit-the-personal-licenses/td-p/9750422)
- Commercial tier jump ($680) and paywalled simulation/advanced CAM/generative design cited as migration drivers — [StackSheriff](https://stacksheriff.com/3d-printing/fusion-360-alternatives/) (affiliate-linked; weak source)

### Inferences
- A seller of printed parts crossing $1,000 faces ~$680/yr, a strong conversion barrier and a space for permissively licensed tools.

### Gaps
- How Autodesk measures/enforces revenue: not found. Statistics on adoption: none.

## 3. Migration triggers

### Takeaway
Documented triggers: 2020 feature cuts/10-doc cap, 2024 price rise, cloud outages (offline mode, no access to Open/Save/Export). AI/data-use terms, login mandates and data-ownership concerns: no sourced evidence found.

### Cited Findings
- Outages: 3 Aug 2023 database failure put Fusion 360 into offline mode until 12:01 PM PDT — [Autodesk health](https://health.autodesk.com/incidents/zf4656lzpl6v); earlier outages blocked Open/Save/Upload/Export; users asked for local storage — [Autodesk forum](https://forums.autodesk.com/t5/fusion-design-validate-document/resolved-fusion-360-outage/m-p/6910941)
- Forum threads show hobbyists moving after restrictions — [V1 Engineering](https://forum.v1engineering.com/t/time-for-a-change-of-cad/31203), [Snapmaker](https://forum.snapmaker.com/t/fusion-360-features-removed/9392)

### Inferences
- Cloud-dependency (account, sync, outages) is a durable pain point supporting a local-first pitch.

### Gaps
- AI training/terms-of-service changes, data-retention policy changes (e.g. inactive-document deletion), account requirements, Hacker News/Reddit quantified sentiment: not found; need separate search.

## 4. Linux situation

### Takeaway
No official Linux client; Autodesk says only Windows/macOS. Community routes: Wine/Lutris/Proton installer scripts (fragile), Windows VM, browser version (not available to trial/personal accounts per search summary).

### Cited Findings
- Community manager: Linux not supported — [Autodesk forum](https://forums.autodesk.com/t5/design-validate-document/does-autodesk-fusion-360-support-linux-os/td-p/6565836); ideastation "Linux port" request — [IdeaStation](https://forums.autodesk.com/t5/fusion-360-ideastation/fusion-360-linux-port/idi-p/8743014); petition — [forum](https://forums.autodesk.com/t5/fusion-support-forum/petition-to-add-linux-support/m-p/9583810/highlight/true)
- Wine/Proton installer attempts — [forum](https://forums.autodesk.com/t5/fusion-support-forum/running-fusion-360-installer-on-linux-through-proton-libraries/m-p/9628918/highlight/true); guide — [All3DP](https://all3dp.com/2/fusion-360-for-linux-how-to-install-it/)
- Browser version works on Linux but not for trials/Personal (search-summary claim, unverified)

### Inferences
- Unserved, vocal Linux segment; Wine path breaks on updates, so a native app has a clear niche.

### Gaps
- Current WineHQ rating and 2026 Autodesk statement not verified.

## 5. Where users went and why

### Takeaway
FreeCAD (free/offline, steep curve), Onshape Free (cloud, public docs), Plasticity (one-time purchase), SolidWorks for Makers (cheap, Windows); drivers: price, offline/ownership, ease for 3D printing.

### Cited Findings
- FreeCAD: offline, 2-4 week learning investment; Onshape: liked but cloud and public documents; Plasticity one-time purchase — [StackSheriff](https://stacksheriff.com/3d-printing/fusion-360-alternatives/), [Reddit mirror](https://redlib.hackliberty.org/r/BambuLab/comments/1fcojmi/what_are_people_using_to_design)
- Onshape free plan: older source says 10 private docs/100MB and unlimited public; later private removed; commercial-use terms disputed on forum — [Onshape forum](https://forum.onshape.com/discussion/comment/23012), [more](https://forum.onshape.com/discussion/comment/55511)
- SolidWorks for Makers: reported $24/yr Black Friday deal, annual, Windows-only — [Bambu forum](https://forum.bambulab.com/t/solidworks-for-makers-is-now-only-24-year/115575)

### Inferences
- Nobody combines Fusion-like parametric UX, native Linux and local-first files; FreeCAD has the first-order gap in UX.

### Gaps
- Shapr3D, Solid Edge Community, DesignSpark, SolveSpace: no sourced data; standard SolidWorks Makers price unverified.

## 6. Sustainability models

### Takeaway
Donation-funded FreeCAD is small (~EUR130k/yr); Blender relies on corporate patrons; KiCad runs fund drives. Fission360 could add paid sync/support/extensions.

### Cited Findings
- FreeCAD 2025: donations EUR129,981.32, expenditures EUR127,093.95, 2026 budget EUR230,000 drawing on reserve; income all donations, mostly individuals — [FPA report](https://fpa.freecad.org/annualreports/2026.html), [blog](https://blog.freecad.org/2026/04/24/2025-annual-report-and-plans-for-2026/)
- KiCad 2025 fund drive target $128,000; current total unclear — [kicad.org](https://kicad.org/blog/categories/Media)
- Blender: corporate patrons (Wacom, Bolt Graphics Sept 2025; Netflix Animation Studios; Dell EUR30k/yr; Octane at least EUR240k/yr); Anthropic patron news reported with conflicting amounts — [CG Channel](https://www.cgchannel.com/tag/blender-development-fund/), [GamingOnLinux](https://www.gamingonlinux.com/2026/04/anthropic-begin-funding-blender-as-a-corporate-patron/comment_id=293580); older Intel-era figure >EUR1.8M/yr (outdated)

### Inferences
- Donations alone do not fund a full-time team; a hybrid (corporate sponsorship + optional paid cloud sync/support) is realistic.

### Gaps
- Blender 2025 total income, KiCad final total, Onshape free-plan economics: not found.

## 7. Licensing risks for Fission360

### Takeaway
OCCT (LGPL-2.1 + OCCT exception, v6.7.0+) and PySide6 (LGPL/GPL/commercial) are compatible with an MIT/LGPL/GPL app if dynamically linked and notices kept; verify wheel bundled libs; UI cloning risk is mostly trade dress/copyright of assets, not covered by search.

### Cited Findings
- OCCT 6.7.0+ is LGPL-2.1-only with exception allowing object-code distribution under own terms with prominent notice that it uses OCCT; <=6.6.0 used OCCT-PL; Debian notes commercial licence available — [SPDX](https://spdx.org/licenses/OCCT-exception-1.0.html), [OCCT forum](https://dev.opencascade.org/content/open-cascade-technology-changes-its-license-gnu-lgpl), [Debian](https://metadata.ftp-master.debian.org/changelogs/main/o/opencascade/stable_copyright)
- OCP (CadQuery bindings) is Apache-2.0 on conda-forge; wheels bundle (delocate) native libs, so their licences travel with it — [conda-forge](https://anaconda.org/conda-forge/ocp), [ocp-build-system](https://github.com/CadQuery/ocp-build-system)
- PySide6: LGPLv3/GPL/commercial; dynamic linking and replaceability, include licence text and offer source; QtCharts/Data Visualization are GPL-only; Qt advises commercial users not to use pip community wheels — [pythonguis](https://www.pythonguis.com/faq/licensing-differences-between-pyqt6-and-pyside6/), [Qt docs](https://doc.qt.io/qtforpython-6/commercial/index.html)

### Inferences
- LGPLv3 (PySide6) is compatible with GPLv3 and permissive code but not GPLv2-only; choose GPLv3-or-later/LGPLv3/MIT, not GPLv2-only. Ship as separate wheels (replaceable) rather than frozen single binaries, or include relink instructions. Unsourced: UI layout/ideas are generally not patentable as such, but avoid Autodesk names, icons, logos and copied assets; no patent search was done.

### Gaps
- Actual cadquery-ocp wheel bundled licence files (VTK, Qt-like libs) not inspected; patents/trade-dress: no sources found; not legal advice.
