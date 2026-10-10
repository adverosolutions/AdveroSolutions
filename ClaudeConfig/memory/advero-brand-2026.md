---
name: advero-brand-2026
description: "Advero Solutions logo + social branding project (started 2026-09-30); Spatial look; B Depth picked 2026-09-30; masters in repo Brand/; full social kit being built"
metadata:
  node_type: memory
  type: project
  originSessionId: c804c71e-7545-4f61-901d-dc2c539b0185
  modified: 2026-09-30T21:45:55.451Z
---

On 2026-09-30 Lorenzo asked for full Advero Solutions branding (logo, banner, then every social platform), in the same Spatial design as his Upwork pages ([[upwork-visual-walkthrough-lane]]), approved by him before the full rollout. It is Advero **Solutions**, not the old Advero Advertising (he checked); the name is set as two words "Advero Solutions" unless he says otherwise.

Round 1 is a Design canvas artifact: https://claude.ai/artifact/QWWP6kuStm58D1u8sUG1wL. It holds a foundations sheet plus six directions (A Heritage ring+chevron, B Depth stacked glass squares, C Flow node "A", D Orb blue sphere, E Wordmark "advero.", F Check "a" into a checkmark). Each direction has a 1440x960 logo sheet and a 1584x396 LinkedIn banner with draft copy "Leads in. Calls booked." and the three case-study numbers. Source files and the brief live in the session scratchpad and are not in the repo yet.

**Why:** he wants one cohesive brand across Upwork pages and every social profile.

**How to apply:**
- Next step is his pick or mix. Then build the full kit: exact platform sizes, PNG/SVG exports, email signature and favicon.
- Eyebrow text uses deeper blue #1f5fd6, because #2f74f5 fails contrast at small sizes.
- Parked for round 2: the D banner card overlap, the E one-colour dot glow, the F bottom-row gutters, and the foundations "Sample data" panel looking like a placeholder.
- As with the Upwork page bake-off, many parallel directions and then a pick worked better than iterating a single design.

**Update 2026-09-30: B picked, full kit in progress.** Lorenzo chose B (Depth) and liked D (Orb) too; D's sphere may become a supporting accent. The mark was refined to climb at about 54°. The approved masters (SVGs with outlined wordmark, PNGs, GEOMETRY.md) and the tokens (`Brand/tokens/brand.css`, `tokens.json`) are in the repo `Brand/` folder for the website redesign, which runs in a separate chat. Rules from platform research:
- Personal profile photos (LinkedIn personal, Upwork, X, Skool member) must be his face. Upwork bans logos and text in the photo. The kit gives a sky headshot background for them, and the logo avatar is for brand accounts only.
- Upwork portfolio images are 1000x750 with minimal text and no other platforms' logos.
**Kit finished 2026-09-30.** All assets passed review. They are in `Brand/` (126 files: `social/<platform>`, `templates`, `email`, `web`, `guidelines`, `source` artboards plus `render.py`), and `Brand/README.md` maps each file to its platform slot. The canvas has five pages: Brand, Banners, Profile photos & icons, Templates, Round 1. The commit is 98e027e on local main and was cherry-picked to branch `brand/advero-kit` in `.worktrees/brand`, where the suite passed with 12534 tests. The live-write hook blocks pushes from Claude, so Lorenzo pushes from his own terminal.
**Headshot done 2026-09-30.** His Photos-library original (HEIC, stored rotated) was cut out with macOS Vision person segmentation through pyobjc, because the Swift CLT SDK is broken. It sits on brand light blue #6aa5ff; he said "fantastic". The files are `Brand/social/avatars/headshot-lorenzo-*`.
**Copy follows the website (2026-09-30):** the eyebrow is "AI agents for service businesses", the headline stays "Leads in. Calls booked.", and agent names come from Website/index.html ([[advero-website]]). He called the LinkedIn banner "kind of empty" and wants it to read as an established company. He picked **Live** ("much better") over Agents (roster plus proof) and asked for a centring polish; after review, the final version is in `Brand/social/linkedin/` (commit 7448b46). The design shows website-hero glass panels (reply agent, calendar, calls-booked card) at one zoom, centred with the text block. **Carry-over done 2026-09-30:** he said "make sure everything matches and carries over nicely", so X header, Facebook cover, YouTube banner, Skool cover, Upwork agency banner and the web og/twitter share images now use the Live design, all reviewed and approved. Commit 69a2353 on main, cherry-picked as 7391e90 on `brand/advero-kit`; canvas v10. Generators live in session scratchpad `kit/work-CO-*/gen.py` (not in repo).
- YouTube uses panel zoom 0.80 so floor shadows fade before the y 931 phone crop; the blank TV slabs were removed.
- Web cards: the page sky is under 4.5:1 behind a #1f5fd6 eyebrow on its own, so a soft white `.lv-pool` sits behind the eyebrow (min 4.69). Re-run a contrast check if eyebrow position, width or tracking changes.
- Parked kit-wide: the white avatar "M" on the Reply agent is 3.35:1 against the light end of its gradient (in the LinkedIn pattern too).
- The live site's share images (Website/build.sh copies Brand/web into dist) update only when the website session rebuilds and redeploys; that is not the brand chat's job.
Still open:
- Lorenzo pushes `brand/advero-kit` himself (6 brand commits not yet on origin as of 2026-09-30).
- The Facebook cover and LinkedIn company cover need a live crop check.
- Parked polish is in the review reports.
