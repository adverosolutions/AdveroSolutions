# Private preparation: aged care AI operations

Prepared 20 October 2026. Research/content only. Initial research status was requires_adapter. A bounded Gmail candidate and assigned spec are now implemented; exact native review is pending and CRM product remains unresolved. No live email, notes or CRM updates. Subsequent main authorization covered the assigned spec and bounded Gmail/native adapter maintenance. This worker made no queue changes.

## Job facts and first-stage recommendation

Source: https://www.upwork.com/jobs/~022112536224921411609
Australian aged care provider; founder is overloaded with email/admin and has no AI automation. Wants Gmail/Workspace drafts in their own tone, review before sending, email/call summaries and actions against the correct CRM contact, privacy, error handling and measurable time savings. CRM, call platform, business name and founder name are not supplied. No permission or evidence to assume GHL, a particular clinical system or an integration already built.

Recommend a first pilot: one ordinary administrative email thread → owner-reviewed Gmail draft → structured note/action package mapped to the identified contact. Start by reviewing process, finding one repeatable email category, confirming current CRM and access, collecting owner-approved writing examples, and agreeing the baseline. Do not include clinical decisions or medical advice in the sample. Confirm actual similar-project proof from Lorenzo; this preparation invents none.

## One sample, two-minute scene map

Outer illustrative label once. Entity: Evelyn Carter, evelyn.carter@example.com, client reference AC-1042; email subject “Next week’s visit”; received 20 October 2026, 09:10 Australia/Sydney. Message: “Hi, could someone call me about moving next week’s visit to the afternoon? I’m available after 2 pm tomorrow. Thanks, Evelyn.” This is a request, not a confirmed reschedule. Owner: founder (no invented name). Follow-up action: call Evelyn 21 October after 2 pm, Australia/Sydney, confirm preferred visit day and availability. No diagnosis, care plan, date of birth or real personal data.

| Time | Stop/purpose | New fact and visible evidence | Spoken cue |
| --- | --- | --- | --- |
| 0–10s | Opening | Draft replies and capture the follow-up before the founder sends anything | “I started with a visit-change request, since it needs a reply and a follow-up.” |
| 10–35s | Gmail desktop inbox/thread | Evelyn’s actual sample message, subject, sender and time; a user-created label such as Needs review may be visible as a label, never an invented native priority status | “Evelyn wants a call after two tomorrow. She hasn’t confirmed a new visit time.” |
| 35–75s | Same Gmail thread, editable inline reply draft | Draft recipient is Evelyn, thread is unchanged, readable reply below. Original message stays available. Native Send control remains unclicked. Editing one phrase demonstrates the owner’s control. | “The reply asks for the missing day. It stays in Drafts while you check or edit it.” |
| 75–100s | n8n native execution output, or deferred real CRM contact after product discovery | One structured note/action from the same thread: AC-1042; “Requested a call about moving next week’s visit to afternoon”; owner founder; due 21 October after 2 pm Sydney; missing preferred visit day; reply status draft, not sent. If no real CRM adapter is available, clearly show this as a proposed note package in the n8n result, not as a saved CRM record. | “This is the note and follow-up to map into your CRM. We need the preferred day before changing the visit.” |
| 100–120s | Goal/close | Metrics below and reply CTA | “Reply and we can use a 15-minute call to pick the first email category and review how your CRM handles the follow-up.” |

Draft sample (illustrative; founder voice must be learned from approved examples):

Hi Evelyn,

Thanks for letting me know. Which day would you like to move the visit to? I’ll arrange a call after 2 pm tomorrow to discuss the options.

Thanks

No auto-send. Do not visually change Draft to Sent, or the visit to confirmed, without a separate user action/valid scheduling result. A demonstration can end usefully on a complete draft plus a clearly identified outstanding action. The date follows the source email’s Sydney time, not the presenter’s Chicago date.

Opening caption, verbatim: I've already put this workflow together for you. Let me walk you through how it works.

## Directional metrics

- Reduce email handling time: active founder minutes reviewing, editing, responding and recording actions per eligible thread. Compare the same categories before/after; exclude unattended model time.
- Increase action capture: explicit email/call commitments saved with the correct contact, owner and due date / sampled commitments identified. Unknown dates remain explicit missing fields, not invented due dates.
- Maintain human review coverage: AI-assisted outgoing messages reviewed by the founder before sending / AI-assisted outgoing messages sent. A saved draft is not a sent message or an approval record.

Baseline note: “We’ll agree the baseline using a small sample of your current emails and admin tasks.” No invented hours saved or percentage improvement.

## Official research and fidelity requirements

Checked 20 October 2026. Existing visual-reference catalog lists Gmail only as an intake watchlist; no accepted Gmail screenshots/adapter. Existing n8n screenshots cover generic light canvas and Edit Fields inspector, not Gmail or AI drafting. Do not reuse those as Gmail evidence.

Primary official sources retrieved:
- https://support.google.com/a/users/answer/9259856?hl=en — desktop Reply/Reply all, native reply location, editable reply behavior and subject controls. Owner review is reading/editing and choosing Send, not a Gmail Approve button.
- https://support.google.com/a/users/answer/9259846?co=GENIE.Platform%3DDesktop&hl=en — desktop compose/send and recipient controls. The article also documents Gemini, but Gemini Help me write is a different product surface from an external automation producing Gmail drafts; do not add Gemini buttons/claims to this proposed n8n integration.
- https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.gmail/draft-operations/ — Gmail node Resource Draft, Operation Create, Subject, Email Type, Message and options including thread context. This supports draft creation, not evidence it was sent or that CRM notes were written.
- https://docs.n8n.io/integrations/builtin/cluster-nodes/root-nodes/n8n-nodes-langchain.agent/ and https://docs.n8n.io/integrations/builtin/cluster-nodes/sub-nodes/n8n-nodes-langchain.lmchatopenai/ — native AI cluster reference if n8n is selected. A single model drafting chain may suffice; the post does not demand an agent and we should not add one merely for complexity.

Official Gmail image candidates discovered in reply documentation HTML:
- https://storage.googleapis.com/support-kms-prod/LQ83uwbbg6Jj60W0GwJL4JHOLI9Wb6wUJl7b
- https://storage.googleapis.com/support-kms-prod/FlWgN6FW9vxvlR12Iy1diqjybSXvJWB4cSGx
These are vendor SVG illustrations/screens from the reply page, not current full-workspace screenshots. The second URL could not be rendered by web open. They have not been visually accepted; no screenshot hash or current-version claim is made. Icon-only images and the 325×60 template-menu GIF are insufficient. Full current Gmail desktop inbox + populated thread + editable draft views remain a blocking reference gap. Obtain a vendor image with full coverage or an authorized real-workspace capture before approving native fidelity.

Gmail geometry must preserve the Gmail app rail/navigation, Compose, Inbox/Drafts labels, search/header, thread subject/sender/time placement, inline reply recipient line, formatting toolbar, blue Send with dropdown, draft state, attachment/delete controls and actual thread grouping. Do not invent “Approve”, “AI reviewed”, a built-in Needs review category or CRM cards inside Gmail. Needs review can be a clearly user-created label. Do not use mobile screenshots to implement desktop Gmail. Version/theme/account must be recorded; imagery cannot settle edition when unknown.

Privacy is a discovery/implementation requirement, not a generic safety slide: confirm authorized access, which email/call categories are eligible, least required fields, provider retention/data handling, appropriate permissions and the existing CRM’s handling before processing real client data. The demo uses synthetic administrative content only. Make no compliance certification claims.

## Minimal adapter/content contract

1. New Gmail desktop scene: inbox/thread + reply draft states; shared threadId/messageId/recipient, subject/body, received timestamp/timezone, user label and draft status. A Drafts entry must reopen the same draft. Native Send is visually accurate but must never produce a live write; any simulated send must require a deliberate presentation action and is unnecessary for this sample.
2. Founder review represented through editable draft + unsent state. No artificial approval dashboard. Replay restores original draft and cannot leak edits across scenes. Presenter Show result produces a complete reviewable draft immediately.
3. Optional n8n extension: Gmail Trigger/read context, model draft step and Gmail Draft Create, with native node inspector/output. Reuse only accepted node families after extension; do not relabel an HTTP node as a Gmail node. AI Agent is optional here and requires its own supported typed ports if selected.
4. CRM boundary explicit in schema: proposed_note versus persisted_record. Current post supplies no native CRM identity. Do not set persisted/saved flags, render a GHL skin, or claim CRM integration proof. After discovery add the actual CRM contact/note/task adapter and reference evidence, retaining AC-1042.
5. All routes must show the original email, readable draft and follow-up package. Optional controls can expose mapping and tone instructions, but cannot contain the only result. Three directional metrics plus baseline and blue reply-to-15-minute-call CTA.

Recommendation for main: review the implemented Gmail candidate and exact page before recording. A focused Gmail-first pilot story is accurate; full CRM result remains unresolved until product identity is known. Do not conceal that gap with a generic vendor record. Self-review checked chronology, unsent review, missing visit day, visible output, no clinical claims and sources. No independent visual acceptance performed.

## Implementation and current-reference addendum (20 October 2026)

Current executable route: custom workflow plan → native Gmail thread plus editable unsent reply → explicitly custom proposed CRM note/action. The current Gmail adapter has no send capability or fake Approve action. Native-looking Send is disabled in the local sample. Drafts reopens the same edited draft; replay restores the original synthetic draft. No CRM saved state is claimed.

Saved primary references and image hashes: reference-evidence/sources.json. Inspected gmail-official-0.webp, gmail-official-3.webp, gmail-official-5.webp and gmail-official-6.webp from https://workspace.google.com/products/gmail/ and https://workspace.google.com/intl/en/products/gmail/ai/ . They confirm light desktop layout, left navigation/Compose, top search, thread/reply region and blue split Send button, but are stylized product artwork with muted text and Gemini overlays. We do not reproduce those Gemini overlays or claim they are full target-account screenshots.

A much stronger current composer detail is saved as reference-evidence/gmail-reply-2026.png from https://workspaceupdates.googleblog.com/2026/07/prevent-accidental-disclosures-with-new-Reply-All-BCC-warnings-in-Gmail.html (July 2026; updated September). Pixels inspected: split Send/dropdown; text-format control; attachment, link, emoji, Drive, image, confidential-mode, signature, More and trash icons. The yellow warning applies to a Reply All recipient-list exception and is absent from our ordinary direct reply sample. The candidate toolbar was refined against this image, including icon semantics and ordering. Remaining difference: no current full-account inbox screenshot is available in this packet, so sidebar/complete-workspace parity still needs reviewer judgment; the product-image reference is explicitly qualified. Official 2026 Gmail logo is embedded from https://www.gstatic.com/images/branding/productlogos/gmail_2026/v2/web/192px.svg .

Self-check evidence: current integrated schema/catalog validates the job. Negative checks reject a different draft recipient and any sent status. Both shared JS files pass syntax checks; Python compile() passes without cache writes. Isolated DOM harness checks owner edit preservation across Drafts, replay restoring the source draft, disabled Send and no invented Approve button. Worker headless launch failed SIGABRT/EPERM in sandbox; main received harness/runner for its browser QA. These are self-review findings, not an independent approval or browser pass.
