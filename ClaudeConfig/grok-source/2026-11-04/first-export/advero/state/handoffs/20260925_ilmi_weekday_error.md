# Error: Ilmi N3 wrong weekday — 2026-09-25

## What happened
Ilmi N3 sent ~16:27 CT said "on our call on Thursday". Calendar event was **Wed Sep 23 11:30–11:45 CT** (attendee [REDACTED], accepted). Sopio Thursday was correct; Ilmi was copy-pasted.

## Source of wrong day
GHL Call Time field showed Thu Sep 24 2pm ET (stale/wrong). CoS/Calls used that / Sopio pattern instead of Google Calendar.

## Rule (going forward)
Before filling `{weekday}` on any no-show email: read the lead's calendar event start. Never use another lead's day or a GHL Call Time field alone.

## Fix pending
Lorenzo approval for in-thread correction (Wednesday + same slots). Update GHL note.
