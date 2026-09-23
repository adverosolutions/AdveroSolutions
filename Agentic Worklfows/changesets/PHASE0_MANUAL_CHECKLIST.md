# Phase 0 manual checklist (Lorenzo)

Everything below is a hand step in a UI or account that the automation cannot and must not touch. Nothing in `changesets/` is applied until you tick the corresponding box in `runbooks/phase0.md`. Dates as of 2026-09-21.

## Order of operations (read this before picking a section)

The sections below are numbered by subject, not by sequence. **Do them in this order**, because the
first one unblocks most of the rest:

1. **Section 3, the GHL Private Integration token.** Everything else in the build is downstream of it.
   Without it: the calendar timezone in DECISIONS A5 cannot be read, so every "12:00 to 18:00 CT" slot
   the engine offers is unverified; `shared.ghl.get_free_slots` returns nothing, so cadence D2's
   `SKIP_STALL_DAYS=2` stops every armed lead after two days; `jobs/appointments_tick` has no
   appointment source at all and the show-rate and no-show sequences do nothing; the "reply C" a lead
   sends to the GHL reminder cannot be read, so the 4 h chase task fires on every booking; and the
   store rows a vetoed booking leaves behind cannot be cleaned up from the calendar. It is fifteen
   minutes of clicking and it is the critical path.
2. **Section 2, A2P 10DLC.** Approval takes 3 to 7 business days, so it is second only because it is a
   queue: start it the same day. Every SMS leg in S4 and S5 is dead until it clears.
3. **Section 1, Zoom and the calendar rules.** Needs the token to verify (the timezone read, the
   availability window, the event title), and Zoom is what makes no-show detection possible at all.
4. Then sections 4 to 8 in any order.

## 1. GHL: Zoom, calendar rules, phone required

> Do section 3 first: every checkbox here that says "confirm" needs the token to confirm anything.


- [ ] Profile (top-right avatar) > My Profile > Calendar Settings > Video Conferencing > Connect Zoom, authorise the AdveroSolutions Zoom account. ids.json shows `isZoomAdded=false` today.
- [ ] Calendars > Discovery Call (id `GDugwLmZNdsD13RBDnRu`) > Meeting Location: change from Google Meet to Zoom (Zoom: use the connected account, unique link per booking). Keep Fireflies on the invite.
- [ ] **Confirm the calendar's timezone before anything else on this list.** Settings > Business Profile (or the calendar's own Availability tab) must read `America/Chicago`. Nothing in Phase 0 has ever read it: `config/ids.json` records the window as "Mon-Fri 12:00-18:00 (calendar timezone follows the location)" with no timezone for the GHL location, and there is no GHL token in any `.env`, so no script can check it. If it is on Eastern, the same window is 11:00 to 17:00 CT: every slot the cadence offers as "12:00 to 18:00 CT" per `config/offers.md` rule 2 is an hour off, a 17:00 to 18:00 CT booking is rejected by the widget, and Ilmi's 11:30 CT slot is legal after all (so the line below about it being outside the window is wrong). Write what you find into `config/ids.json` as `ghl.location_timezone` and tell the next session, which adds a test that it equals `shared.settings.TZ`.
- [ ] Same calendar > Availability: keep Mon to Fri 12:00 to 18:00, slot 15 min, buffer 15 min, minimum notice 4 hours. Change "Allow booking for" from 30 days to 7 days (5 business days is the rule; GHL counts calendar days, so 7 gives Mon to Fri plus the weekend).
- [ ] Ilmi Curovic already holds Wed Sept 23 at 11:30 CT, which is outside the 12:00 to 18:00 window you are about to enforce **if that window is Central** (see the timezone item above). Narrowing availability does not move an existing appointment, so leave it where it is and confirm it with `changesets/drafts/ilmi_wednesday_confirmation.md` (section 8).
- [ ] The two calls already booked this week (Ilmi Wed Sept 23, Sopio Thu Sept 24) are **not** GHL bookings. They are hand-made Zoom meetings on Lorenzo's own Google Calendar (events `eqlug7qn67rnjdppja91ffuto0` and `j8n9pmfjl3cufeiu58g4kp12c8`, both carrying a real `us06web.zoom.us` link, verified read-only 2026-09-22). Connecting Zoom to GHL does not rewrite them and does not need to: the links on those two invites already work. Do not "fix" them.
- [ ] Same calendar > Forms and Payment > booking form: Phone = required.
- [ ] Same calendar > Notifications: keep auto-confirm on; reschedule and cancel links on.
- [ ] Event title: `Lorenzo <> {{contact.company_name}}: 15 minutes` (today it is `Discovery Call - {{contact.name}}`). Keep it offer-neutral: there is one Discovery Call calendar and all six campaigns book onto it, so a title that says "reactivation plan" contradicts the pitch for anyone arriving from cleaning_trigger, bookkeeping_trigger or recruiting_outbound. Tiffany Spelman is on cleaning_trigger and was sold a $24,000/yr new-contract guarantee, not a reactivation. If you would rather have offer-specific titles, that needs two calendars and two booking URLs in `config/ids.json`, which is a bigger change than Phase 0.
- [ ] The booking URL itself is already verified: `config/ids.json` records `booking_url_note: "VERIFIED 2026-09-21: HTTP 200, page title 'Discovery Call'. Safe to use in outbound copy."`, so do not re-test it. All that is left is to open `https://api.leadconnectorhq.com/widget/booking/GDugwLmZNdsD13RBDnRu` once after the Zoom switch and confirm the page now shows Zoom as the location.

## 2. A2P 10DLC registration (Low-Volume Standard)

Where: Settings > Phone Numbers > Trust Center (or Settings > Business Profile > A2P registration). Pick Low-Volume Standard (the blueprint quotes $24.50 one-time; confirm the current fee on the screen). Approval takes 3 to 7 business days; SMS legs in every sequence stay off until it clears.

One campaign's staged copy promises a text channel while this is pending: **cleaning_reactivation** (step 1 variant B says "email and text sequences"), which is sanctioned because its `config/offers.md` row says "Email + text sequences". No other campaign's copy may mention texting; recruiting_reactivation used to and no longer does, because its offers.md row offers no text leg. Until A2P clears, the text leg is a promise of what the build includes, not something that is sending.

Have ready before you start:
- [ ] Legal business name exactly as on the EIN letter, EIN, business address, business type (LLC / sole prop), website `adverosolutions.com`, industry.
- [ ] Authorised contact: your name, email, mobile.
- [ ] Campaign use case: "Mixed" (appointment reminders and follow-up with contacts who replied to us).
- [ ] Campaign description, two sentences: who receives texts (people who replied to our email and booked or requested a call) and what they get (confirmations, reminders, reschedule links).
- [ ] Opt-in description: contact gives their phone on the booking form after replying to an email; add "By booking you agree to receive appointment texts. Reply STOP to opt out." to the booking form.
- [ ] Three sample messages, with STOP language, e.g. "Hey {{first_name}}, Lorenzo here. Confirming our call {{time}} CT. Zoom link: {{link}}. Reply C to confirm. Reply STOP to opt out."
- [ ] Estimated monthly volume: under 2,000 (Low-Volume ceiling is 2,000/day across the brand; we will be far under).
- [ ] The number you will text from is on the same GHL location as the Discovery Call calendar.

## 3. GHL Private Integration token

**This is item 1 in practice. See "Order of operations" at the top.**

Where: Settings > Integrations > Private Integrations > New. Name it `advero-reply-engine`.

- [ ] Scopes to tick: `contacts.readonly`, `contacts.write`, `opportunities.readonly`, `opportunities.write`, `calendars.readonly`, `calendars.write`, `calendars/events.readonly`, `calendars/events.write`, `conversations.readonly`, `conversations.write`, `conversations/message.readonly`, `conversations/message.write`, `workflows.readonly`, `locations.readonly`, `locations/tags.readonly`, `locations/tags.write`, `locations/customFields.readonly`, `users.readonly`.
- [ ] Copy the token once (it is shown a single time) into `~/.advero/live.env` (chmod 600, outside the repo) as `GHL_PRIVATE_INTEGRATION_TOKEN=...`, **not** into any repo `.env`: agents can read those. Never paste it in chat or commit it.
- [ ] Mint a second Private Integration with **readonly scopes only** (`contacts.readonly`, `opportunities.readonly`, `calendars.readonly`, `calendars/events.readonly`, `conversations.readonly`) and put that token in `Agentic Worklfows/.env` as `GHL_PRIVATE_INTEGRATION_TOKEN_READ=...`. Full steps: `runbooks/read_only_keys.md`.
- [ ] Read-only check before anything else: `python3 -c "from shared.ghl import GHL; print(GHL().search_opportunities(limit=1))"` from the `Agentic Worklfows` folder. It must print one opportunity, not `None`.

## 4. ntfy (phone alerts)

- [ ] Install the ntfy app (iOS or Android) or open https://ntfy.sh in a browser.
- [ ] Either set `NTFY_TOPIC=advero-<something-private>` in `.env`, or let the engine generate one: the first notification writes the topic to `.tmp/ntfy_topic.txt` and includes the subscribe URL.
- [ ] Subscribe to that topic in the app. Send a test: `python3 -c "from shared.notify import notify; print(notify('Advero test', 'ntfy is wired'))"`.
- [ ] Optional email fallback: set `NOTIFY_EMAIL`, `GMAIL_SENDER_EMAIL`, `GMAIL_APP_PASSWORD` in `.env` (an app password, not your Gmail password).

## 5. Insurance domains and inboxes (M2: 8 domains, 23 inboxes, warm by Oct 11)

Warm-up needs 21 days from the day the inboxes start warming, not from the day you buy the domains. Buying on **Sept 22** puts warm-up completion at **Oct 13 at the earliest**, and only if DNS and inbox creation finish the same day; Oct 13 2026 is a Tuesday. The Oct 11 date in `config/ids.json` belongs to the existing 11 warming domains, which started warming 2026-09-20 23:39Z (Sept 20 + 21 days = Oct 11, a Sunday). So either treat **Oct 13** as the M2 readiness date for these 8 new domains, or buy today and accept that DNS and provisioning eat the buffer. Pattern: 3 inboxes per domain, personas `lorenzo@`, `lorenzov@`, `lorenzovillarreal@`, same as the 11 warming domains. 8 domains x 3 = 24 slots; use 23 (skip `lorenzovillarreal@` on the last domain).

Proposed names, all in the existing `advero` pattern, every one marked **check availability** before buying (nothing was queried):

| # | Domain | Inboxes |
|---|---|---|
| 1 | adverolabs.com | lorenzo@, lorenzov@, lorenzovillarreal@ |
| 2 | adverodigital.com | 3 |
| 3 | adveroworks.com | 3 |
| 4 | adverogroup.com | 3 |
| 5 | adverosystems.com | 3 |
| 6 | useadvero.com | 3 |
| 7 | hiadvero.com | 3 |
| 8 | adveroco.com | 2 (lorenzo@, lorenzov@) |

Backups if any are taken: adveroagency.com, adveroconsulting.com, goadvero.com, adveroconnect.com.

Order:
- [ ] Buy the 8 domains (~$12 to 15/yr each), set DNS to the provider the other 11 use.
- [ ] Create 23 Google Workspace inboxes (Zapmail ~$3.00 to 3.50 or Instantly DFY $5/mo), SPF, DKIM, DMARC on every domain.
- [ ] Add to Instantly with warm-up on, daily limit 25, warm-up limit 10; tag them `insurance` so the deliverability monitor (A4) can tell them from `active`.
- [ ] Do not add them to any campaign `email_list` until Oct 11 and only after the Phase 2 monitor promotes them.

## 6. Instantly UI-only toggles

The API cannot set these, so they are done in the UI after the Phase 0 change-set is applied.

- [ ] Each of the six campaigns > Settings > "AI Smart Pause" (auto-pause on out-of-office replies): ON. Keep "Stop on auto reply" OFF (already off on all six).
- [ ] Each campaign > Sequences > Preview: click through 5 leads and confirm the spintax renders (no literal `{{RANDOM`), `{{personalization}}` is line one, and step 3 shows as a new subject line.
- [ ] Confirm the step timing on the preview timeline reads day 0, day 3, day 7. The one failure mode to look for is **step 1 on any day other than day 0**: if step 1 reads day 3, `delay` is a pre-delay (the wait before its own step, not before the next one), every new lead waits three days for the first email, and the timeline will read day 3 / day 7 / day 10. In that case restore from the pre-apply backup, shift each delay one step earlier, set step 1 to 0, rebuild with `build_sequences.py`, re-run the tests and re-apply (runbooks/phase0.md go-live step 7).
- [ ] cleaning_trigger only: do not switch variant B on until the lead list carries `buildingType` and `metro` (Leads > check a lead > custom fields).
- [ ] After lead labels are created: Settings > Lead Labels > confirm all 11 exist with "AI" **off** (R9: AI labelling stays off until every detector reads the values recorded in `changesets/instantly_phase0/lead_label_values.json`).
- [ ] TODO after the first live `--labels --apply`: add the `GET /lead-labels` response shape to `config/instantly_api_contract.md`, using the `value_key` recorded per label in `lead_label_values.json`, and confirm that file says `"complete": true` (11 distinct values, none a built-in interest code -4..4). The contract has no lead-labels shape today, so the value key is inferred.

## 7. Upwork (read-only, by hand)

- [ ] Messages > Invitations tab: ClosePoint USA and RoutVox Consulting are not visible through the API; open each, reply or decline by hand, following `changesets/drafts/closepoint_routvox_invitations.md`. There is no copy in that file on purpose: nobody can read what either client asked for, and inventing a client problem is the one thing the proposal rules forbid. The application flow itself is untouched (blueprint M6).
- [ ] Jennifer Lawson (contract 44491561, ended Sept 14, support window ended Sept 21): send `changesets/drafts/jennifer_l_review_ask.md`.
- [ ] Treasure Labs (Aysha Sanam, contract 44501032): send `changesets/drafts/treasure_labs_oct5_checkin.md` on Oct 5.

## 8. Other drafts waiting on you

- [ ] Sopio (Taxfo Accounting), today: `changesets/drafts/sopio_confirmation.md` from `lorenzov@theadvero.com` to `sopiosvanishvili@taxfoaccounting.com`, same thread.
- [ ] Tiffany (FlowerHill Facility Services): `changesets/drafts/tiffany_upfront_cost.md` from `lorenzovillarreal@adveromedia.com` to `tiffany@flowerhillfs.com`, same thread, fill the two slots and the link first. Read the draft header before you send: she already has an upfront price in writing from Sept 17, and the draft deliberately does not quote a second one.
- [ ] Mike (Man Transformed), by Oct 12: `changesets/drafts/mike_day25_renewal.md`, fill the results and the retainer price.
- [ ] Ilmi (Shining Armor Cleaning NJ), today: `changesets/drafts/ilmi_wednesday_confirmation.md` from `lorenzo@adveromedia.com` to `info@shiningarmorcleaningnj.com`, same thread. This is the only call inside 48 hours, so it goes out before the Sopio and Tiffany replies. Note this thread was already answered at 14:03 CT on Sept 21 ("I'll get the cal invite sent over", no time named) and she has accepted the 11:30 CT invite, so this is a second message in the thread, not a first reply. What it adds is the timezone question: she wrote "around 11:30" with no timezone and it was booked as Central.

- [ ] Nobody who has no draft here gets a hand-sent message this week. Two positives are deliberately not drafted: `ignacio@ariacleaningservices.com` asked on Sept 16 to be contacted next month and was told "sounds good, I'll be sure to check in", so he waits until October; `rob@cjsglobal.com` (cleaning_reactivation) proposed "2pm EST" for Friday Sept 18 and was marked `lt_interest_status -3` (lost) at 13:25 CT that same Friday (verified read-only 2026-09-22), so the outcome is already recorded and he is not a follow-up. Do not move either of them into the Interested-quiet subsequence.
