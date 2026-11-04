# Handoff: Sopio first no-show N3 + Rob stage options — 2026-09-25 ~16:05 CT

From: Executor (CoS)
Mode: read-only gather + draft plan. Ask first ON. **Do not send Instantly/Gmail. Do not write GHL.**
Related: Calls standby `20260925_1603_noshow_sopio_rob.md`; Inbox live ops `20260925_1548_inbox_live_ops.md`.

---

## A) Sopio — [REDACTED] (Taxfo Accounting)

### Facts (confirmed)
- **Outcome:** FIRST NO-SHOW. Lorenzo marked no-show 2026-09-25 ~16:00 CT. NOT Rob.
- **Scheduled call:** Thu Sep 24 **3:00–3:15pm CT (4:00pm ET)**. Google Calendar event id `j8n9pmfjl3cufeiu58g4kp12c8`, summary "Lorenzo Villarreal's Zoom Meeting", attendee `[REDACTED]` (needsAction). Zoom link on invite.
- **Instantly:** interest **1 Interested**. Inbox **`[REDACTED]`**. Thread subject `Re: Sopio, question`.
- **GHL:** no contact / opportunity on file (case + prior Inbox pass).
- **Thread (Instantly Unibox, case 20260925_sopio.json):** cold → she asked % → he said 20–30% + Wed 2 / Thu 4 CT → she picked **Thu 4pm Eastern** + phone [REDACTED] → he sent cal/Zoom → she then said available **daily 3–6pm ET** (Sep 21 evening). Last writer: Sopio Sep 21. No inbound after the miss.
- **Ladder:** first miss → skip **N1** (no Zoom join data / Meet path; CoS+Calls: skip N1). Due step = **N3** `no_show.ns_reschedule_email`. N3 timing: later of no-show flag and S+25 → due now when Lorenzo marked.

### Calendar for proposed slots
- Lorenzo primary `[REDACTED]`: **no events** Mon Sep 28 or Tue Sep 29 (list_events empty).
- `suggest_time`: free **Mon Sep 28 2:00–5:00pm CT** and **Tue Sep 29 2:00–5:00pm CT** (her window 3–6pm ET = 2–5pm CT).
- Proposed reserved slots (in window, soonest first): **Mon 3:00pm CT (4:00pm ET)** and **Tue 2:00pm CT (3:00pm ET)**.

### Exact N3 draft (copy_doc_approved.txt tag `no_show.ns_reschedule_email`)

Send as **reply in Instantly thread** from `[REDACTED]`, subject stays `Re: Sopio, question` (template subject "New time for our call" only if no thread — she has a thread).

```
Hey Sopio,

Looks like I missed you on our call today. I understand things come up, so let's get another call on the books at a time that works well for you.

Could we do Mon 3:00pm CT (4:00pm ET) or Tue 2:00pm CT (3:00pm ET)? Just reply with the one that works.

Lorenzo
```

### "Today" wording note (OPEN ASK)
- Approved N3 body says **"our call today"**. Miss was **Thu Sep 24**; send would be **Fri Sep 25**.
- Skill booked-calls Status: waiting on Lorenzo to decide N3 "today" wording when no-show is marked on a later day.
- Options for Lorenzo: (1) send approved text as-is, (2) hold until he edits one word (e.g. "Thursday" / "yesterday") — that edit is a hold card, not auto-send.

### Proposed field updates (AFTER Lorenzo yes to send — not applied)

| System | Field | Proposed |
|---|---|---|
| Instantly | interest | **-1** (matches GHL Follow Up Later per `05_lead_state_ghl.md` §2). **Conflict:** Calls standby used **-4**; SOP maps -4 to Lost+no-show reason (third miss). Ask which. |
| GHL | contact | **Create** (none exists): Sopio / Taxfo Accounting / [REDACTED]; tags `cold-email`, `instantly-positive-reply`, niche bookkeeping, campaign_key TBD |
| GHL | opportunity | Create Sales opp; stage **Follow Up Later** (`ce219fc8-3caa-45e5-bc81-622a1625a23b`) after first miss |
| GHL | Sequence | `no_show` |
| GHL | Last Email Sent | `no_show.ns_reschedule_email` (on send) |
| GHL | Last Email Date | send time CT |
| GHL | Next Email | `no_show.ns_d2_value_email.bookkeeping_reactivation` (N5) — see note |
| GHL | Next Due Date | **Mon Sep 28 10:00 ET** (lead zone) ≈ **09:00 CT** |
| GHL | note | Record miss Thu Sep 24 3pm CT / 4pm ET; N1 skipped; N3 sent; slots offered; Decision cost n/a until Opus/send |
| State | `offered_times.jsonl` | reserve Mon 3pm CT + Tue 2pm CT for this lead |
| State | `sent_log.jsonl` | on send |

**Next-touch note:** Miss day 0 = Thu Sep 24. N4 day 1 was Fri Sep 25 **10:00 ET** — already past if N3 goes Fri afternoon. With 8h spacing after N3, propose **skip N4**, next = **N5 day 2** Mon Sep 28 10:00 ET (`bookkeeping_reactivation` niche point on file). Confirm with Opus/CoS before arming.

### Asks (Sopio)
1. Approve N3 draft + slots as written? Or change times?
2. Keep "today" or edit for Thu miss?
3. Instantly interest **-1** (SOP) or **-4** (Calls standby)?
4. Create GHL contact + Follow Up Later on send yes?
5. Skip N4 → N5 Mon, or force N4 after 8h?

---

## B) Rob — [REDACTED] (CJS Global / Rob Marano)

### Facts (confirmed)
- **Call DID happen** Fri Sep 18 **1:00–1:15pm CT (2:00pm ET)**. Lorenzo: went poorly. **NOT a no-show. Do NOT start no-show ladder.**
- Calendar event id `3i10oid4i1lckk4dfm4j8sbog8`, attendee `[REDACTED]` (needsAction), Zoom on invite.
- **Instantly:** **Lost** (case interest **-3**; UI Lost). Inbox **`[REDACTED]`**.
- **GHL:** no contact / opportunity on file.
- **Thread outcome:** cold cleaning reactivation → "tell me more?" → overview + Thu 4 / Fri 3 → he proposed Fri 2pm EST → locked in + invite → Sep 18 chase "still good for today at 2?" — **no inbound after Sep 15**. Call completed poorly per Lorenzo; Instantly already Lost.

### Email
- **No email draft.** No copy-doc template fits a completed-but-poor discovery call (no post-call / soft-close / "not a fit after call" tag found). Cadence and no-show ladders do not apply.

### Stage options only (pick one — Ask Lorenzo)

| Option | GHL | Instantly | When |
|---|---|---|---|
| **1. Keep Lost** | Create contact+opp **Lost** (`6ce29ed4-…`) with lost reason e.g. `not a fit` / `poor call` + note | keep **-1** or **-3** (sticky negative; do not flip positive) | Default if no pipeline / no follow-up |
| **2. Follow Up Later** | Stage **Follow Up Later** + dated task (e.g. +30d) | **-1** | If he might reopen later |
| **3. Keep as-is** | Still no GHL contact; Instantly Lost only | no change | Minimal; leaves GHL blank (hygiene gap) |

Also: create GHL contact yes/no; campaign_key / niche (cleaning reactivation) for tags.

### Asks (Rob)
1. Which stage option (1 / 2 / 3)?
2. Lost reason text if option 1?
3. Follow-up date if option 2?
4. Create GHL contact now (records only, no email)?

---

## C) Open questions (CoS → Lorenzo)

1. Sopio: send N3 as drafted? "today" vs Thu wording?
2. Sopio: Instantly -1 vs -4?
3. Sopio: GHL create + Follow Up Later + Sequence no_show on approval?
4. Sopio: skip N4 → N5 Mon 10:00 ET?
5. Rob: Lost vs Follow Up Later vs Instantly-only keep?
6. Neither lead has campaign_key on file — set when creating GHL?

---

## D) Explicit non-actions this pass
- No Instantly send / interest write
- No Gmail send
- No GHL create/update
- No calendar invite create
- No message to Lorenzo (CoS owns that)

