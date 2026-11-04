# Handoff: Zoom-only calendar (no Meet alongside Zoom)

**When:** Tue Sep 29, 2026 ~10:40 CT  
**By:** COO / Grok Bot  
**Ask:** Lorenzo/COO — strip Meet from Ilmi Wed Sep 30 invite; encode permanent Zoom-only booking rule; check Dawnn Oct 5.

## Verification (get_event proof)

### Ilmi — YES Meet gone
- Primary event id: `vfj1q3q57ug82rj6c3kb3cc9t8`
- Calendar: `[REDACTED]`
- Wed Sep 30 2026 2:00–3:00pm CT — Pricing Call - Ilmi Curovic / Shining Armor Cleaning NJ
- Before: `conferenceUrl` https://meet.google.com/mcx-zzvk-wsm + Meet conferenceData
- After: `conferenceData: {}`, no `conferenceUrl`
- Location still Zoom: https://us06web.zoom.us/j/83593576911?pwd=ZuIxwcDrEK5hNdHRTDeoamHTPr5OIw.1 (id 83593576911, passcode 496021)
- Twin Zoom-sync `cpo2v4fm0nre8vj3inkf8paf04` was already Meet-free
- Strip method: Chrome (account `/u/1`) → Edit → Remove conference (`#xRemRtcBu`) → Save → **Don't send** (silent; no extra lead email)
- Updated: 2026-09-29T15:39:46Z

### Dawnn — YES Meet gone (also stripped)
- Primary event id: `4neqch19e50b3agq17qno7eoag`
- Mon Oct 5 2026 11:00–11:15am CT — Discovery Call — Dawnn Clisby / Dc Workforce Solutions
- Before: `conferenceUrl` https://meet.google.com/han-owza-hdu
- After: `conferenceData: {}`, no `conferenceUrl`
- Location still Zoom: https://us06web.zoom.us/j/85045477391?...
- Strip: same UI path, Save → Don't send
- Updated: 2026-09-29T15:41:47Z
- Twin Zoom-sync `trtn7gh8bt5vt34rberosbekcc` was already Meet-free

## Permanent fix encoded
- Updated `~/advero/skills/booked-calls.md`:
  - Hard rule: calls run on Zoom only; never Meet+Zoom
  - New section **Zoom-only calendar booking (HARD)** with required strip-before-notify path, MCP limitation, API/UI strip steps, auto-Meet toggle OFF instructions
- Appointment Setter ping: `~/advero/state/queue/appointment_setter_zoom_only_20260929.md`

## Remaining for Lorenzo (optional, not blocking Ilmi)
1. **Turn off auto-Meet** on Advero calendar: Calendar Settings → Event settings → "Automatically add Google Meet to all events I create" → OFF (signed in as [REDACTED]). Until OFF, every `create_event` may re-attach Meet and strip step stays mandatory.
2. No lead re-notify needed for Ilmi/Dawnn strips (used Don't send).

## Blockers
- None for Ilmi Wed call. Guest sees Zoom only on primary.
- Calendar MCP still cannot remove conferenceData; browser UI or Calendar API PATCH required for strips.

## Auto-Meet calendar default
Tried Calendar Settings UI on /u/1 ([REDACTED]) 2026-09-29 ~10:42 CT: no visible Automatically add Google Meet toggle on main settings (only Speedy meetings / Gmail auto-events). Lorenzo should check Event settings under General, or Google Admin Workspace Meet defaults, and turn auto-add OFF. Until then, strip-after-create remains mandatory for Appointment Setter.
