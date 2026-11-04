# Sample Eric-style metrics card — Tue Sep 29, 2026 CT
Pulled ~4:57pm CT from Instantly `campaigns/analytics` + `overview` (expand_crm_events).

**Email-1 proxy:** Instantly `new_leads_contacted_count` (first-touch new leads contacted). Not perfect step-1 send count, but the closest API field without scraping the UI.

---

## North-star (today so far)

| Metric | Today | Rolling 7d | Read |
|---|---:|---:|---|
| Reply rate (unique / sent) | **0.33%** (1 / 300) | 0.56% (8 / 1,425) | Under Eric’s ~1% bar — early signal, not a kill yet |
| Contacts per positive (sent ÷ interested) | **300** (1 interested) | **475** (3 interested) | Eric watches jumps (e.g. 300 → 700) as list/spam drift |
| Net-new Email-1 (proxy) | **223** | **880** | vs total sent 300 today → ~74% first-touch; rest follow-ups |

Also today: bounce **3.00%** (9 / 300) — sits on Advero’s ~3% pull line (Deliverability owns this). Instantly CRM: meeting_booked=2, interested=1.

---

## Per-campaign reply (today)

| Campaign | Sent | Email-1 proxy | Unique replies | Reply % |
|---|---:|---:|---:|---:|
| Cleaning — Client Reactivation | 50 | 30 | 1 | **2.0%** |
| Cleaning — Trigger Outbound | 50 | 32 | 0 | 0.0% |
| Bookkeeping — Client Reactivation | 50 | 42 | 0 | 0.0% |
| Bookkeeping — Trigger Outbound | 50 | 41 | 0 | 0.0% |
| Recruiting — Client Reactivation | 50 | 47 | 0 | 0.0% |
| Recruiting — Outbound | 50 | 31 | 0 | 0.0% |

(Subject A/B on cleaning is live; today’s volume is too thin to call a winner.)

---

## How this would show in chat (proposed evening line)

```
Instantly north-star — Tue Sep 29 (so far)
Reply 0.33% (1/300) · 7d 0.56%
Contacts/positive 300 today · 475 on 7d (3 interested)
Email-1 ~223 of 300 sent (77 follow-ups)
Best today: cleaning reactivation 2.0% (1/50)
Bounce 3.0% — Deliverability watch
```

RevOps still owns final column layout + routine wiring after their design comes back.
