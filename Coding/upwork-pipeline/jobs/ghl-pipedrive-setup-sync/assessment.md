# Assessment - GoHighLevel & Pipedrive Setup Expert Needed (private)

## Time
- Integration on the canvas (GHL to Pipedrive with clean, dedupe, routing, deal create or move, write-back; Pipedrive to GHL stage sync with echo guard and activity; error alert): 14 to 20 hours including the GHL workflow webhook, Pipedrive webhook and custom fields, and testing with test leads. About 1.5 weeks calendar.
- Full post scope (12 responsibilities): roughly 45 to 70 hours, 3 to 5 calendar weeks.
  - Pipedrive setup, pipelines, stages, custom fields: 5 to 8 h
  - GHL sub-account structure, pipelines, custom fields, tags, lead sources: 5 to 8 h
  - Lead follow-up workflows plus email/SMS: 8 to 12 h. SMS needs A2P 10DLC registration in GHL if not done; approval can take 1 to 3 weeks and sets the calendar.
  - Integration: 14 to 20 h (above)
  - Migration of existing contacts and opportunities: 6 to 14 h, depends entirely on their volume and how messy it is (unknown)
  - Testing: 4 to 6 h. Documentation and basic training: 3 to 5 h.

## Likelihood
High for the integration if both accounts give API access; the pieces are standard. What breaks:
- Unverified by Lorenzo in a live account: Pipedrive API v2 shapes used on the canvas (persons/search, deals POST and PATCH, activities with participants, deal custom_fields keyed by field hash) and the Pipedrive webhooks v2 payload (meta.action, meta.user_id, previous.stage_id). The catalog's Pipedrive n8n node is marked unverified (node 5b); fall back to a POST /api/v2/persons HTTP call if its fields do not map.
- GHL side: the workflow Webhook step must send opportunity id, stage name and the Pipedrive deal id as custom data; the private integration token needs contacts and opportunities write scopes. Contact custom field key `pipedrive_deal_id` has to exist in the sub-account.
- Echo loop is the real design risk in a two-way sync: GHL moving an opportunity fires the GHL stage workflow, which PATCHes Pipedrive to the same stage. Node 10 drops changes made by the sync's own Pipedrive user and non-stage changes. Needs a dedicated API user in Pipedrive (a seat) or the guard falls back to comparing stages only.
- Source of truth per field (owner, value, stage) must be agreed before build or the two CRMs overwrite each other.
- Pipedrive plan tier: custom fields and webhooks are available broadly, but seat count for a dedicated API user costs a seat.
- Migration quality depends on their existing data; duplicates across both CRMs need a one-time merge before the sync goes live.

## Standard pricing
- Market for the full 12-item scope from an experienced GHL + Pipedrive builder: $3,000 to $6,500.
- Integration alone: $900 to $2,000.
- The post says Fixed $10: a placeholder against a 3 to 5 week scope. Bids average $9.84 on the same basis. Real price gets set on the call.
- Recurring software (theirs): GHL plan ($97 to $497/mo), Pipedrive per seat (plus one seat if a dedicated API user), n8n cloud from about $24/mo or self-hosted, GHL phone/email usage and A2P fees.

## Pricing path (Lorenzo only)
- Value: assumption, 8 hours a week of duplicate entry, manual stage updates and chasing unrouted leads at $50/h = 8 x 52 x 50 = $20,800 a year. Leads lost between two CRMs not counted.
- Price range: 10 to 20% = $2,080 to $4,160.
- Land offer (milestone 1): the one-way GHL to Pipedrive sync, sections 1 to 3 (clean, dedupe, routing, deal in the right stage, id write-back), live on their accounts.
- Upsell path: two-way stage sync and activities; migration; GHL follow-up workflows with email/SMS; documentation and training; then a monthly retainer for troubleshooting and changes ("ability to troubleshoot existing automations").
- Milestones:
  1. 30%: paid once the GHL to Pipedrive sync with cleaning, dedupe and routing is delivered and you've signed off.
  2. 25%: paid once the two-way stage sync, activity automation and error alerts are delivered and you've signed off.
  3. 25%: paid once pipelines, custom fields, follow-up workflows and the contact and opportunity migration are delivered and you've signed off.
  4. 20%: paid once testing, documentation and the training session are delivered and you've signed off.

## Ask before quoting
- How many new leads a day or week, and from which lead sources?
- How many existing contacts and opportunities to migrate, and from where (GHL, Pipedrive, a spreadsheet, another CRM)?
- How many pipelines and stages, and do GHL and Pipedrive stages match one to one?
- How many reps, and the rule for who gets which lead (by source, round robin, territory)?
- Which system is the source of truth for owner, value and stage?
- Pipedrive plan and seats; GHL agency or single sub-account; is A2P 10DLC done for SMS?
- Existing automations or Zaps that need troubleshooting or replacing?
- Preference among n8n, Zapier and Make (the canvas is n8n; the logic ports).

## Flags
- Client in the US (NJ); no US-only restriction stated.
- They ask for "examples of similar GHL + Pipedrive projects". Lorenzo has no verified GHL + Pipedrive past project to cite; the proposal answers with the canvas and the roofing routing bullet, never a claimed identical project.
- They ask for hourly rate and availability: rate goes in the Upwork bid field only, never in the proposal.
- Fixed $10 budget, 3 hires, $80 spent, 5.0 feedback: small-spend history; the price conversation happens on the call.
- Sharp points the client would value, already on the build and in beats: dedupe by email before create (node 3), and the echo guard that stops a two-way sync from looping (node 10).
