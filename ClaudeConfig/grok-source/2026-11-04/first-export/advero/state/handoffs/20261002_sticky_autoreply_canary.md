# Sticky Auto-Reply Canary Pool — 2026-10-02 CT

**For:** Lorenzo / COO  
**Built:** 2026-10-02 09:02 CT  
**Ask-first:** Sheet + CSV only. **No** Instantly campaign created. **No** CSV uploaded to Instantly. **No** settings changed.

## Sheet
- **Title:** Advero — Sticky Auto-Reply Canary Pool (2026-10-02)
- **URL:** https://docs.google.com/spreadsheets/d/1CLHGRENAlRLJuHjKPaI1lFql3WiyRj5aPL52ZKkFVWI/edit
- **spreadsheetId:** `1CLHGRENAlRLJuHjKPaI1lFql3WiyRj5aPL52ZKkFVWI`
- **Tabs:** Canary Pool (14) · Excluded OOO (29) · Rules

## CSV backups
- `/home/box/advero/state/handoffs/20261002_sticky_autoreply_canary.csv`
- `/home/box/advero/state/handoffs/20261002_sticky_autoreply_excluded_ooo.csv`

## Counts
| Metric | Value |
|---|---|
| Received Unibox emails scanned | 130 (`GET /emails?email_type=received`, paginated) |
| Unique lead addresses in Unibox | 111 |
| **Sticky canary pool (deduped)** | **14** |
| Excluded temporary OOO / busy auto | 29 |
| Human / other replies (not in pool) | 68 |
| Exclude rate among auto-ish unique leads | 29/(29+14) = **67.4%** |

### Classification mix (sticky)
- `mailbox_no_longer_monitored`: 4
- `mailbox_moved_permanent`: 3
- `inbox_filter_auto`: 2
- `unmonitored_or_nonprimary_inbox`: 2
- `ticket_auto_ack`: 1
- `rarely_checked_inbox_auto`: 1
- `person_left_permanent`: 1

## Canary readiness (skill Level 4)
- Skill: **5+ addresses minimum**; **80%+ auto-response = healthy**; ideally enough for **12 inboxes**.
- **14 meets the 5+ floor** but is **thin for 12-inbox coverage** (~1 address per sending inbox, no spare / no round-robin depth).
- Prior daily cards cited **17 usable**; that prior pool file was **not found on disk**. This is a **fresh Unibox rebuild**.
- **Recommendation:** usable for a first canary round **after Lorenzo verifies** older addresses still auto-reply (esp. `[REDACTED]` which said address would discontinue 2025-10-05). Grow pool by continuing to tag sticky Unibox hits weekly. Do **not** send canary via Instantly reply endpoint (lands in prospect cold thread). Do **not** mail blocklisted / negative-status / dead leads.

## Include rules (sticky / permanent)
- Mailbox no longer monitored / not in use / not monitored
- Mailbox gone / does not exist / user unknown (if present in Unibox — Instantly often hides NDRs)
- Person no longer works here / left company / change of position
- Email transferred / moved / new address / will be disabled or discontinued / DBA rebrand
- Inbox Zero / cold-email filter auto-notice (note: may only fire on first-time cold senders)
- Unmonitored / non-primary / "we do not respond to emails" / marketing-only inbox
- Rarely-checked inbox auto ("call the office")
- Ticket / auto-ack with **no** dated return

## Exclude rules (temporary)
- Dated OOO ("out until…", "back Monday", "on vacation", "returning Oct…")
- Short temporary away / traveling this week / limited access with return date
- Busy-season tax deadline auto without permanent mailbox change

## Sample sticky rows
| email | classification | date CT | snippet |
|---|---|---|---|
| [REDACTED] | ticket_auto_ack | 2026-09-29 08:45 CT | Hello and thank you for your reply. One of our friendly service techs will respond very so… |
| [REDACTED] | mailbox_moved_permanent | 2026-09-28 13:54 CT | Hi, Thank you for your email! I wanted to let you know that Elite Professional Finance is … |
| [REDACTED] | mailbox_no_longer_monitored | 2026-09-28 12:02 CT | Please be advised that this email is no longer monitored. For assistance, please contact t… |
| [REDACTED] | inbox_filter_auto | 2026-09-24 07:06 CT | https://www.getinboxzero.com Inbox Zero The recipient uses Inbox Zero https://www.getinbox… |
| [REDACTED] | unmonitored_or_nonprimary_inbox | 2026-09-18 06:20 CT | We do not respond to emails. To engage services with Chartered Financial Strategies, pleas… |
| [REDACTED] | mailbox_moved_permanent | 2026-09-17 08:21 CT | Please note that our email has changed and this email will be disabled at the end of the m… |

## Gaps
1. Pool still under ideal size for 12 inboxes with redundancy.
2. Instantly hides most hard-bounce NDRs from Unibox — hard bounces are **not** in this pool (use bounce analytics, not Unibox).
3. Two Inbox Zero rows may not fire again on a same-sender canary (first-time filter).
4. Several sticky hits came from **retired/old sending domains** (`onlineadverosolutions.com`, `techadverosolutions.com`, etc.) — addresses are still usable as **recipients**; sending domain on the historical reply is informational only.
5. No Instantly campaign / upload performed (by design).

## Source
- Instantly API v2 read-only via box `INSTANTLY_API_KEY` / `~/advero/bin/_load_box_secrets.py`
- Cross-checked with `~/advero/state/handled.jsonl` labels `auto_reply_unmonitored`
