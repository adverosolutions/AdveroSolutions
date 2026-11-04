# Private preparation: GHL landing page and calendar funnel

20 October 2026. Original post: https://www.upwork.com/jobs/~022112504919683362216 . `jd.txt` is authoritative. Account/prepared-for name: your team. No client name, company, industry, offer or proof is known. Jamie Reed, Sam, introductory call, online meeting location, 30-minute duration, Oct22 at14:00 America/Chicago are clearly illustrative fixture choices. No invented testimonials, revenue figures, scarcity, logo, offer pricing or conversion lift.

## Distinct two-minute route

| Seconds | Stop | New fact and visible proof | Narration |
| --- | --- | --- | --- |
| 0–10 | Cover | Page + calendar + confirmation, prepared for your team | Approved opening caption verbatim. |
| 10–35 | Custom system overview | CTA → native GHL calendar → booking submit → next-step confirmation | “The page points to one action. The calendar handles availability and contact details, then opens the thank-you step.” |
| 35–60 | Public landing page | Clear appointment offer, primary CTA, duration and what happens next | Point at actual CTA and the short booking sequence. No native admin chrome on public content. |
| 60–95 | Neo booking | Same appointment, staff, selected time and timezone; Continue opens form, Schedule Meeting completes local sample | Point at available slots and timezone. Submit is required before local confirmation. |
| 95–108 | Confirmation | Jamie Reed, introductory call, Sam, online appointment, Oct22 at2PM CT,30min | “The confirmation keeps the appointment details the visitor just chose.” |
| 108–120 | Close | Booking completion, abandonment and mobile completion definitions; agreed baseline; reply-to-call | “Reply on Upwork and I'll send three times for a 15-minute call.” |

All four required demonstrations stay on the short route. No second canvas/empty admin page. If Lorenzo clicks landing CTA, that screen transitions locally into the calendar; separate chapters remain direct access to each surface. The generated source has no live integration or external iframe. This is an interactive sample, not production booking evidence.

## UI requirements and official sources

Read existing `catalog.json` and `references.json` first. Existing GHL workflow/Conversations references do not establish public funnel or calendar parity. GHL `productionReady:false` is not changed by this work.

- https://help.gohighlevel.com/support/solutions/articles/155000003552-calendar-widget-styles : select Neo ordinary calendar widget, keep its visual family distinct from Classic and Services v2.
- https://help.gohighlevel.com/support/solutions/articles/155000001529-calendar-widget-customization : official Neo appearance reference, including Continue placement note. Visually inspected https://s3.amazonaws.com/cdn.freshdesk.com/data/helpdesk/attachments/production/155014897818/original/gjK47oHkNCfIh1EE1GujIBvd3VT6uyg_Vg.png?1702299491 . Layout: left title, staff dropdown, duration/date/time/timezone; middle month/day grid and timezone; right slots; footer Continue right. The image itself shows December2023, despite updated2026 documentation. Historical pixels are qualified, not assumed current. A current actual-account widget/form/confirmation comparison is still needed for exact native acceptance.
- https://help.gohighlevel.com/support/solutions/articles/155000007763-using-custom-values-in-calendars : Calendar element redirect “Go to next step” and assigned user fields on next funnel step. Do not assume all appointment fields dynamically populate without testing actual merge fields.
- https://help.gohighlevel.com/support/solutions/articles/155000005610 : native editor path Sites → Funnels → Steps → selected step → Edit. This demo shows authored public pages; it does not invent an admin builder view.

Public landing/thank-you content is custom authored for this sample. The GHL booking widget is the native interior. Keep approved presentation shell, colors, Inter and opening/CTA unchanged. Do not add a calendar drawn like an admin dashboard, card-based fake appointment log or third-party Calendly branding.

## Implemented adapter contract

`kind:'funnel'`, `platform:'ghl'` with content `{surface,name,subtitle,brand,heading,body,cta,booking}`. `surface` is landing|booking|confirmation. Booking fields: service, durationMinutes, location, staff, staffOptions, dateISO, timezone, timezoneLabel, slots HH:MM, selectedSlot and contact{name,email,phone}. Dates and time text are derived in the renderer, preventing duplicated display-label mismatch. All three surfaces use the same nested entity tokens. Two statuses describe page entry and settled sample.

Shared scoped files are `templates/sales-deck/funnel_schema.py`, `runtime/funnel.js`, `runtime/funnel.css`. Python exports validate_funnel(scene,path), JS exports window.FunnelScreens.render(scene,job) and applyStep(scene,index). Native root only; main integrates schema dispatch, build assets and runtime calls. No outer shell changes from this worker. No live service call or backend import claim.

Interaction acceptance: CTA opens local booking; slot selection updates summary; Continue opens details; browser-native required/email validation; form Submit opens confirmation; repeated submit cannot duplicate sample appointment; Replay resets that public scene; re-rendering does not install duplicate listeners; keyboard-focus controls visible. Fixed sample availability, not real calendar availability. Only selected sample date is enabled; no invented currently available week. Need direct desktop1280/1440 and mobile390 check plus source comparison and independent review before recording readiness.

## Proposal/screening boundary

The post asks for similar work and approach. Explain single CTA, booking within funnel, confirmation and mobile validation. Confirmed fact: Lorenzo sets up GHL accounts routinely. No supplied verified GHL funnel examples; do not invent links or call adverosolutions.com a GHL build. Pricing stays for the call. Final screenshot/spec review is independent main-owned work; worker self-review does not approve production.

Verification update: full schema.validate passes. Adapter node syntax check passes. Isolated headless Chrome tested the same shared public adapter at1440/390 with medspa fixtures: calendar routing, slot summary, form/submit confirmation, cross-chapter data continuity and containment; no page errors. Specs and public screenshots require main-owned whole-page independent review. This worker's review was a self-review.
