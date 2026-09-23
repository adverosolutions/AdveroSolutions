# GHL workflow build spec: "Proposal Follow-up Sequence"

Status: DRAFT EXISTS, EMPTY. The workflow `45f6c25f-e7d0-419b-898f-a9b0e6e1fa06` ("Proposal Follow-up Sequence") is already in the account as a draft with no steps (`config/ids.json` ghl.workflows.proposal_follow_up). GHL workflows cannot be created or edited through the public API: there is no POST or PUT on `/workflows`, only a list endpoint and "add contact to workflow". So this file is a build spec for the UI, not code, and the JSON below is a representation of it for review, not something any script posts.

Controlled-environment rule: build the steps in the existing **draft**, test with an internal contact (Lorenzo's own email), and publish only after the checklist in `runbooks/precall_and_proposal.md` is signed off. Until A2P 10DLC clears, every SMS step stays **disabled** (toggle off, do not delete).

## Ids (from `config/ids.json`)
- Location: `ebyNANPagaK7ycf1pfge` (AdveroSolutions)
- Workflow: `45f6c25f-e7d0-419b-898f-a9b0e6e1fa06`, status draft
- Pipeline: Sales `GCBkIzFpung73cIDVPzn`
- Stages: Proposal Sent `fcf3359e-f8e0-4354-92ee-2d7b396b769e`, Won `48eca719-502a-46cc-9e39-7db0aeffb41e`, Lost `6ce29ed4-fab0-4244-938f-758ef8688cd8`, Follow Up Later `ce219fc8-3caa-45e5-bc81-622a1625a23b`
- Assigned user: `gIwBtPohHJXADQBuGAx8` (Lorenzo)
- Booking / reschedule URL: `https://api.leadconnectorhq.com/widget/booking/GDugwLmZNdsD13RBDnRu`

## Workflow settings
| Setting | Value | Why |
| --- | --- | --- |
| Name | Proposal Follow-up Sequence | already named in the draft |
| Trigger | Opportunity Status Changed / Pipeline Stage Changed: pipeline Sales, stage **Proposal Sent** | the proposal generator's `stage_hint` is `proposal_sent`; moving the opportunity is what arms this |
| Stop on response | **ON** | a reply is a conversation, not a step. The reply engine takes it from there |
| Allow Re-entry | OFF | a second proposal to the same contact is a new decision, not a re-run |
| Time window | 07:00 to 19:00 America/Chicago | CLAUDE.md engine rule: sends only 07:00-19:00 CT |
| Skip weekends | ON for every email step | D3 from a Friday proposal otherwise lands on Monday anyway; make it explicit |
| Timezone | Contact's timezone, fallback Account (America/Chicago) | |

## Exit conditions (build these first, not last)
| Leaves the workflow when | How |
| --- | --- |
| They reply on any channel | Stop on response (workflow setting) |
| They pay | Opportunity moved to **Won** -> "Remove from workflow" step in the Deal Won workflow (`e0593495-a88e-46f0-a9ac-611fabf7f0f9`) |
| They say no | Opportunity moved to **Lost** -> Remove from workflow |
| They book another call | **Appointment Status -> Confirmed** on Discovery Call -> Remove from workflow. Not Customer Booked Appointment: a call booked from an email reply is first created as an unapproved `new` hold (`booking.book()`), before Lorenzo sees the card. On "booked" the hold alone pulled the contact out, and a hold he then vetoed left a live proposal with no follow-up at all. On "confirmed" the contact leaves only once the call is approved (or self-booked through the widget, which auto-confirms). Rehearse both in the UI before publishing, as `show_rate_workflow.md` describes |

## Steps (in order)

| # | Step | Type | Config | Notes |
| --- | --- | --- | --- | --- |
| 0 | Trigger | Pipeline Stage Changed | Pipeline Sales, stage Proposal Sent | Lorenzo moves the card after he sends the proposal he reviewed |
| 1 | Wait 1 day | Wait, Time delay, skip weekends | 1 day, resume 09:00 contact time | D1 |
| 2 | D1 email: any questions | Send Email | subject `Quick question on the proposal`, body below | Plain text, from lorenzovillarreal@adverosolutions.com |
| 3 | Wait until D3 | Wait, Time delay | 2 days | |
| 4 | If/Else: is there a Loom | Condition on custom field `proposal_loom_url` is not empty | Yes -> step 5, No -> internal task "record the 90-second walkthrough for {{contact.company_name}}" assigned to Lorenzo, then step 6 | The Loom is per deal, so the branch keeps the sequence honest when one was never recorded |
| 5 | D3 email: walkthrough | Send Email | subject `90 seconds on how this runs`, body below with `{{custom_values.proposal_loom_url}}` | |
| 6 | Wait until D7 | Wait, Time delay | 4 days | |
| 7 | D7 case study | If/Else, **three ways** | `offer-outbound` -> outbound study. `offer-reactivation` -> reactivation study. **Neither tag -> no email at all**: an internal task "Tag {{contact.company_name}} with its offer type, then send the D7 case study by hand" assigned to Lorenzo, plus an internal notification | **The offer tag is load-bearing.** offers.md allows one proof point per offer type, never mixed. A two-way branch made "no tag" and "tagged reactivation" the same case, so a `cleaning_trigger` prospect whose tag did not apply got the reactivation proof line ($6M recovered) that `draft.wrong_offer_proof_problems` rejects in every other send path. Neither tag exists in the account yet (see "Before publishing"), so the untagged branch is today's default, not an edge case |
| 8 | Wait until D14 | Wait, Time delay | 7 days | |
| 9 | D14 email: decision ask | Send Email | subject `Where did you land`, body below | The yes/no question, not another nudge |
| 10 | Wait until D21 | Wait, Time delay | 7 days | |
| 11 | D21 email: close out | Send Email | subject `Closing this out`, body below | |
| 12 | Move opportunity | Update Opportunity | Stage -> **Follow Up Later** (`ce219fc8-3caa-45e5-bc81-622a1625a23b`), status open | Not Lost: they never said no |
| 13 | Add contact tag | Add Tag | `proposal-follow-up-later` | Feeds the 90-day re-engagement list |
| 14 | Internal notification | Notify Lorenzo | "{{contact.name}} never answered the proposal. Moved to Follow Up Later." | |
| 15 | End | | | |

## The copy

Every body obeys the same rules as the rest of the engine: no em dashes, no exclamation marks, never mentions AI or automation, signed "Lorenzo", and no figure that `config/offers.md` marks TO CONFIRM. `{{contact.first_name}}` and `{{contact.company_name}}` are GHL merge fields.

### D1: any questions
```
Hey {{contact.first_name}},

Sent the proposal over yesterday. Wanted to check whether anything in it needs changing before you decide.

The part people usually want to talk through is what the first sequence actually says, so if that is the question, I can walk you through it in five minutes.

Lorenzo
```

### D3: Loom walkthrough
```
Hey {{contact.first_name}},

Rather than another email about it, here is ninety seconds of me walking through exactly what would run for {{contact.company_name}}: {{custom_values.proposal_loom_url}}

It shows the first two messages and where the replies land. If it raises a question, just reply here.

Lorenzo
```

### D7: case study (reactivation branch, tag `offer-reactivation`)
```
Hey {{contact.first_name}},

Something worth knowing while you are deciding. I built a similar system for a commercial roofer doing $150M/year. I recovered about $6M worth of contracts within 6 months.

Same idea as what I proposed for {{contact.company_name}}: the work was already there, nobody had gone back to it.

Lorenzo
```

### D7: case study (outbound branch, tag `offer-outbound`)
```
Hey {{contact.first_name}},

Something worth knowing while you are deciding. I recently implemented the same system for a commercial roofer doing $150M/yr and generated about $180,000 in new contracts in 90 days.

Same idea as what I proposed for {{contact.company_name}}, pointed at the accounts you do not have yet.

Lorenzo
```

### D14: decision ask
```
Hey {{contact.first_name}},

Straight question so neither of us is guessing. Is this a yes, a no, or a not right now?

Any of the three is a fine answer. I just want to know whether to keep the slot open.

Lorenzo
```

### D21: close out
```
Hey {{contact.first_name}},

I have not heard back, so I am closing this out on my side.

If it comes back around, reply to this and we pick it up where we left it. No hard feelings either way.

Lorenzo
```

## JSON representation (for review; nothing posts this)
```json
{
  "id": "45f6c25f-e7d0-419b-898f-a9b0e6e1fa06",
  "name": "Proposal Follow-up Sequence",
  "status": "draft",
  "locationId": "ebyNANPagaK7ycf1pfge",
  "settings": {
    "allowReentry": false,
    "stopOnResponse": true,
    "timeWindow": {"start": "07:00", "end": "19:00", "timezone": "America/Chicago"},
    "skipWeekends": true,
    "timezone": "contact_fallback_account"
  },
  "trigger": {
    "type": "pipeline_stage_changed",
    "filters": {"pipelineId": "GCBkIzFpung73cIDVPzn", "stageId": "fcf3359e-f8e0-4354-92ee-2d7b396b769e"}
  },
  "exits": [
    {"type": "stop_on_response", "channels": ["email", "sms"]},
    {"type": "opportunity_stage", "stageId": "48eca719-502a-46cc-9e39-7db0aeffb41e", "action": "remove"},
    {"type": "opportunity_stage", "stageId": "6ce29ed4-fab0-4244-938f-758ef8688cd8", "action": "remove"},
    {"type": "appointment_status", "calendarId": "GDugwLmZNdsD13RBDnRu", "appointmentStatus": "confirmed", "action": "remove"}
  ],
  "steps": [
    {"id": 1, "type": "wait", "mode": "time_delay", "days": 1, "skipWeekends": true, "resumeAt": "09:00"},
    {"id": 2, "type": "send_email", "template": "d1_any_questions",
     "subject": "Quick question on the proposal", "from": "lorenzovillarreal@adverosolutions.com"},
    {"id": 3, "type": "wait", "mode": "time_delay", "days": 2},
    {"id": 4, "type": "if_else", "condition": {"customFieldNotEmpty": "proposal_loom_url"},
     "yes": [{"type": "send_email", "template": "d3_loom", "subject": "90 seconds on how this runs"}],
     "no": [{"type": "add_task", "title": "Record the 90-second walkthrough for {{contact.company_name}}",
             "assignedTo": "gIwBtPohHJXADQBuGAx8", "dueIn": "4h"}]},
    {"id": 5, "type": "wait", "mode": "time_delay", "days": 4},
    {"id": 6, "type": "if_else", "name": "d7_case_study_branch",
     "branches": [
       {"name": "outbound", "condition": {"contactTagIncludes": "offer-outbound"},
        "steps": [{"type": "send_email", "template": "d7_case_study_outbound",
                   "subject": "The roofer version of this"}]},
       {"name": "reactivation", "condition": {"contactTagIncludes": "offer-reactivation"},
        "steps": [{"type": "send_email", "template": "d7_case_study_reactivation",
                   "subject": "The roofer version of this"}]}
     ],
     "else": [
       {"type": "add_task", "title": "Tag {{contact.company_name}} offer-reactivation or offer-outbound, then send the D7 case study by hand",
        "assignedTo": "gIwBtPohHJXADQBuGAx8", "dueIn": "4h"},
       {"type": "internal_notification", "to": "gIwBtPohHJXADQBuGAx8", "channel": ["email", "app"],
        "body": "{{contact.name}} reached D7 with no offer tag. No case study was sent: offers.md allows one proof point per offer type and there is no way to tell which one applies."}
     ]},
    {"id": 7, "type": "wait", "mode": "time_delay", "days": 7},
    {"id": 8, "type": "send_email", "template": "d14_decision", "subject": "Where did you land"},
    {"id": 9, "type": "wait", "mode": "time_delay", "days": 7},
    {"id": 10, "type": "send_email", "template": "d21_close_out", "subject": "Closing this out"},
    {"id": 11, "type": "update_opportunity", "stageId": "ce219fc8-3caa-45e5-bc81-622a1625a23b", "status": "open"},
    {"id": 12, "type": "add_tag", "tags": ["proposal-follow-up-later"]},
    {"id": 13, "type": "internal_notification", "to": "gIwBtPohHJXADQBuGAx8", "channel": ["email", "app"],
     "body": "{{contact.name}} never answered the proposal. Moved to Follow Up Later."}
  ]
}
```

## What this sequence deliberately does not do
- **No SMS.** A2P 10DLC is not registered (`config/ids.json` ghl.a2p_10dlc). Add the D3 and D14 SMS legs only after it clears, and add them disabled first.
- **No payment link.** The link belongs to the SOP-009 verbal-commit path in `services/reply_engine/proposal.py`, which drafts it for Lorenzo within the hour of the call. A workflow that mails a payment link to somebody who has not verbally committed is a different sequence with a different trigger.
- **No pricing.** Nothing here restates a number. The proposal holds the numbers, and repeating them in a follow-up is how a figure drifts from `config/offers.md`.
- **It does not create itself.** No script in this repo posts this workflow, because no endpoint exists to post it to.

## Before publishing
1. Custom field `proposal_loom_url` exists on the contact (Settings > Custom Fields, text).
2. Contact tags `offer-reactivation` and `offer-outbound` are applied by the reply engine at booking time. Neither exists in the account today (`config/ids.json` ghl.contact_tags_in_use is `cold-email`, `instantly-positive-reply`), so until they do, **every contact takes the untagged branch and gets a task instead of an email**. That is deliberate: the D7 branch is the only step whose copy depends on which offer was sold, and guessing it is how the reactivation proof line ends up in a trigger deal.
3. Test with Lorenzo's own contact record end to end, checking that a reply really does stop it.
4. The Deal Won workflow gets a "Remove from workflow" step pointing at this one.
