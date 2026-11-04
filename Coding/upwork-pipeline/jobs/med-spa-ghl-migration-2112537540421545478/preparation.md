# Private preparation: med spa migration

Status: preparation only, 20 October 2026. No generated page, backend import, live send or review approval. Original: https://www.upwork.com/jobs/~022112537540421545478 . `jd.txt` remains authoritative. Prepared-for/account fallback: **your team**. Company, contact and clinic addresses are unknown.

## Story and fixture

Goal: move Mindbody/Mailchimp contacts into a two-location GHL booking and follow-up system while preserving opt-outs. The main success fixture is **Jamie Reed**, jamie.reed@example.com, +1 202-555-0148, synthetic contact `sample-med-101`. Sample appointment `sample-appt-101`: Location 1, Botox consultation, 30 minutes, staff Riley, Thu 22 Oct 2026 14:00–14:30 America/Chicago. These location/staff/duration/timezone choices are illustrative, not facts about the business or clinical advice. Location 2 offers staff Jordan; filler consultation is 60 minutes. Do not invent a discount, clinical outcome or treatment eligibility. Offer heading: “Book your Botox or filler consultation”; CTA: “Choose your location”.

Calendar implementation choice for the bounded sample: ordinary Neo Round Robin calendars, one calendar per location/service (four fixture calendars), with eligible staff and duration attached to each calendar. The public landing location/service choices route into the corresponding widget. Do not fabricate a combined ordinary-calendar location/service dropdown. Do not blend Services v2 navigation or Service Booking triggers into this choice. Services v2 is a possible production alternative after checking account enablement; it needs its own adapter.

Exception fixtures are distinct: Morgan Lee, `sample-med-102`, has a No-show appointment `sample-appt-102`; Taylor Quinn, `sample-med-103`, has a historical SMS opt-out; Casey Lane, `sample-med-104`, is the missed caller. Never show Jamie simultaneously as Showed and No-show. Historical service tags demonstrate migration, not new marketing permission.

## Two-minute scene map

| Time | Stop and purpose | New visible evidence | Spoken cue |
| --- | --- | --- | --- |
| 0–10s | Cover | Prepared for your team; two locations; Mindbody + Mailchimp → GHL | Locked opening caption verbatim. Then “This starts with your existing contacts and follows a booking through to the visit.” |
| 10–42s | GHL workflow mechanism | Appointment Status = Confirmed trigger, four calendar filters, Booked stage update, 24h/2h waits with separate SMS and email actions. Same screen exposes distinct No-show and Showed workflows using an outside-frame presenter selector, not fake native tabs. | “Both reminders use the appointment time. A no-show gets a rebooking message; a completed visit gets the review request.” Point at actual trigger/action labels. |
| 42–78s | Public three-step funnel | Landing CTA → location/service choice → real Neo-layout date/time + staff widget → details form → booking submit → thank-you page. Confirmation shows Jamie, Location 1, Riley, 30 minutes and Oct 22 at 2 PM CT. | “Jamie chooses the location and service, then Riley and an open time. The thank-you page shows the appointment she just booked.” |
| 78–99s | GHL Conversations, results | Jamie SMS/email 24h and 2h reminders with timestamps; showed review request at 16:30. Presenter switches contact to Morgan's no-show rebooking and Casey's missed-call text, bounded within same distinct screen. | “These are the messages each trigger creates. The review request follows an attended visit, two hours after it ends.” |
| 99–110s | GHL contact/pipeline outcome | Taylor's historical service tag and SMS DND evidence; Jamie in Showed, Morgan in No-show. This extra stop is justified by import suppression and stage requirements, not repeated canvas proof. Use actual Contacts view then Opportunities only if both references/adapters exist. | “The import keeps Taylor's SMS opt-out. New leads, bookings and attended visits have their own stages.” |
| 110–120s | Close | Three directional measures and clear call ask | “Reply on Upwork and I'll send three times for a 15-minute call.” |

Keep all requested outputs on the two-minute route. If the final two native states cannot fit at readable size, target 130–140 seconds instead of combining unrelated GHL surfaces into a fictional dashboard. Quick must still show landing, booking, confirmation, appointment timing and opt-out outcome; do not hide these behind Detailed. Optional detail: four-calendar settings, import mapping preview, complete message bodies. No repeated scene for workflow final node vs “execution”.

## Workflow semantics and visible sample output

- Confirmed appointment → create/update the same opportunity in Booked → wait until 24h before start → SMS and email → wait until 2h before start → SMS and email. Check still valid/current before each send; cancelled/rescheduled events stop stale reminders. Late bookings skip a past reminder rather than sending both immediately. Jamie reminder timestamps: Oct 21 14:00 and Oct 22 12:00 CT.
- Separate Appointment Status = No-show trigger → no-show stage → consent/DND check → rebooking SMS. Morgan sample: “Hi Morgan, we missed you today. Would you like to book another time?” Do not invent an actual reply or a new booking.
- Separate Appointment Status = Showed trigger → Showed stage → wait to **appointment end + 2h** → eligible review request. Jamie: end14:30, request16:30. If the chosen Wait UI anchors to start, offset must include service duration (150 minutes for this 30-minute appointment, 180 for a 60-minute appointment); do not silently equate two hours after start with two hours after visit. Verify event-end custom field/mapping before claiming production implementation.
- Missed-call sample: independent inbound missed-call event → eligible SMS text-back; never wire it from appointment confirmation. Casey: “Sorry we missed your call. Were you looking to book a consultation?” Built-in feature can text on every missed call; if using that feature show its actual settings, not a made-up workflow trigger. Repeated-call deduplication is an implementation choice, not a native feature claim.
- Jamie 24h SMS: “Hi Jamie, a reminder for your Botox consultation tomorrow at 2 PM with Riley at Location 1.” Email subject “Your appointment tomorrow”; body repeats exact date, staff, location and duration. 2h versions say “today at 2 PM”. Review sample: “Hi Jamie, thanks for visiting today. Would you leave a review of your visit?” A future production review URL stays private; no fake clickable live review link.
- Pipeline minimum: New lead → Booked → Showed, with No-show exception stage. Each transition requires a corresponding action/event. No sales value invented for consultation bookings.

## Contact import plan and proof boundary

Around 4,000 is the post's source estimate, never an achieved import count. Export Mindbody contact/service data and Mailchimp subscribed/unsubscribed/cleaned status; normalize and deduplicate email/phone, retain external IDs, service tags and per-channel opt-out evidence. Keep automation enrollment disabled through migration and suppression checks. A previous Mailchimp unsubscribe does not create SMS consent. Unknown SMS permission stays held; never infer it from a service tag or a populated phone field. Previously opted-out SMS remains blocked. Do not clear existing GHL DND during merge.

Official CSV docs say the generic DND column applies all channels. Therefore use that as a conservative quarantine, or apply channel-specific DND through the documented workflow action before any sending enrollment. Do not claim CSV's single DND column is SMS-only. Channel-specific release requires positive source permission and reconciliation, not blanket DND removal. Visible illustrative proof: Taylor, `past-service:filler`, `source:mindbody`, `sms-opt-out`, outbound SMS DND enabled, no SMS generated. A sample proof is not an imported live record.

## Exact references and qualification

Existing catalog read first: `templates/sales-deck/visual-reference/catalog.json`, `references.json`; GHL catalog remains productionReady:false. Existing workflow reference `assets/ghl-workflow-a40574215114.png` is useful for dotted canvas/top Builder, Settings, Enrollment History, Execution Logs controls. Existing Conversations refs `ghl-conversations-30e383a67a3b.png` and `862e469c1971.png` cover inbox/thread/details structure. `ghl-contact-2beadb770b86.png` is Appointments-list entry point only, not an open overlay.

Official sources checked 20 October 2026:

1. https://help.gohighlevel.com/support/solutions/articles/155000003552-calendar-widget-styles : ordinary Neo widget identity and supported staff selector.
2. https://help.gohighlevel.com/support/solutions/articles/155000001529-calendar-widget-customization : Neo widget appearance and July2026 Continue-position note. Inspected image https://s3.amazonaws.com/cdn.freshdesk.com/data/helpdesk/attachments/production/155014897818/original/gjK47oHkNCfIh1EE1GujIBvd3VT6uyg_Vg.png?1702299491 . Exact observed layout: left calendar title/description, staff dropdown and duration/date/time/timezone summary; middle month and day grid; right vertical slots; timezone selector under grid; Continue bottom right. **Screenshot contains December2023; it is historical shape evidence, not proof of latest exact pixels.** Obtain current widget/form/confirmation capture before native parity approval.
3. https://help.gohighlevel.com/support/solutions/articles/155000007763-using-custom-values-in-calendars : funnel Calendar element redirect “Go to next step”; assigned user values can populate next step. Does not prove every arbitrary appointment field propagates.
4. https://help.gohighlevel.com/support/solutions/articles/155000002619-workflow-trigger-appointment-status : status/calendar filtering. https://help.gohighlevel.com/support/solutions/articles/155000002470/ : event-relative waits and past-date handling. Endpoint does not establish an appointment-END toggle; verify mapping explicitly.
5. https://help.gohighlevel.com/support/solutions/articles/155000003905 : CSV import DND caveat. https://help.gohighlevel.com/support/solutions/articles/155000003270-workflow-action-dnd-contact : direction/channel-specific DND.
6. https://help.gohighlevel.com/support/solutions/articles/48001239140-where-and-how-to-configure-the-missed-call-text-back-feature : Settings → Phone System → Voice settings and communication preferences. Do not use older Business Profile screenshots for the current path.
7. https://help.gohighlevel.com/support/solutions/articles/155000005610 : Sites → Funnels → Steps → chosen step → Edit. Public pages are authored client content, not GHL's editor. Avoid adding an editor scene unless it supplies distinct necessary proof.
8. Alternatives only: https://help.gohighlevel.com/support/solutions/articles/155000003546 and https://help.gohighlevel.com/support/solutions/articles/155000006140 . Inspected Services v2 settings and Service Booking trigger images. Separate multi-location Services model; requires account enablement and a separate trigger family. Do not depict private-beta Services notifications as generally available.

## Minimal typed adapter contract requested

These are proposed fields, not keys already accepted by the current compiler. Main must map them into schema/adapter maintenance explicitly.

```ts
type CalendarFixture = {
  id: string; locationId: string; locationLabel: string;
  serviceId: string; serviceLabel: string; durationMinutes: number;
  staff: {id: string; name: string}[]; widgetStyle: 'neo';
  timezone: string; slots: {startIso: string; endIso: string}[];
};
type AppointmentFixture = {
  id: string; contactId: string; calendarId: string; staffId: string;
  startIso: string; endIso: string;
  status: 'confirmed'|'showed'|'no-show'|'cancelled';
};
type PublicFunnelScene = {
  adapter: 'ghl-public-funnel';
  steps: ['landing','booking','thank-you'];
  offer: {heading: string; body: string; cta: string};
  calendars: CalendarFixture[]; appointment: AppointmentFixture;
  contact: {id: string; name: string; email: string; phone: string};
  consent: {sms: 'granted'|'denied'|'unknown'; email: 'granted'|'denied'|'unknown'};
  initialState: 'landing';
};
type AppointmentRule = {
  event: 'confirmed'|'showed'|'no-show'|'missed-call';
  calendarIds?: string[]; anchor?: 'start'|'end'; offsetMinutes?: number;
  channels: ('sms'|'email')[]; pipelineStage?: string;
};
type SuppressionFixture = {
  contactId: string; serviceTags: string[];
  smsPermission: 'denied'|'unknown'; outboundSmsDnd: true;
  source: 'mindbody'|'mailchimp'; messageDisposition: 'blocked';
};
```

Adapter requirements: public three-step stateful funnel, actual Neo date/time → details → confirmation form, location/service calendar routing, same appointment entity passed to native results, event-relative wait inspector, distinct status and missed-call mechanisms, contact DND and pipeline proof. Public Calendar slot selection must not itself confirm; Submit creates local sample appointment, next step confirms it. Changing calendar/staff/date clears stale selections. Back preserves contact draft; duplicate Submit does not create another appointment. Show result settles public thank-you; Replay resets that scene's sample state only. No network, real embed or service calls. Outside-frame presenter controls may select fixtures; never style these as invented GHL controls.

## Close, proof and proposal needs

Directional measures: booking completion (confirmed bookings / booking-step starts), show rate (Showed / appointments due), suppression accuracy (known opt-outs with zero prohibited sends / known opt-outs checked). Establish baseline together; no uplift or achieved performance claim. Strong blue reply-to-15-minute-call CTA; three times wording.

Screening gaps stay private: no confirmed medspa/healthcare-specific build experience; confirmed dental-practice experience can be mentioned narrowly. No verified GHL funnel portfolio URLs in available facts. Do not claim adverosolutions.com is a GHL build. No A2P approval count or registration completion claim. Price: “we can cover that on the call”. Requested two-week launch is a client target, not proven delivery; estimate 7–14 days after account/access/content review with testing, without guaranteeing external approvals. Test location/staff/duration conflicts, both reminder channels/times, reschedule/cancel, no-show vs showed, repeat missed calls, review end-time anchor, opt-out merge and unknown consent before launch. Self-reviewed for requirements and continuity; not independent approval.

## Implemented bounded revision (supersedes proposed native scene map/contract above)

The actual `deck-spec.json` uses the approved maintenance instruction: **custom system overview → public landing → Neo booking → public confirmation → custom timing/opt-out record**. Native GHL appointment workflow/Contacts/DND/pipeline views lack an accepted adapter and are not fabricated. Mechanism and test-fixture record are labeled custom; they describe planned native GHL behavior without implying live logs. Public customer pages are authored content. This is five distinct mechanism/result stops, with the last stop required for original import and follow-up cases. Recording target is about two minutes; allow 130seconds if message proof needs more time.

Implemented public contract is smaller than the initial proposal: content `{surface,name,subtitle,brand,heading,body,cta,booking,choices?}`, with surface landing|booking|confirmation. Booking `{service,durationMinutes,location,staff,staffOptions,dateISO,timezone,timezoneLabel,slots,selectedSlot,contact:{name,email,phone}}`. Optional choices contain `{id,service,durationMinutes,location,staff,staffOptions,slots}`. This is ordinary Neo calendar routing, not invented native location/service selectors. Main adds dispatcher/result-gate integration and reviews page hashes. No queue/lock/catalog modifications by worker.

The timing proof includes actual sample text for reminder, review request, no-show rebooking and missed call; stage progression is explicit text in the custom record. Review request fixture is end14:30 +2h=16:30. Contact Taylor is SMS DND held, not shown receiving a text. The original estimate “around4,000” is confined to private source evidence. Known unknowns remain in this note.

## Final native-workflow revision and verification

Main added the verified `appointment_status` action catalog/allowlist. The first required scene now is an actual **native GHL reminder builder**, replacing the custom architecture: Appointment Status=Confirmed → Wait24h → SMS → Email → Wait2h → SMS → Email. Calendar group “Both locations” contains the four illustrative location/service calendars. Trigger Contact only. Each Wait inspector uses the documented appointment-event-relative Before setting and past-date Skip-outbound behavior. Separate SMS and email nodes preserve real action semantics; seven compact native nodes require internal canvas panning. Additional automation branches remain custom proof, not invented nodes.

Final route is native reminder builder → public landing → Neo booking → confirmation → custom timing/opt-out record. No extra duplicate workflow. Cancellation and reschedule cleanup is a production test/implementation requirement, not claimed as a guard represented by the seven-node reminder graph. No-show, showed, missed-call and import handling in the custom record are distinct fixture paths.

Verification: both complete job specs pass current schema.validate with current platforms catalog. `node --check` passes adapter JS. Isolated headless Chrome with temporary profile passed routing between four location/service choices, selected slot summary, Continue/form/Submit confirmation, selected-slot continuity across public chapters,390px containment and no page errors. Worker inspected screenshots at1440 and390. Screenshots in /tmp/medspa-funnel-landing-1440.png, booking-1440.png, form-1440.png, confirmation-1440.png and booking-390.png (each carries full medspa-funnel prefix). These are self-review of the bounded adapter, not full-page independent review or current-account native parity certification. No queue, lock or catalog mutation by worker.
