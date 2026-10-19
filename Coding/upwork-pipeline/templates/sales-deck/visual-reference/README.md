# Native screen reference library

Requested by Lorenzo on 19 October 2026 after rejecting the seven-job batch's
visual quality. This package is research and a visual production plan. It does
not certify the existing adapters or restart any proposal jobs.

Open `index.html` for the local visual board. `catalog.json` contains the product
and screen plans; `references.json` contains curated image provenance and hashes.
`research/source-evidence.json` records successful and unsuccessful source
retrievals, including excluded candidate imagery. A vendor page being current
does not make every screenshot on it current. Historical captures and cropped
details are labeled explicitly.

## Product identity before layout

The priority scope includes n8n, Make, Zapier, GoHighLevel, Claude, Claude Code,
Codex, Hermes, regular Grok, Grok Bot, Cursor, Orca IDE and Antigravity. Lorenzo
clarified Orca as an IDE; the identified product is onorca.dev, not Orca Security
or a similarly named agent service. Additional plans follow actual demand in
the local job corpus; the watchlist handles the remaining common categories.

For every job, identify **product + surface + edition/version + theme** first.
Examples: Claude Customize > Skills versus a Claude Project versus Claude Code;
Hermes Desktop versus CLI versus Web Dashboard; Zapier visual editor versus
Next Gen Workflow Manager; Zoho CRM versus Flow or Creator. If the post does not
settle a distinction that changes the UI, resolve it before choosing a renderer.

Never substitute a supported adapter for the named product. A custom internal
dashboard is appropriate only when the job requests one and it is labeled as
custom. An API implementation may need a real request/result and the destination
application rather than a fabricated vendor canvas.

## Readiness is separate from research coverage

All current entries have `productionReady: false`. This is deliberate: the
existing batch was rejected, and no replacement native renderer is implemented
or accepted by this research task. Downloaded references are not completed demos.

Each product must pass these stages in order:

1. Identify the exact product/surface from the original post.
2. Obtain current full-workspace and relevant detail references. Record source,
   captured/checked date, edition/theme/version when known, and image hash.
3. Write the screen/state map and the client's sample input/output requirements.
4. Implement the correct native interior in isolation, preserving the approved
   outer presentation palette, typography, opening and closing CTA.
5. Compare the implementation with the reference at the same viewport. Inspect
   full navigation, chrome, controls, geometry, app icons, typography and state.
6. Check the visible business result, data consistency, replay and navigation.
7. Run one focused independent Astra High review. Record exact artifact hashes
   and the scope checked. Accept that exact native template only after defects
   are resolved. The actual prospect demo still needs its job-specific review.

The reference board shows missing imagery and remaining implementation work.
Do not convert a documentation-only entry, a historical screenshot, or a cropped
menu into a green production status. No current renderer is made visually ready
by the old `platforms.json` technical `supported` flag.

## Research and prioritization

`research/local-demand.json` counts each tool at most once per deduplicated
original post title/body with a real Upwork URL. Metadata, example folders,
duplicate jobs and eight sources without Upwork URLs are excluded. This is
Lorenzo's selected historical corpus, not a representative sample of all Upwork.
Mentions overlap. Bare Make is conservatively excluded to avoid counting the
ordinary verb; its count understates jobs that use that shorthand.

`research/public-demand.json` holds separate public-market signals. Category
pages were discoverable in search but some direct fetches returned 403. Their
displayed sample counts have mixed crawl dates, overlap and include non-build
work. They are labeled search-index signals, not live totals or market shares.

## Reproduce and maintain

```sh
/usr/bin/python3 analyze_demand.py
/usr/bin/python3 build_catalog.py
/usr/bin/python3 build_board.py
```

`collect_references.py` uses the bundled workspace Python with Pillow. It fetches
only public pages/assets and saves original image bytes. It produces candidates,
not automatic approvals. Its raw output must be curated manually into
`references.json`; do not overwrite that selection or trust the first images on
a page. Some primary reference images are frames captured from official videos;
their timestamps are recorded. No AI-generated screenshot is source evidence.

The reference board works directly as a local HTML file. Browser QA uses an
isolated headless session and never the user's signed-in profile. This package
is not served by or registered into the live recording queue.

Before adding an unfamiliar product, follow the same stages above. Add its exact
surface and evidence to the catalog; do not invent a fallback. Recheck references
when the vendor UI, target account, edition or theme changes. Use
`../OPERATING_POLICY.md` to keep research and template work outside time-sensitive
daily generation and to avoid repeated Astra coordination.
