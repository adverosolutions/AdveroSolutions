# Private assessment - Cal.com integration to GHL

**Rate vs market.** Post is $15-$38/hr, recorded bids avg $21.93. Market for GHL + Zapier setup work is about $40-$75/hr, or a fixed $150-$300 for this scope. At the top of his range it is about $75-$115 for the job. Worth it for the client, not the rate: 190 contracts, $75.9k spent, 4.99 over 102 reviews, and he has hired automation people before (n8n / Zapier / Make / GHL). A clean 2-hour job here is a door to repeat work. 11 connects.

**Time.** 2 to 3 hours of real work, 1 to 2 calendar days, gated by access.
- Cal.com setup, since he says the account still needs it: connect his calendar, one event type, availability, booking form fields (add phone if he wants it). 30-45 min.
- Two Zaps: Booking Created -> LeadConnector (GHL's Zapier app) create/update contact with Call Time, Call Notes and the call-booked tag; Booking Cancelled -> add call-cancelled. 30-40 min.
- GHL: pipeline + stages, 2 custom fields, 1 custom value, the workflow. 30-45 min.
- End-to-end test: book, reschedule, cancel, rebook with a test email. 30 min.

**Likelihood: high.** Standard parts, and the risk sits in his accounts, not the build. What breaks:
- **Zapier plan.** Free tier caps tasks per month and limits multi-step Zaps. One booking costs 1 task if the tag is set inside the create/update contact action, 2 if it is a separate step. Check his plan before promising a filter step.
- **Cal.com event types.** If he has more than one event type, which ones count as a "call booked"? Otherwise a 15-min chat lands in the pipeline too. Needs a filter on event type.
- **Reschedules.** Confirm in a live test that a Cal.com reschedule does not also fire the cancel Zap. If it does, a reschedule would look like a cancel. Also confirm whether a reschedule fires Booking Created a second time. Unverified until tested; do not promise the reschedule behavior on camera beyond "the card stays put".
- **Duplicate contacts.** Cal.com matches on email. A lead already in GHL under another email or phone-only makes a second contact. GHL's allow-duplicate-contacts setting and the Zap's match field decide this. Rebooks: the create/update opportunity step should update the same card; check the allow-duplicate-opportunities setting so a rebook does not open a second one.
- **Which calendar.** Cal.com reads his Google/Outlook calendar. The workflow does not put anything on a GHL calendar. If he wants the call on a GHL calendar too, that is an extra Zap action and a conflict risk. Ask.
- **Time zones.** His Upwork account is set to America/Sao_Paulo but he is in New York. Call Time must be formatted in his time zone in the Zap, and the GHL location time zone must match, or alerts show the wrong hour.
- **SMS.** The owner texts (steps 4 and 13) need a GHL phone number on the location. Can switch to email or in-app if there is none. Nothing texts the lead, on purpose: Cal.com only collects email by default.
- **Watch window.** The goal only catches a cancel while the contact is still in the 14-day wait. Match the wait to Cal.com's future-booking limit for that event type.

**Honest framing.** The Zapier leg lives in his Zapier account, so the Loom shows the GHL workflow built live in Lorenzo's account and the Zap drawn in the chart / section note. The Zaps get built in his account after access. Lorenzo has not shipped Cal.com's Zapier app specifically; frame it as the pattern, verify trigger names in his account.

**Option worth raising on the call (option only, not the pitch).** Cal.com can post a webhook straight into GHL's Inbound Webhook trigger, with no Zap in the middle. That removes the Zapier task cost and one moving part. Trade-off: GHL may bill Inbound Webhook as a premium trigger depending on his plan, and the mapping is done inside GHL. He asked for Zapier, so build Zapier unless he prefers this.

**Standard pricing (reference).** $150-$300 fixed, or 2-3 hrs at $40-$75/hr. Recurring software he already owns: Zapier (his plan), GHL (his plan), Cal.com (free tier is enough for one person; paid only for teams/routing).

**Ask before quoting.**
1. Is the Cal.com account set up yet (calendar connected, event type made), or is that part of the job?
2. Which Cal.com event types should land in the pipeline?
3. Does the Call Booked Pipeline exist already, and what stages does he want after the call (Showed / No Show / something else)?
4. Zapier plan tier, and is LeadConnector already connected to his GHL sub-account?
5. Should the booking also show on a GHL calendar, or is Cal.com the only calendar?
6. Who gets the alerts, and does the GHL location have a phone number for internal texts?
7. Access: GHL user on the sub-account, Zapier and Cal.com logins or team seats.

**Demo prerequisites not in the compiler's prereqs list** (create by hand in the demo account): custom fields `call_time` (Call Time) and `call_notes` (Call Notes), custom value `booking_link`, and pipeline stages Showed and No Show next to Call Booked and Cancelled. Pipeline name "Call Booked Pipeline", never the real "Sales" one.
