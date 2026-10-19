# Private assessment and content evidence

Job: AI Agent Developer & Automation Engineer
Upwork: https://www.upwork.com/jobs/~022112195798820744982
Source: `jd.txt` and `intake-private.json` in this folder, captured 19 October 2026.

The post requests technician calls and emails, order intake, data entry, reporting, LLM/API integration and a documented system the client can manage independently. It names n8n or Make as examples. The demo proposes n8n and a custom project workspace; it does not assert an existing client stack or infer the client's industry from unrelated history. No client first name is evidenced, so personalization is omitted.

## Frozen sample path

All people, addresses, events, transcript, completed actions and counts are invented illustrative sample data. Completed sample states depict the requested automation result. They do not claim that an actual account was connected, a real call/email occurred, or a database was changed.

1. Taylor Reed requests inspection of two units at 18 Sample Lane, Suite 204, on 22 October 2026, 1pm to 3pm CT. Original event EVT-642-A for order ORD-642 lacks access instructions.
2. Missing access holds that event for operations reviewer Casey Morgan and stops order entry and outreach for that event.
3. Casey verifies front-desk access with Taylor, records the correction and resubmits EVT-642-B on the same order.
4. The successful illustrative n8n route receives the corrected event, extracts fields through a conceptual LLM HTTP Request, checks required fields, and calls a conceptual dispatch integration. Its depicted result writes ORD-642, completes the technician call, sends the email and updates dispatch reporting.
5. Completed call CALL-642-B includes Jordan Ellis confirming the same inspection/window. Sent confirmation EMAIL-642-B carries the same order, site, access and window.
6. The written record shows the held original, verified correction, persisted fields and technician-confirmed status. The report links both intake events, completed call and sent email to ORD-642.
7. The client handover plan includes a workflow export, editable field map, client-owned credential setup, failure fixtures and pause/retry guide. Acceptance includes changing a field map, replaying the complete event without duplicate order creation, then removing access and confirming the held result.

No extra human release/approval gate is invented on the successful path. Casey's review is limited to correcting the incomplete intake. All four scenes are required on Quick: compact n8n workflow, completed outreach, written order/correction history, and dispatch report/handover.

## Compact workflow

Five nodes across four ranks: webhook → HTTP extraction → If required fields → HTTP dispatch integration; false → Edit Fields hold. The successful sample route contains four steps. Resolved node details are at most 120 characters. Detailed calling, email, entry and report results are in the required custom workbench scenes. This content-only change addresses the independent desktop review's small-label finding on the previous seven-rank generation.

The single dispatch integration node is a conceptual orchestration action, not a fabricated native n8n connector or a claimed vendor endpoint. HTTP Request is the supported native n8n action. Actual calling, email, LLM and order/report provider adapters, endpoints, credentials and event contracts remain discovery work. No endpoint is fabricated. Provider-specific concerns belong here rather than obscuring the sample result on screen.

## Proof, metrics and private intake

The visible proof value remains the controller's concise ORD-642. It is sample proof only, not a past-project result or executed integration receipt. Three directional close metrics define time to confirmed dispatch, validated order completeness and technician response rate. The baseline note, opening caption and 15-minute CTA remain exact. No rates, pricing, delivery dates or improvement promises are included.

Private captured client metadata: $74,147.78 spend, 11 total contracts, one active contract, seven feedback entries with score 5, 6% hire rate, 27 Connects required and not applied at capture. The work-history list is a sample. Bid amounts have unspecified units and are not used as market rates. These metadata are not placed in public scenes. The post asks for portfolio, pricing and timeline; the controller owns the locked proposal, and this spec invents no experience or commitment.

## Validation and remaining work

Direct schema validation passes against current platforms.json. Content self-review checked exact ID/caption/CTA, resolved nested tokens, five-node/four-rank shape, short node details, source privacy, completed sample actions, required Quick scenes, concise proof value and supported adapter keys. This is self-review, not independent approval.

No page generated, queue command, shared asset edit, live write or external call was performed. The controller must rebuild and independently review the changed generation; the earlier generation's review is obsolete.

No additional presentation adapter is needed. Remaining production discovery: actual order/report system and schema, LLM provider/extraction constraints, phone/email providers and result events, authorized recipients/contact rules, source for corrections, retries and duplicate prevention, client credential access and support boundaries. Main must still assess visual fit and route behavior on the rebuilt page.
