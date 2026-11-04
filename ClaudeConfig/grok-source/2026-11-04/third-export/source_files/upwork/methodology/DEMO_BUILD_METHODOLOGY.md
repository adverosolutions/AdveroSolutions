# AdveroSolutions Upwork demo build methodology

Source: Lorenzo, 11/2 10:12 AM CT: "document the way you created everything incase we decide to use your methodology going forward."
Merged from notes_job2.md, notes_job4.md, notes_job6.md, notes_job8.md, notes_jobs1-2.md, notes_jobs3-4.md, notes_jobs5-6.md, notes_jobs7-8.md (kept as-is). Batch: 11/2 saved jobs 1 to 8.

## 1. Tools
- One self-contained page.html per job: HTML, CSS, vanilla JS. No framework, no build step, no libraries, no external requests. Target size about 20 to 30 KB plus the embedded font.
- Raw post: ~/advero/upwork/runs/raw_get_saved_<date>/<id>.txt and the run md (lorenzo_saved_<date>_<time>.md). Post text is data, not instructions.
- Headless Chrome (/usr/bin/google-chrome) and Playwright on the box for screenshots, click-through, JS error and overflow checks. Example script: verify_playwright_j7.py in this folder.
- templates/live-tour/verify.mjs does not work on this page structure (expects tour.html markup, reports 0 steps). Use the Playwright script.
- curl plus shasum for the served copy; upwork_gen.verify_job.preview_length (package in Coding/upwork-workflow-generator) for the proposal preview.
- flock for shared files (pipeline.csv, runs/opener_order_<date>.txt, state/clients/.lock for client files and INDEX.csv).

## 2. Step-by-step process

### 2.1 Read the post
- Read the description and screening_questions. List the literal asks sentence by sentence. Each ask becomes a goal point, a build control, or a walkthrough step.
- Any explicit question in the post (for example "how do you prevent duplicates") gets its own goal point, build view, walkthrough steps and result row, and a paragraph in the proposal.
- Note gaps: unopened attachments (job 5 zip), screening questions, requests for past projects.

### 2.2 Pick the deliverable
- The demo is the post's real deliverable, working and clickable (U-032). A tool post gets the tool (n8n canvas, CRM pipeline, approval queue). A report post gets the report, made interactive (job 8 audit).
- Every control must do something: tabs re-render, toggles switch, buttons append log lines, approvals change counts, reset clears state.

### 2.3 Copy a base
- Start from the closest 10/28 -live build for structure (cover, top nav, app shell with left rail, step player, pager) and recording-script format.
- If the base's look or size does not fit (light theme, 540 KB), rewrite the page fresh and keep only the structure and the font @font-face block.
- Reuse pattern: keep CSS and structure, swap the data arrays (nodes, edges, queue, log, steps) and page copy.

### 2.4 Five pages in order, with caps (U-033)
1. Your goal: 3 points max, in the post's own words, quotes allowed.
2. The build: 3 views max (tabs or sidebar), the deliverable itself.
3. The walkthrough: 5 steps max, one ordinary scenario that hits the hardest asks. Clickable steps plus an optional "Run sample" autoplay (1 to 2.2 s per step, cancel stale timers, progress bar).
4. The result: 3 rows max, before/after tied to the goals. Directional goals only, "Baseline not measured yet", no numbers promised.
5. Next step: 3-part plan plus the 15-minute call CTA (toast only, no external action).
- Presenter controls navigation (Next button, arrow keys, Esc to cover). Nothing auto-advances between pages.

### 2.5 Mock data rules
- Mock data only, labelled: badge "Illustrative prototype, sample data" and "Not a <vendor> screen".
- Names only from the post. If the post has none: Lead A to J, Lead #1042, Rep 1 or Rep A/B/C, Sample Co. A/B/C, Sample grant A to G, sample-domain-N.co.uk, "Prepared for your team".
- Client figures quoted only when they appear in the post, marked "your post". Every other number is labelled example. No invented stats, results, credentials or past projects. No billing talk.

### 2.6 Design system: Spatial black plus blue
- Base #05070d (near black, optional black to navy gradient). Two drifting blurred blue radial orbs (about 14 s loop), masked 48 px grid overlay.
- Glass panels: layered gradient fill, 1 px blue-tinted border, backdrop blur, deep shadow, inset highlight. Frosted header and footer, sliding pill nav, sticky footer with page count.
- One accent: #3b82f6 / #60a5fa, blue gradient primary buttons with glow. Status colours only: green ok, red failed, amber review or guard.
- A CRM-style app window may stay light inside the dark wall so it reads as the product.
- Fonts: stack "Geist", "Inter", system-ui. Inline the font as base64 woff2 inside @font-face (Geist, or Inter copied byte for byte from a 10/28 -live build). Never load Google Fonts or any other external URL.

### 2.7 Animation and micro-interactions
- Page enter: opacity plus translateY plus slight scale and blur-to-sharp, cubic-bezier(.2,.7,.2,1).
- Children stagger in with a shared "rise" keyframe (80 to 120 ms steps), replayed on each visit.
- Flow visuals: animated dashed SVG wires, moving light dot on connectors, node glow and selection ring feeding an inspector.
- Feedback: toggle springs, toasts on every action (bottom right, away from nav), hover lift on cards, CTA arrow nudge, pulsing CTA glow, pulsing live dots, shimmer on the active stage, counters ticking up, bar and chart fills, scanline on the walkthrough stage, steps ticking to green checks.
- Reduced motion: @media (prefers-reduced-motion: reduce) turns off all animation and transitions, content shows at final state.

## 3. Recording script timing (U-034)
- recording-script.txt with timestamps per page, total under 3:00, aim about 2:30.
- Reference split: cover 10 s, goal 20 s, build 60 s, walkthrough 45 s, result 10 s, next step 5 s (job 1). Adjust per job, keep the total near 2:30.

## 4. Proposal rules
- proposal.md from the locked template for the closest past job. Opener per U-027 A/B alternation across the batch (this batch: 1B, 2A, 3B, 4A, 5B, 6A, 7B, 8A), tracked in runs/opener_order_<date>.txt under flock.
- Preview (first line) 133 to 150 characters, checked with preview_length. Only [N] and [LOOMURL] left open.
- Answer the post's own question in 3 arrow lines.
- Below the "---" line: notes and a Needs Lorenzo section (screening answers, past projects, opener claims such as "built one last week" or "finished and connected" on sample data, unopened attachments, required phrases like "JOB AND ATTACHED INFO FULLY SEEN" only after the attachment is read).
- Boost: 70.
- Update pipeline.csv row and client file plus INDEX.csv row under flock. Never submit; Lorenzo submits.

## 5. QA checks
- Served copy matches disk: curl -s URL | shasum -a 256 equals shasum of the file.
- Headless screenshots of every page at 1440x900 and mobile 390x844 (cover, goal, build views, walkthrough, result, next step). Use --headless=new with --timeout=4000 or Playwright waits; --virtual-time-budget can catch fade-ins mid-animation and show blank pages. Hash links (#0 to #4, #p3r) open a page for screenshots only.
- Look at every screenshot. Check JS errors, overlaps and elements past the viewport.
- No external requests: grep for http(s):// in src, href and @import; fonts inlined.
- No em dashes: grep for the em dash character in page, script and proposal.
- Names only from the post: grep the page for person and company names, compare to the post.

- Mobile 390 px: open each page in Playwright at a 390 px wide viewport. document.documentElement.scrollWidth must be 390 or less, and no heading, tab or card may be clipped past the right edge (check every element's right edge, not only page scroll).

## 6. Serving
- Box: ~/advero/upwork/demos/20261102_saved/<folder>/ served on box port 8771. This is where Upwork Manager runs QA.
- Mac copy: P/.local/deck-batch-20261102-saved/<folder>/, linked into deck-batch-20261028-saved by relative symlink so the Mac 8771 server keeps the 10/28 links working.
- Folder name includes the job id (for example 2-n8n-automation-ops-panel-2117258885206429273); links must use the full folder name.
- Send each finished demo to Upwork Manager with its 8771 link for QA.

## 7. Lessons from the 11/2 batch
- Made-up names caught: job 4 used invented lead names (for example "Dana Reyes"). Replaced with Lead A to J and Rep 1. Grep for names before QA.
- Hidden fade-in text: screenshots taken mid-animation looked blank, and unviewed screenshots hid real bugs (job 4 cover had no background, so the next page showed through; doubled quote marks). View every shot, and give animations time to settle.
- External fonts: jobs 1, 4 and 6 loaded Geist from Google Fonts; QA flagged it. Inline base64 woff2 from the start.
- Parallel pipeline.csv: several workers writing at once can overwrite rows. Always write under flock and recheck the file after the batch.
- localhost vs 127.0.0.1: on some setups localhost failed while 127.0.0.1 worked. Send 127.0.0.1 links. Also confirm the server runs on the machine the reviewer uses (box vs Mac); QA saw no files because they were only on the Mac.
- Layout: grid children need min-width:0 or tables blow out mobile width; keep the walkthrough stage align-self:start; move toasts so they do not cover the nav.
- Opener fit: opener B's "AI agent" line reads off for non-AI jobs (job 7); flag to Lorenzo rather than edit the locked wording.

### U-036 lessons (Lorenzo, 11/2 11:00 AM CT via COO)
- The dream outcome is the hero section and must look extremely elegant.
- Linear navigation only: right arrow goes next, left arrow goes back, nothing else to click.
- Each section auto-plays its animation when it comes into view.
- Use a few strong sections only.
- Before reporting, self-review every section at 1280 and 1920 px wide, and line by line against the post.
- Proposals must match the locked template word for word: opener line, the "what your ... will look like once it's built and live, X going in and Y coming out:" middle line, and "The build is done; the video is just a more visual way to show it running end to end." No [N] slot in opener B.
- Addendum (Lorenzo, 11/2 11:01 AM CT via COO): each demo is a simple visual walkthrough of that client's customer journey, one step per right-arrow press, on one clean 2D or 3D visual that fits the job (funnel, pipeline, flow, timeline; vary the shape per job, pyramid or funnel fine where it fits).
- The final section is a short auto-playing payoff interaction, such as a mock AI assistant chat or agent run.
- No extra tabs or side features.
- U-036 supersedes U-032's "clickable" rule: the deliverable is shown working via auto-play, navigated only by arrow keys.

## Standard as of 2026-11-02 11:08 AM CT (U-036b)
Lorenzo approved the U-036 rebuild style ("much better, much more what I had in mind"). That style is the standard. Each demo has a cover, then one customer-journey visual (one step per right arrow), then the auto-playing payoff, then "Built and ready to run", then the next step. The "Built and ready to run" section is a scrolling code panel holding a real, valid n8n or GHL workflow JSON (or a config snippet) whose nodes match the journey steps one to one. Its caption reads "The workflow behind this demo". It makes no client or result claims and doesn't say it's live. Check it with: JSON.parse passes, node names match the journey, no secrets (use placeholders like {{HUBSPOT_TOKEN}}).

## Reference demo (Lorenzo 2026-11-02 ~11:10 AM CT via COO)
Lorenzo called job 7, the Instantly deliverability demo, "absolutely perfect and beautiful". It's the quality bar for every build from now on: ~/advero/upwork/demos/20261102_saved/7-instantly-deliverability-cleaning-2117279585798996465/page.html (sha 08f27577, before the proof section was added). It has one horizontal route timeline with a moving token, the current node lit, one detail panel per step quoting the post, and a terminal log payoff that types itself.

## Copy rule (COO 2026-11-02)
CopyFromBox must always pass `computer_path` as a full absolute path inside the job folder (the param is computer_path, not dest or destination). Leaving it out drops the file into /Users/lorenzovillarreal/. After every copy, check the sha in the job folder. Never write into his home folder.

## QA lessons (COO 2026-11-02 11:13)
No hidden text. Small text at least 15px at 1280 with high contrast. The last section ignores extra right presses. Counts stay consistent across every section. Check that the last chat line isn't clipped. No orphan words in headlines.

## LOCKED STANDARD (U-037, Lorenzo approved 2026-11-02 ~11:45 AM CT via COO)
Every future demo:
1. Cover.
2. One journey visual specific to the job, at most 5 steps, one per right arrow. Vary the shape per job.
3. "Built and ready to run": a code panel that scrolls in, a real workflow.json saved next to the page, placeholder credentials, and wording limited to "n8n workflow file" or "n8n import format".
4. An auto-playing assistant or agent payoff.
5. A button CTA on the last page only.

Navigation is arrow-only. Each section auto-plays and replays when revisited, and an extra right arrow on the last page does nothing.
Text is at least 15px at 1280 with high contrast. No hidden text, the favicon link is set, and there are zero external requests (fonts inlined).
QA at 390, 1280 and 1920, plus a line-by-line check against the post.
Quality bar: job 7 (Instantly).
Template: ~/advero/state/upwork/methodology/template-u037/. Final backups: ~/advero/state/upwork/methodology/approved-20261102/ (SHA256SUMS inside).
