# Reactivation list

Leads who said no, opted out, or were annoyed, parked for a later re-contact instead of being dropped.

Where it lives
- Google Sheet: Advero Lead Pool, tab "Reactivation"
  https://docs.google.com/spreadsheets/d/1J9JRGX1UUBXc1omWmDJuz7oUF047JGDcelQN4-9o57M/edit#gid=28178631
- Mirror: ~/advero/state/reactivation/reactivation_queue.csv (includes each lead's full Instantly record as JSON)
- Raw Instantly records captured before any change: ~/advero/state/reactivation/raw/<email>.before.json
- Suppression for Lead Gen dedupe: ~/advero/state/reactivation/do_not_reload.csv (email, suppress_until, added_ct, reason)

Rule (Lorenzo, 2026-10-21)
- Opt-out or clear no = no email for the current campaign plus 3 months, then back into sequences.
- Re-contact once a quarter for 6 months: next contact = reply date + 3 months, second contact = + 6 months.
- No permanent do-not-email for anyone (email_allowed = yes).
- Lead Gen dedupe must skip every email in do_not_reload.csv until its suppress_until date, so they are not re-pulled or re-loaded early.
- COO flagged on 2026-10-21 that CAN-SPAM requires honoring opt-outs with no expiry; Lorenzo chose this rule.

Adding new ones
- Future clear no-interest and opt-out replies get appended the same way: one row in the Reactivation tab and the CSV (same columns, notes left blank), one row in do_not_reload.csv with suppress_until = next contact date, and the case file + handled.jsonl updated.

## Canonical list (updated 2026-10-21 11:00 CT)
The canonical reactivation list is the "Reactivation" tab of "Advero CRM & Accountability" (sheet id 162UL8KgMo2U--ArMl0ieBE19LqcOWjmkYdFbBbqXj9s), maintained by Revenue Operations. The Reactivation tab in the Advero Lead Pool sheet is superseded; do not write to it.
