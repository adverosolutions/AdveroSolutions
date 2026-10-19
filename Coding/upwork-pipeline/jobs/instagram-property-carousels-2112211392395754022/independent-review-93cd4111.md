# Independent review — APPROVE

Job: instagram-property-carousels-2112211392395754022
Reviewer: independent review agent `/root/tokyo_review`
Canonical artifact: `.local/recording-queue/public/jobs/instagram-property-carousels-2112211392395754022/page.html`

Exact reviewed identities:
- Page SHA-256: `93cd4111b7fe4b09aa4af511b70959b1278cf75f4d11d08b535635ba723e26e0`
- Public content SHA-256: `c3742bd1f29d925bb0b066f708b6273e28f821d4a645f3b0a4ae554b6cd9e3e0`
- Normalized spec SHA-256: `0d4b381ffc590f024ebd0940c3c2dcdff3b0e055933c47f3dabac423c2d05380`
- Template SHA-256: `4dbfdc2ccb27f33075070264178cfdf993572c437c003fbbc5d866d0addd3806`
- Recording script SHA-256: `70c86a75416485b94770bb9863ddad0ad8ec1a44798975df7818f110a7c3ac51`

The current normalized spec and public content independently validate. The template lock matches its actual files. In-memory page and recording-script recompilation exactly match the canonical files, and every hash matches the current build report. No generated file, spec, template, proposal, or queue state was edited by this reviewer.

## Evidence and provenance

I independently inspected the original post, spec, generated script/report, private static handoff `review-static-private.json`, sample continuity, and saved screenshots. The separate static reviewer supplied private assessment and photography provenance evidence. My earlier IAB session became unavailable (`Browser is not available: 2`) before this job. The coordinator captured screenshots and interaction evidence through its working hidden IAB; I independently reviewed those pixels. I did not personally operate the Instagram browser, and do not claim that I did.

Initial complete visual evidence is in `.tmp/review-c4813415/`: desktop cover, both native Make workflows, both carousel slides, notifications, result, optional dashboard, close, and mobile cover, both workflows, both slides, notifications, result and close. I viewed those screens, plus `mobile-carousel-auto-settled.png`. The coordinator's `browser-evidence.json` records the runtime checks described below.

That generation was rejected for a specific mobile result defect: the long SAMPLE-P102 metric value clipped in its narrow card. The sole reported public content repair shortens the visible value to P102 and preserves SAMPLE-P102 in the note. The script and template remain byte-identical. The current spec and current mobile result independently confirm that correction.

Fresh screenshots for the final generation are in `.tmp/review-93cd4111/`. I inspected `mobile-the-result.png`, `desktop-result.png`, `desktop-prepare-workflow.png`, `desktop-publish-workflow.png`, and `mobile-success-measures.png`. The corrected P102 value and full SAMPLE-P102 note fit cleanly. Both desktop workflows remain readable, and the mobile close retains the blue CTA. The complete unchanged-scene review and interaction evidence above are carried forward explicitly; the fresh generation's browser-evidence JSON was an empty array when read, so it is not represented as a new interaction log.

## Content and visual findings

The demonstration follows source verification, draft generation, carousel preview, approval notices, exact-version recheck, publishing receipt and exception handling. Both workflows use native Make styling and supported Webhooks/HTTP/Router concepts. The approval and result screens are explicitly custom workbench views. Claude is described through HTTP rather than an invented native module.

SAMPLE-P101, SAMPLE-POST-101 revision v3, SAMPLE-MEDIA-101 and next listing SAMPLE-P102 remain consistent. Withdrawn SAMPLE-P104 is blocked; changed SAMPLE-P105 requires approval again; an empty slot skips and alerts; duplicate keys are suppressed. Retry and uncertain-result handling are described without inventing a successful live deployment. Daily scheduling and rotation remain in required scenes. The optional dashboard is Detailed-only.

The two photographs are traced in the private static review to VSRE corporate website assets. On-screen labels, caption and alt text explicitly distinguish those corporate photographs from the invented sample listing. No invented listing fact is presented as verified by those photographs. Missing price is omitted. The static handoff confirms the embedded bytes match the supplied assets and the earlier brochure-plan imagery is absent.

Raydel is used as a supported contact first name, without ownership claims. Public content excludes private source evidence and intake metadata. Counts, receipts and property details are visibly illustrative. Prices, delivery times and production access are not fabricated. Close metrics are directional rather than unsubstantiated numerical promises.

Desktop screenshots are 1440 by 900. Both Make graphs are legible at scale 1. The carousel photos are crisp, their text fits, and captions and notifications remain readable. At 390 px the cover, carousel, notifications, corrected result and close fit. Large native graphs are contained in their own frame. The coordinator observed page scrollWidth 390. Long documents use the workbench's bounded internal scrolling; the full mobile result exposes the lower rows.

The palette, embedded Inter font, opening caption, manual chapter navigation and blue call CTA match the approved shell. No remaining blocking visual defect was found in the final evidence.

## Behavior evidence and limitations

The coordinator's saved log for the unchanged template records Standard 7 chapters, Detailed 8, Quick 7, and no optional Capture button on Quick. It records Talking points expansion, Present class, Escape exit, left/right navigation and Previous/Next. Carousel replay begins at step 0 and naturally settles at step 1 on the same carousel heading. Show result was captured at the final carousel and workflow states. Rapid Replay followed by navigation to the publish workflow holds step 3 and the correct heading after the old timer would have expired. There is no automatic chapter advance in that check.

Reduced-motion settling was inspected in template source; it was not emulated in the browser because the documented interface did not expose a reduced-motion override. Assets are embedded in the generated page and source inspection found no service-write behavior. Runtime network monitoring is not claimed. The coordinator reported the browser viewport reset after capture.

APPROVE applies only to the exact page, public content, spec, template and recording script hashes listed above. The earlier c4813415 page is not approved by this report.
