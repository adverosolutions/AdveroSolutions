# Private assessment and requirement mapping

Prepared 2026-10-19. This file is private provenance, implementation questions and proposal preparation. It is not public demonstration copy. No proposal file was authored. The public deck is an illustrative route, not delivered software or an authenticated integration.

Applied Lorenzo's `lorenzo-voice` and `claudeisms` skills to the visible copy. A separate self-review found the sample IDs, facts, revisions and route coherent. This was not an independent review; main retains build and independent page review.

## Observed website evidence

Read-only `web__run`, 2026-10-19:

1. `https://www.vsre.net/` returned inaccessible via the tool. This is a tool/hostname observation, not proof the site is unavailable to normal visitors.
2. `https://vsre.net/` loaded successfully, title VSRE – Commercial Real Estate Specialists. The page text at lines 18 and 27 included navigation labelled “Availabilities”. Lines 203–207 showed an Explore our portfolio section and a “Check Availability” link. Following link 11 led to `https://vsre.net/availability/`.
3. `https://vsre.net/availability` redirected to `https://vsre.net/availability/`. That page loaded, title Availability – VSRE. Its extracted text at lines 31–32 showed the hero “Prime opportunities, tailored to match your needs.” The remaining extracted content was navigation, image references, newsletter/contact/footer and accessibility controls. It did not expose listing rows, specifications, pricing, availability records or a listing photograph inventory.
4. No API, feed endpoint, CMS type, listing provider, embedded widget or listing-photo mapping was verified. The absence of listing rows in this extraction does not establish absence of listings on a rendered page. Do not call the source WordPress, a particular IDX provider, Airtable or a specific feed without inspection/access evidence.

Source URLs: https://vsre.net/ and https://vsre.net/availability/ . Web references in this worker session: turn1view0, turn2view0, turn2view1. No browser automation, screen interaction, scraping script or live write was used.

## Conditional access recommendation

First request the source-of-truth listing system and website administrator's supported export/feed/API documentation. Prefer a documented, authorized direct feed or CMS export with stable listing IDs, availability, updated-at/version information, structured fields and original image references if available. This is a recommendation, not a claim that such access exists.

If no supported feed/export exists, inspect the actual listing detail pages and any authorized embedded provider with the website administrator. Assess permitted page extraction only after confirming rights, completeness, selectors, status semantics and practical change detection. Save source reference, fetch time, facts hash and authorized photo references. Missing/stale/ambiguous availability must hold publication; source fetch failure must not imply withdrawn inventory. Confirm explicit withdrawal versus temporary fetch/page errors.

Validate actual property image access/rights, image-to-property mapping, resolution, ordering, logos/contact details and brand rules. Updated asset contract: the required carousel scene now embeds two actual corporate-website JPEG photographs for a visible graphic layout. Their source is explicitly separated from invented SAMPLE-P101 facts; neither is claimed to depict that fictional property. Production listing-photo mapping, renderer and brand templates remain implementation decisions. No fake image URL is supplied. See assets-private.json.

## Sample route

Every property ID and publishing receipt in the deck is invented SAMPLE data, unrelated to the observed VSRE inventory:

- SAMPLE-P101, SAMPLE Commerce Park, Doral, FL (invented), 12,000 sq ft, 22 ft clear height, 2 grade-level doors, active in invented SAMPLE source, source revision v3.
- SAMPLE-POST-101 revision v3, two sample daily slots 10:00 and 16:00 ET, every day.
- Last promoted SAMPLE-P103; new SAMPLE-P101 takes priority; SAMPLE-P102 next. After completing the active cycle, reset the cycle cursor and generate fresh caption/layout versions. New-listing prioritization should not permanently starve existing listings; agree the practical tie-break/fairness policy.
- Draft two concrete graphic slides and a caption from the sample facts; price absent and omitted. The inlined corporate photos are explicitly labelled as layout imagery and do not depict fictional SAMPLE-P101. Production uses each real listing’s verified photos.
- Manual approval records exact content/source revision v3. Changed text, graphics, regeneration or source facts invalidates approval; content returns for review.
- At the slot, recheck current availability and facts, source freshness, approved revision, pause/mode, due slot and unique post/slot key.
- Successful sample records SAMPLE-MEDIA-101, advances rotation on confirmed receipt, and chooses SAMPLE-P102 next.
- Separate illustrative blocked cases: SAMPLE-P104 withdrawn; SAMPLE-P105 changed to v4; no approved content at 16:00; duplicate attempt for the same key. These are alternate cases, not a claimed executed live test.
- Transient publishing error: bounded backoff retry. Uncertain response: reconcile remote publication/container status before attempting again. Final/permanent failure: alert and leave visible failed status. Do not mark rotation successful from an unconfirmed response.

## Native adapter and screen honesty

Two required compact workflow scenes use Make `custom_webhook`, `http_request` and `router` only. The first prepares source/rotation/draft; the second starts with a distinct due-slot event and checks exact approval/current source before publishing or skipping. HTTP represents conceptual calls to project services and Claude's API; it is not a native Claude or Instagram module. A schedule service/Make scheduling configuration would invoke the orchestration; the webhook is not asserted to be a standalone scheduler. Approval wait/resume is conceptual persisted orchestration, not an in-memory blocking Make run.

Nonworkflow scenes use `workbench` per extension-contract.md and label the screen as custom project output. No GHL substitution. No Meta/Canva/Airtable UI claim. The deck does not implement actual approve/edit/regenerate/bulk/pause controls. Its optional dashboard record expressly lists these as proposed implementation requirements.

Worker ran data-only `schema.validate` against the updated carousel contract: PASS. The coordinator subsequently split the graph into two four-rank workflows: six scenes total, including a required two-slide carousel and required email/SMS draft scene. Worker did not build a page, touch the template lock/shared files, run queue commands or claim readiness. Main handles template freeze/build and independent exact-page review.

## Requirement mapping and secondary details

1. Website listings/photos: required workflow's validate-source step and related source condition; optional dashboard source record. Access uncertainty remains explicit. Real synchronization needs inserts/updates/withdrawals, stable IDs, source hashes, photo change detection and timestamps.
2. Two daily posts seven days/week: required workflow context and result detail. Continuous rotation, new-listing priority, avoid consecutive same property with alternatives, cycle reset and fresh caption/layout variants are required route copy. Scheduling, manual priority and pause/resume are optional dashboard-plan requirements. With only one active property, agree whether to repeat or leave space; do not imply impossible diversity.
3. Claude accuracy: validated source fields only, missing price omitted, explicit revision and source-change blocking. Production should validate structured model output against an allowlist of source facts; unsupported claims return to review. Style prompts must not append summary/tagline copy or restate the prior line, e.g. no “No more chasing leads.”
4. Carousel generation: required carousel-preview scene includes two visible photographic slides, caption/hashtags/CTA and explicitly invented specifications. Corporate photos are labelled separately from the fictional sample listing. The production renderer uses actual authorized photos without adding property features; logo, contact, fonts/colors/layout variants require client assets. No comparable graphics project history is evidenced here, so none is claimed.
5. Approval dashboard: required route enforces exact approval/reapproval and shows approval notification drafts. Optional dashboard record maps preview/edit/approve/reject/regenerate/bulk approve, 14 upcoming posts, scheduling/priorities, status, pause/resume and future auto-mode. Future auto mode is an explicit client setting; retain freshness, withdrawal and duplicate checks. Do not silently enable it after handover.
6. Email/SMS: required scene shows both ready-for-review drafts with a labelled setup-time dashboard-link placeholder. Proposed event types include ready, pending reminder, publication success, posting failure and workflow error; independent enable/disable and frequency. No real dashboard link or provider has been configured, no message sent.
7. Publishing: required route covers due-time recheck, receipt, retry/reconciliation, duplicate guard and empty-slot skip/alert. Authorized Meta API versus compatible provider is unresolved pending account/access constraints; no direct integration was demonstrated.
8. Technology: Make orchestration + Claude API + proposed custom data/review/publishing services is the demonstrated concept, not a final cheapest-stack procurement claim. Choose renderer/database/hosting/email/SMS/publishing services only after source and account audit; do not require every optional platform in the post.
9. Costs: public demo deliberately makes no numerical cost or fixed-price promise. See private cost worksheet below. Mandatory job request remains to resolve with Lorenzo before submission; this demo must not be represented as a full response to the mandatory estimate questions.
10. Ownership: optional dashboard record maps client-owned workflow exports, source code, templates/configuration, admin access, operating docs, training and recording. Build in client-controlled accounts, disclose third-party licenses and avoid dependency on freelancer accounts. No required monthly freelancer involvement is promised by the demo; actual support terms require Lorenzo's decision.
11. Milestones and acceptance: source sync; content/rendering; review/notification workspace; publishing and tests; docs/training/handover. Working end-to-end proof must use authorized accounts and verified source content before final acceptance. No timeline promise given.
12. Scope: automation system, not ongoing social media management. Branded graphic assets and API permissions need validation; these are implementation gates, not tasks already delivered.

## Thirteen proposal questions: private answer status

1. Similar work/examples/role: no verified directly comparable carousel implementation supplied. Public deck uses visible SAMPLE proof only. Lorenzo must provide any real portfolio claim.
2. Recommended stack/why: preliminary Make + Claude + custom review/data/services; reduce subscription count after source/account investigation. No claim this is already priced as the least expensive option.
3. Retrieve/sync vsre.net: observed shell and availability URL only; conditional documented feed/CMS access first, permitted extraction fallback only after inspection.
4. Claude/inaccurate information: structured source-only generation, omit missing data, fact allowlist, revision review and publish-time source hash.
5. Branded carousels: real text sample plus proposed photo/template renderer, brand assets and rendering validation outstanding.
6. Rotation/new properties: persisted cycle cursor, new-first priority, all active listings before repeat, avoid consecutive when alternatives, vary copy/layout.
7. Dashboard/notices: proposed custom review queue, 14 upcoming posts, review/batch/schedule/mode controls; draft email/SMS and independent notification preferences.
8. Unavailable/missed approvals/errors/duplicates: block withdrawals/changes/stale source, skip empty slots, bounded retries and uncertain-response reconciliation, unique key/confirmed receipt.
9. Instagram setup: verify exact selected Meta login/API path or provider with account administrator. Official documentation unavailable below; do not invent permissions.
10. Timeline/fixed development price: intentionally not promised; Lorenzo decides after source/account/renderer scope. Existing pipeline rules prohibit billing copy.
11. Monthly/annual costs: all categories and assumptions identified below, numerical estimates not researched or authorized for public copy.
12. Independent handover: design for client accounts/credentials and recoverable exported configuration; optional support terms are Lorenzo's decision.
13. Ownership/admin: full applicable exports/source/templates/admin and license disclosure are acceptance requirements, not present deliverables.

## Private operating-cost worksheet, no price claim

Client says approximately 60 monthly carousels. Two per calendar day actually varies from 56 to 62 by month, so show the billing period assumption when estimating. Sample has two slides; real slides/post, draft horizon, regenerations and retries must be agreed.

Required estimates to obtain for the selected stack:

- Claude API: listing summary input + caption/layout text output per draft, variants/regenerations, model and token usage, retries; do not infer runtime model or price from other jobs.
- Make: sync polling/change events, per-post orchestration operations, approvals/resumes, due checks, rendering and publish status polls, error retries. Daily schedule alone is not the full operation count.
- Graphics: per rendered image/carousel, slide count, layout variants, regeneration and asset/license charges; local renderer versus paid service must be selected.
- Dashboard/database: row/storage limits, users, review/authentication and 14-post horizon.
- Hosting/storage: API worker hosting, persistent state/database, original and rendered images, backups and egress.
- Email/SMS: ready notices, pending reminders, success/error alerts, digest/frequency choices; SMS carrier/registration fees if applicable to selected provider/region.
- Publishing: direct Meta path versus compatible publishing provider subscription/limits, account count and supported carousel workflow.
- Extra APIs/licenses: website feed/provider access, fonts/templates/design licenses or other required services only when verified.
- Separate mandatory/optional items; one-time setup/development, monthly run rate, annualized estimate, usage sensitivity, optional maintenance and any required ongoing involvement. Never invent current vendor prices.

No itemized dollar estimate, fixed price, annual total or timeline is claimed. This is a known unresolved mandatory post request for Lorenzo/main, not something to hide with a general “low cost” claim.

## Meta source attempts and uncertainty

Read-only official-documentation attempts on 2026-10-19:

- https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/content-publishing/ returned inaccessible via web tool.
- https://developers.facebook.com/docs/instagram-platform/content-publishing/ returned fetch failure, HTTP 429.
- Official-site search queries returned no usable results in this session.

Therefore no exact professional-account type, Facebook Page linkage, permission name, app review requirement, carousel limit, supported scheduling feature or API fee is asserted as verified. Login path/provider, account eligibility, administrator ownership, granted scopes, app review/access level, token renewal, image hosting requirements, rendering constraints and endpoint behavior must be checked from current official docs during implementation. Do not conflate Instagram Login and Facebook Login requirements.


## Asset update after actual-photo requirement

Main supplied two observed home-page image URLs. Worker downloaded each unchanged, inspected both with view_image, embedded the source JPEG bytes in a required workbench carousel, and validated the updated spec. One image is an aerial photograph of an industrial building, the other an office-interior photograph. Neither has verified listing identity or SAMPLE-P101 association. Details, URLs, byte counts and hashes are in assets-private.json. A historical Countyline brochure rendering and site plan were also extracted as evidence but are not used as actual photographs. The brochure cannot establish present availability.

The deck retains main’s shortened footer, result proof and notice edits. Email/SMS drafts are a separate required compact scene. No page was built by this worker and no queue/shared files were modified.
