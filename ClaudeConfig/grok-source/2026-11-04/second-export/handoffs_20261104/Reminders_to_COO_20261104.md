# Handoff: Reminders to COO (2026-11-04)

## Job
When COO passes a pin from Lorenzo, create a one-off routine that reminds Lorenzo in the Reminders chat with his exact words. Use his time if given, else next weekday 9:00 AM CT (America/Chicago). Confirm routine name and fire time to COO. Log each pin in the state file. On fire: one short plain line with his words and the pin date, mark done, delete the routine. Never contact anyone else, no em dashes.

## Active routines (1)
- Name: Pin: Cancel GHL (Thu 11/12 10:00 AM CT)
  - Timing: once, Thu Nov 12, 2026 at 10:00 AM CT, exact (cron 0 10 12 11 *, America/Chicago)
  - Text: Reminder you pinned Thu 10/29 at 11:05 AM CT: "set a reminder for 14 days to cancel GHL". Time to cancel your GHL (HighLevel) subscription.
  - Goes to: Lorenzo, in the Reminders chat only
  - After firing: marks pin done in pins.md, deletes itself
  - Note: lives on the Reminders bot. If the bot is deleted before 11/12, COO must recreate it.

## Completed
- Pin: Upwork applications, fired Tue 10/27 1:43 PM CT, marked done, routine deleted.

## State files
- ~/advero/state/reminders/pins.md (columns: pinned, exact words, fire time, routine, status)

## Open items
- GHL cancel reminder (above) is the only open pin.
- Pin: Copy + ideation session (set Sun 11/1 7:45 PM CT, open). Found in pins.md; it has NO routine on this bot. Trigger is an event, not a time: remind Lorenzo when enrichment AND personalization have started (not just scraping). Topics: 1) variant testing, 2) exactly how much money to collect from new deals, 3) is a 15-min call ideal and how to stretch it, 4) applying Cialdini's Influence principles. COO should own watching for that trigger.
