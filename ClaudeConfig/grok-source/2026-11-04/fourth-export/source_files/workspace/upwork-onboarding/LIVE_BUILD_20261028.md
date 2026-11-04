# Live deliverable rebuild brief, 10/28 batch (U-032 + U-033 five-page order)
Lorenzo 11:41 AM CT 10/28 (via COO and Upwork Manager), his words: "we're not actually doing or demonstrating what is being talked about in the post, and we've over-standardized the format. Everything, the way that we walk through builds needs to be the same every single time, but like for this one, number three on the list, they're looking for a reporting dashboard. So instead of whatever we have, like we could just have built a beautiful reporting dashboard, show them through it, be able to click through the tabs, things like that, and the format of you know what the ... first page being about this, the second page being about this, the third page being about this, that's what needs to be standardized. But everything needs to be custom to that particular job."
Also his standing words today: "we need to be flawless today".

GOAL: replace your job's slide deck with the post's ACTUAL deliverable as a working, clickable, beautiful single-page app on sample data (real tabs, filters, switchers, tables, record views, workflow screens that respond to clicks). Not slides describing it. QA gate: "demo shows the post's actual deliverable".

Mac machineId 43321728-d9a1-4b7f-b428-290f6c2304b6. P = /Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/upwork-pipeline. Your job folder P/jobs/<slug>/ already exists (jd.txt, deck-spec.json, proposal.md, assessment-private.md). Raw post also on box ~/advero/upwork/runs/raw_get_saved_20261028/<jobid>.txt. Reuse your own job's content where it helps; do not read or copy other jobs.

STANDARD 5-PAGE SALES DECK (U-033, Lorenzo 11:42 AM CT, supersedes any 4-page order): "make sure it's a sales deck in terms of page one is this, page two is this, page three is this, page 4 is this, page 5 is this. But what's actually on each individual page is completely specific to the job ... everything needs to maintain beautiful, elegant quality, go above and beyond ... walk them through their desired end goal result". Top nav with these 5 pages in this order, names exactly:
1. "Your goal": the client's problem and the end result they want, in their words from the post.
2. "The build": the actual deliverable, working and clickable with real tabs, filters, screens and realistic sample data. No slides describing it. Most Loom time here.
3. "The walkthrough": one realistic scenario run end to end through the build, the way their team would use it day to day (step controls, state visibly changes; fold the automation test run here).
4. "The result": the outcome they're buying, before and after, what changes for them (time saved, nothing missed, visibility). No invented client stats, no numeric promises.
5. "Next step": what happens after the hire, plus the blue 15-minute call button.
Plus a small cover before page 1 with the first line exactly "I've already put this workflow together for you. Let me walk you through how it works." (Prepared for: verified post name only, else business name from the post, else "your team"; names only from the post or chat.)
Quality bar: premium, elegant, beautiful. Go above and beyond.

LOOK (U-016, U-026 legacy look): Lorenzo's Spatial design: palette and tokens from /Users/lorenzovillarreal/Desktop/AdveroSolutions/Brand/tokens/brand.css and the legacy deck's look (see an existing built page in P/.local/deck-batch-20261028-saved/<your slug>/page.html for palette, blue CTA, Inter). Inter font embedded (fonts are in P/templates/sales-deck/assets or the built page; inline as base64) so there are NO remote requests. Layered, polished, product-grade UI. Desktop 1440x900 first, also usable at 390x844. Keyboard: arrow keys / Next-Previous move between the 5 pages; nothing auto-advances.
Vendor screens: show the platform the post names in a look that reads as that product's in-account view where the post demands it (e.g. GHL in-account dashboard), but do not copy logos or trademarks; label "sample data" once. Mock data only, consistent sample names unique to this job (grep P/jobs/*/deck-spec.json and other 10/28 builds to avoid reused names).

OUTPUT: single self-contained file P/.local/deck-batch-20261028-saved/<slug>-live/page.html (create the folder; leave the old slide deck folder untouched). It is served at http://127.0.0.1:8771/<slug>-live/page.html (server already running; check curl 200). Also save a short recording-script.txt beside it (what to click, in order, ~2 minutes, most time on "The build"). Do not use the recording-queue CLI for this page (it only takes compiled specs). Do not touch templates/, DIRECTIVES.md, Upwork, git, or other jobs.

PROPOSAL: proposals stay word for word from the template except the open fixes listed in your task. Back up proposal.md to proposal.pre-live.md first if you touch it. If the "The video walks through" sentence no longer matches the new demo, do not edit it; flag it in your report with suggested wording. Preview check: /usr/bin/python3 -c "import sys; sys.path.insert(0,'/Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/upwork-workflow-generator'); from upwork_gen.verify_job import preview_length; print(preview_length(open('P/jobs/<slug>/proposal.md').read()))" must be 150 or under. Above --- only [N] and [LOOMURL] open. No em/en dashes, no price words.

QA (fix until all pass): headless Chrome on the Mac or box at 1440x900 and 390x844: every page and every tab/filter/switcher clicked, no console errors, no remote requests, no clipping or horizontal overflow, nothing cut off, all text readable; read every line aloud once; it must map to the client's stated problem, show the outcome they're buying, match the job, contain no placeholder text. Take screenshots (cover, each of the 5 pages, one mobile) to box /workspace/upwork-onboarding/decks-20261028s/<slug>-live/. CopyToBox page.html, recording-script.txt, proposal.md into ~/advero/upwork/demos/20261028_saved/<N>-<slug>/live/.
Append a client log line "2026-10-28 HH:MM CT | demo-builder | upwork | live deliverable demo rebuilt (U-032), ready to record (<job url>)" to the client file and upsert INDEX.csv under flock ~/advero/state/clients/.lock.

Speed matters: aim for about 20 to 25 minutes. REPORT in at most 8 lines: 8771 link, what is clickable on each of the 5 pages, proposal changes + preview length, QA results, page SHA-256 of the served 8771 page, box folder, flags for Lorenzo, STATUS: ready to record | blocked: reason.

LENGTH RULE (U-034, Lorenzo 12:16 PM CT, overrides anything above that adds more): "Is there any way we can shorten just what's on the screen just a tad? ... we want to make sure that I can record them in like less than 3 minutes ... condense just slightly." Every deck records in under 3 minutes, target about 2:30. Same 5-page order and premium quality, fewer things on screen. Caps:
- P1 Your goal: 3 points max, ~20s.
- P2 The build: 3 views/tabs max (the strongest), 1-2 working controls each, ~60s.
- P3 The walkthrough: one scenario path, 5 steps max, no side branches, ~45s.
- P4 The result: before/after, 3 rows max, ~15s.
- P5 Next step: CTA only, ~10s.
- Cut extra callouts, drawers, secondary panels. The cover stays one short screen.
recording-script.txt must be timed: a timestamp per page (e.g. 0:00 Cover, 0:10 Your goal, ...), total about 2:30, pointing at the 8771 URL.
Keep every QA fix already made. Every name, date and status must stay consistent after cuts (nothing referenced that was removed).
Proposal: do not edit. If the "video walks through" line no longer matches the condensed demo, report a revised line (template opening kept, 4 to 6 items) for Upwork Manager; do not apply it.
