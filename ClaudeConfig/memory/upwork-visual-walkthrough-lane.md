---
name: upwork-visual-walkthrough-lane
description: "Interactive HTML \"finished system\" walkthroughs as a Loom prop; Lorenzo loved it and wants to split test it against canvas builds (2026-09-28)"
metadata:
  node_type: memory
  type: project
  originSessionId: db551e75-45d4-461e-8eba-556c8fab2d9a
  modified: 2026-09-28T15:20:54.258Z
---

On 2026-09-28 I built `jobs/ghl-crm-funnels-automation-backend/walkthrough.html` for a GHL CRM/funnels job. It's a single-file interactive mock of the client's finished system. Tabs: overview/why, funnel + form with a "submit a test lead" animation, pipeline with simulated moves, the workflows drawn step by step with a run animation, the follow-up sequence, the contact record, and reporting. Branding is neutral, not a fake GHL UI. Lorenzo: "these look really good", and he's considering it for ~99% of jobs because clients don't understand backends. Idea: show the visual walkthrough, then build the real n8n/GHL system on the backend after the hire. He wants to **split test** it against canvas builds.

**Why:** It's a stronger, easier-to-follow Loom prop for non-technical clients.

**How to apply:**
- Offer it as a prop option, and track it with a `--variant` label in finalize so the two can be compared ([[upwork-proposal-assessment]], outcome sync).
- Keep it honest on camera and in the proposal: "how I'd structure your system", not "your live account".
- Use neutral branding, never an imitation of a vendor's UI.
- [[upwork-only-the-job-post]] and [[upwork-best-version-first]] still apply.


**Update 2026-09-28 (later):** Lorenzo decided that for the week of 2026-09-28 *every* job gets a visual walkthrough, including n8n and Make jobs. That week is the test arm, and earlier canvas weeks are the control. Tag each one `--variant visual-walkthrough`. The rules are in `jobs/_AGENT_BRIEF.md` ("Visual walkthrough week"). Proposals say "mock of how I'd set up your system" and push the 15 minute call.

**Positioning update 2026-09-28:** Lorenzo felt "nobody cares for a visual walkthrough, they want something tangible". It is now framed as a **clickable prototype** of their system: the file is `prototype.html`, it's published as a private Artifact link inside the proposal ("click through it yourself"), and it's paired with "the workflows behind it are already built" when we have GHL or n8n files. Never say "mock" or "walkthrough". The variant label is `prototype`.

**Quality bar (Lorenzo, 2026-09-28):** "Make it really high quality, knock it out of the park". Prototypes should be extremely visual and premium. When the post asks for a system, the page demos that finished system running on sample data ("this is exactly what it'll look like when it's done"), and every requirement gets a working screen. The cold-email and GHL+Pipedrive prototypes from 2026-09-28 are the minimum bar.

**Design bar (Lorenzo, 2026-09-28, later):** "the design is not as good as what I know you can do. It needs to be gorgeous, elegant, almost like a $15,000 custom build." The first prototypes read as busy SaaS dashboards: too many cards and chips, glyph icons, generic fonts. The standard now lives in `upwork-pipeline/jobs/_PROTOTYPE_DESIGN.md` (restraint, whitespace, a distinctive type pairing, SVG icons, one choreographed signature moment, dark mode designed on its own terms). A design review scores "$15k custom build" 8+ before a prototype reaches him.

**No link in the proposal (Lorenzo, 2026-09-28, overrides "click through it yourself" above):** the prototype link is never in the proposal. The client sees it in the Loom and has to message him to get the link. Drafts omit the "Click through the prototype yourself" line entirely. `finalize` logs prototype-only jobs (no spec.json) with platform `prototype`.
**Why:** a message from the client opens the conversation.

**90-second rule (Lorenzo, 2026-09-28, latest):** the prototypes got too complex. "I can't follow along myself, so how am I going to expect the prospect to follow along?" He likes the architecture, but each prototype must be walkable in a 1 to 2 minute Loom. That means one sample story, 4 to 6 linear steps driven by a Next button, one idea and one moving part per step, and no code, long tables, toggles or second samples. The full rule is in `jobs/_PROTOTYPE_DESIGN.md` ("The 90-second rule"). The reviewer scores "walkable in 90 seconds" 8+. SaaS setup engine is the pilot before the rest are rebuilt.

**Show, don't explain (Lorenzo, 2026-09-28, overrides the 90-second step format):** a 6-step slideshow with headlines and short sentences still failed. "It's so hard to follow... If the text isn't earning its place on the screen, it doesn't need to be there. Just make it beautiful." The prototype is now one canvas: a 4 to 6 node flow, labels of 1 to 3 words only, one sample item travelling node to node, a big payoff at the end, and Play running in 15 to 25 seconds with arrow keys to step. Lorenzo narrates; the screen only shows. Full rule: `_PROTOTYPE_DESIGN.md` "Show the system, don't explain it".

**Final calibration (Lorenzo, 2026-09-28, overrides the two sections above):** the wordless 5-node flow was too thin ("gives me nothing to talk through"). He approved the detailed voice-agent prototype with one change: "slightly simplify... remove a lot of the fluff words... beautiful, animated, automated... minimal words on the screen." So the target is to keep the screens, live moments and real records, cut ledes and explanatory text, add motion everywhere, and show the ideal outcome, all walkable in 2 minutes. Rule: `_PROTOTYPE_DESIGN.md` "Keep the system, cut the words". Voice agent is the pilot.

**Presenter film mode (Lorenzo, 2026-09-28, "we're getting really close"):** treat each prototype as a board-of-directors YouTube video that he narrates live. Scenes play in a fixed order and nothing auto-plays. A bottom presenter bar has Play and Next scene (Space plays, arrow keys move between scenes). Each action runs 6 to 15 seconds and holds on a beautiful end frame, with cinematic transitions between scenes. Beauty is the priority. It's in `_PROTOTYPE_DESIGN.md`.

**Approved base (Lorenzo, 2026-09-28, final):** the voice-agent film is the template: animated agent, scene description cards, presenter bar, rich motion. A copy is in `upwork-pipeline/jobs/_reference/voice-agent-film.html`. His last note was "as many beautiful visuals on the screen as possible". The plan is to apply this format to the next batch and to the rest of this batch when he says go. He's adding the next batch of saved jobs himself.

**Update 2026-09-28 (evening): the prop is now a cinematic reel, not a click-through film.** Lorenzo rejected the presenter-film prototypes ("missing the mark", "took way too long") and then crude drawn illustrations ("triangles and circles... horrible"). He approved the dark cinematic reel `jobs/hubspot-real-estate-lead-automation/reel.v2.html` ("Now we are talking"): one Play, 35-55 s, glass UI in 3D, aurora, grain, particle streams, masked serif type, closing word card. Next bar is "Netflix film" quality, plus a live automation-logic shot and a builder finale in the named platform's style ("this is what it will look like in your account", no vendor logo, labelled illustrative). Brief: `jobs/_REEL_BRIEF.md`.
**How to apply:** speed matters as much as quality. Show him something fast, never draw clip-art, and skip long review loops.
**Final format (2026-09-28, later still): a scrolling page, not a video.** "Make sure that it's not a video... something I can scroll through... the animations pop up as you scroll... It looks very professional." The 16:9 frame, Play button and scene dots read as low quality. The build is a full-width page: a hero, then one section per moment (glass UI, depth, particles, the live automation flow), then the platform-style builder, then the closing words. Each section animates once on scroll-in (IntersectionObserver). Brief: `jobs/_REEL_BRIEF.md` UPDATE 2. Output file: `page.html`.
**Winner (2026-09-28, night): the Spatial design.** Lorenzo had 10 directions built on the same HubSpot build (`jobs/hubspot-real-estate-lead-automation/designs/d01..d10`) and picked **d08 Spatial**: light visionOS-style white panels at real depths over a pale sky gradient, with scroll parallax, tilt-in, mouse drift, Figtree type and a system-blue accent. It is now the template for every job (`hubspot-real-estate-lead-automation/page.html`, brief UPDATE 3). The dark aurora look is retired.
**How to apply:** when he's unsure about the look, a parallel bake-off of many directions on one build (then he picks) worked better than iterating one design.
**Show the flow and the win (2026-09-28):** after recording the HubSpot Spatial page he said it didn't show enough of what the system does. Every page now opens with a numbered flow strip (what comes in → then this → then this → the win) and has a before/after "Today vs With this system" panel before the builder. Calling it a "prototype" on the Loom is fine.

**Finished product is the standard (2026-09-28, late): APPROVED.** Lorenzo on the three examples: "these look fucking perfection lets save all of these." Format = Spatial look, hero, 3-5 finished screens of the live system, the platform screen (illustrative), close. No audit, flow strip or before/after. References: `upwork-pipeline/jobs/_examples/finished-{ghl,make,clickup}.html`; brief `_REEL_BRIEF.md` UPDATE 4.
**How to apply:** each page took 13-19 min from scratch, which he flagged. Run a batch's pages in parallel (wall time = one page) and have each agent copy the closest reference page rather than rebuild components.
**Reference kit (2026-09-28):** 15 finished-product pages in `upwork-pipeline/jobs/_examples/` (ghl, make, clickup, n8n, notion, pipedrive, claude-code, grok, hermes, zapier, voice-agent, hubspot, clay, cold-email, airtable). Newer ones are DATA-driven (one `const DATA`), so a real job = copy closest page + rewrite DATA. Hermes UI partly inferred; Grok/voice model names are placeholders to update per job.
**Inputs and outputs first (Lorenzo via Nick Saraev, 2026-09-29):** clients care about what goes in and what comes out more than the middle. Same layout, plus an In → Out band after the hero, INPUT/OUTPUT eyebrows on the first and win screens, and In/Out tags on the builder. Brief UPDATE 5. Change as little as possible; he said "we got to a really great point".
**I/O pilot approved (2026-09-29):** finished-ghl.html has the In → Out band, INPUT/OUTPUT eyebrows and IN/OUT builder tags; Lorenzo: "looks great". The other 14 kit pages are still to do; he said "we'll apply later today". Use finished-ghl as the pattern.

**UPDATE 6, 2026-10-02 (approved, "that's perfect, ship it"):** every new page opens with the goal on one 1440x900 screen. Headline, then "A system built around one clear goal: <result>.", then a goal card (big monthly number, the math in one sentence, stated assumptions, three editable inputs marked "Illustrative · we'll use your real numbers"), two small metrics, Scroll. No .sub sentence, no floating hero cards. Reference: `jobs/_examples/pilots/impact-hero.html`. **Why:** he wants each page to sell a business result (dollars or hours), and attention drops in the first seconds, so the goal goes first rather than at the end. Numbers are the client's own math, never industry stats. Proposal copy unchanged. The 15 kit pages don't have it yet; agents copy the hero from the pilot.

**Currency (2026-10-02):** pages always show US dollars, even for clients abroad (a Malaysia job came out in RM; Lorenzo is American and wants $).

**Goal statement (2026-10-03):** the goal card big line must read as the outcome ("+$15,000 a month" / "in revenue won back from ...", or "12 hours a week saved" / "on ..."), not a bare "$15,000/mo" under "The goal, a month". Lorenzo found the bare number confusing.

**Call screen ending (2026-10-03):** every page ends on the 15-minute call CTA (It is built, let us switch it on; software/process/numbers cards; Reply on Upwork pill) instead of the 4-word close. He talks the call over that screen at the end of the Loom.

**2026-10-04:** final screen is a single "Next step / A 15-minute call." panel (no cards); pages cap at 4 finished screens, each goal-oriented and problem-focused. Both in _REEL_BRIEF UPDATE 6 notes and the batch brief.

**Value-equation lines (2026-10-04):** Next step panel adds "Live fast: Draft live in 3 days. Full build in 7 to 14 days." and "Your part: One 15-minute call. I handle the rest." (2026-10-05: onboarding call dropped, fewer steps; testing on this batch, keep if it holds) (time delay + effort). He declined adding on-page proof and guarantees.

**UPDATE 7 (2026-10-06, Lorenzo):** the platform screen must look like the software the post names (Claude Project/Claude Code, GPT editor, AWS console, n8n/Make canvases), never a GHL-style canvas for everything; the Next step sub line + Live fast box must fit the post (build / fix / ongoing / live sessions / audit). Rules in jobs/_REEL_BRIEF.md UPDATE 7.

**Canonical doc (2026-10-09):** Coding/upwork-pipeline/UPWORK_PROCESS.md holds the whole current process (for Codex too); update it whenever a rule changes.
