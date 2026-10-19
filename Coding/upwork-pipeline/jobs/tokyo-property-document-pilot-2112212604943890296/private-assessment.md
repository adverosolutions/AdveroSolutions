# Private assessment, Tokyo property document pilot

Job: 2112212604943890296. Source: `jd.txt` and `intake-private.json`, captured 2026-10-19. This file is private evidence and must not be copied into public scene data.

## Fit and first pilot

The post asks for discovery and a practical pilot rather than an immediate overhaul of every named tool. The deck proposes n8n orchestration for one Japanese PDF-to-standardized-record pilot, subject to discovery. HubSpot, Notion, Nutstore, email and Excel are existing client tools, not connected demo accounts. No native screen for any of those products is represented. Nonworkflow views are explicitly custom project workspaces.

The illustrative discovery ranking is property PDFs first (high impact, medium effort), inquiry drafts second (medium impact, medium effort), receipt sorting third (medium impact, low effort). These are invented discussion prompts, not an audit finding. Review a real example by video call and screen sharing, capture the steps without asking for a lengthy specification, estimate impact and effort with the client, then agree one pilot's input/output fields, exceptions, sample set and acceptance criteria. The pilot scope is separately agreed. No price or timeline estimate is on the deck.

## Concrete sample continuity and Quick route

All four scenes are required. Quick therefore retains discovery, evidence, correction, approval, duplicate handling, result and visible sample proof.

1. `workflow`, n8n: manual sample selection → conceptual document-key lookup over HTTP → duplicate If → new-document extraction held for human review. The true branch links the existing record and skips extraction/append. Required evidence and approval scenes show field standardization, ambiguity review and correction. Request failures remain held. Five nodes span four ranks for readable playback.
2. `evidence`, custom workspace: invented `aoba-property-sample.pdf`, document `PDF-014`, property `青葉レジデンス`, record `PROP-014`. Page 1 has `土地面積` (land area) 132.8 m²; page 3 has `延床面積` (total floor area) 216.4 m². Initial extraction incorrectly maps 132.8 into floor area and flags confidence 0.62. Price `1億4,800万円` is standardized to JPY 148,000,000. All excerpts and values are invented.
3. `approval`, custom workspace: invented reviewer Mika Sato checks page 3, changes `total_floor_area_m2` to 216.4, keeps land area 132.8 from page 1 and approves version 2. A replay of the same PDF digest links `PROP-014`, skips extraction and creates no second append. Confidence remains an illustrative extraction signal; manual review is not portrayed as a statistical confidence recalibration.
4. `result`, custom workspace: the same approved version prepares one consistent row with property, JPY price, land/floor areas, source pages and reviewer. The visible sample proof is the 132.8 → 216.4 m² correction. No actual file is exported or destination updated.

No PDF was supplied or generated. The displayed Japanese source snippets are synthetic fixtures within the deck, not verified extraction from a real document. Duplicate key design is PDF digest plus extraction-schema version; document versioning and same-property/different-document matching need discovery. Do not infer that a digest catches all semantic property duplicates.

## Secondary requirements and handover mapping

- Start with sample or anonymized data and limited access: visible in workflow details and cover labeling.
- Company-owned accounts and separate permissions: visible company-owned/limited-access statement; implementation must assign only the agreed permissions and keep secrets outside shared workflows and logs.
- Japanese accuracy: visible original labels, source pages, low-confidence hold and human correction. Representative testing should include native-text and scanned PDFs, multiple layouts, missing pages, unreadable values, Japanese numerals, JPY units and area labels. Agree an appropriately qualified team reviewer. No Japanese language fluency or legal/property expertise is claimed.
- Errors and duplicates: missing or unreadable fields hold, HTTP request failures hold for retry/review, identical replay links an existing record and skips a second append. Define retry limits, lookup unavailability, changed schema versions and edited-document behavior before implementation.
- Human approval: visible before standardized export, with version and reviewer retained. Outgoing messages remain subject to human approval initially; message drafting is a later candidate rather than part of this PDF pilot.
- Data handling: visible instruction to confirm processing locations, retention and recurring service costs before connecting accounts. Discovery must identify every proposed processor, what content leaves storage, access controls, retention/deletion, logging and recurring service costs. The deck makes no unverified data residency, zero retention, privacy certification or cost claims.
- Confidentiality agreement: client asks for willingness to sign. Lorenzo should confirm before promising it. The deck does not assert signature or agreement.
- Handover/training: visible workflow files, relevant source code, setup instructions, operating guide and team training. Include export schema, field dictionary, sample tests, permission inventory, error/approval runbook and credential ownership in the actual handover. Demonstrate a normal document, ambiguous field, missing field, API failure and duplicate replay with the team.
- Ongoing support: discuss needs after pilot acceptance. No service level, availability, fixed maintenance plan or support duration is invented.
- Other workflows: inquiry/email drafts, CRM/follow-up reminders, receipts/accounting prep and task/project tracking remain discovery candidates. Do not imply all are included in the pilot.

## Personalization evidence

The intake's `personalization` object identifies Simon with `source: client_reviews`, `reviewCount: 2`. Separate review entries:

- 2025-06-08, Administrative Support for Japanese Real Estate business in Tokyo: names Simon in its opening sentence.
- 2024-08-13, Seeking an LGBT/ Gay male Virtual Assistant to do a small update daily on a website vlog: names Simon in its opening sentence.

Simon is a supported client-contact first name. Neither review proves ownership, so the deck never calls him the owner. No other review-history names, industries or project facts appear publicly.

## Factual limits and controller follow-up

The post requests relevant projects, specific roles and results. No confirmed Japanese property document extraction case study is available in this intake. Visible synthetic sample proof is used instead; do not invent a past project or recast unrelated lead-generation figures as document-processing results. Any proposal experience statements must use the confirmed facts in `UPWORK_PROCESS.md`, section 7, with the appropriate limits.

Lorenzo is based in DFW, US Central Time. Japan meeting overlap must be agreed, and no exact availability is promised. Fees, pilot budget and timeline requested in the post are left for the call under Lorenzo's standing copy rules and the controller brief. Do not infer a suitable fee from the posted placeholder or unspecified bid statistics.

The workflow uses only `manual_trigger`, `edit_fields`, `http_request` and `if`. LLM extraction is an HTTP concept, not an `ai_agent` or `chat_model` node. Record lookup and export are conceptual project operations, with no URL, endpoint, credential or configured integration claim. Main owns adapter maintenance, template lock, queue commands, generation and independent review.

## Content verification

Performed a separate content self-review against the parent brief and CONTENT_BRIEF.md. Reviewed continuity, synthetic labels, source-page correction, approval sequencing, duplicate replay, public/private separation, supported scene/node keys, locked opening and 15-minute CTA. Applied `claudeisms` and `lorenzo-voice` guidance; no restatement-only kicker, invented credential, promised result, price or timeline remains. This is not independent page review or a recording-ready verdict.

Direct schema validation against current `schema.py` and `platforms.json` passes for all four required scenes. No page build, browser, queue mutation, shared asset edit, proposal write, commit, push or live write was performed. The coordinator subsequently compacted the workflow to five nodes over four ranks and passed official validation/build against the final template. Independent exact-page browser review remains separate.
