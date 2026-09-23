# Assessment (private) - Virtual receptionist/secretary for heavy equipment dealership

## What the prop shows
- n8n canvas, 18 flow nodes, 6 sections: their 5 duties in their order plus an
  error alert. Voice layer is Retell (their own April 2025 history), which
  hands the call to n8n at 4 points: inbound ring (caller lookup and greeting
  language), mid-call inventory question, mid-call demo booking, and the
  post-call transcript. Invoices run from a short form the owner fills.
- Representative tools, stated on the overview sticky: HubSpot (CRM),
  QuickBooks Online (invoices), Google Sheet (inventory), Google Calendar
  (demos), Twilio (texts), call forwarding (phone). None is named in the post.
- Not drawn on the prop, needed in the real build: QuickBooks find-or-add
  customer before the invoice; a free/busy check on the demo calendar before
  booking; the HubSpot `phone_e164` unique property and the custom fields.

## Sizing (their numbers only)
- Call rhythm: 2-7 calls a day over a full-time 8-hour day = one call every
  1.1 to 4 hours. On the build (section 1 note, overview) and beat 2.
- Their posted seat: 40 h x 52 / 12 = about 173 h a month x $5-$15 = about
  $870 to $2,600 a month. Any retainer should land well under the top of this.
- Calls a month = 2-7 x their open days (not given). Illustration only, if
  weekdays: about 43 to 152 calls a month.
- Voice minutes = calls a month x their average call length (not given).
  Illustration only, at 4 minutes a call on weekdays: about 170 to 610 minutes,
  roughly $17 to $90 a month at $0.10 to $0.15 a minute.
- n8n executions: each call fires about 3 to 6 (ring, 1 to 3 questions,
  booking, 3 post-call events of which 1 is kept), so roughly 450 to 1,050 a
  month at weekday volume; inside n8n Cloud Starter's allowance.

## Time
- Discovery and their inputs (inventory, tools, hours, rules): 2 to 3 h.
- Retell agent: English/Spanish prompt, 2 custom functions (check_inventory,
  book_visit), inbound webhook, post-call analysis fields, number and
  forwarding: 6 to 8 h.
- n8n sections 1 to 5 plus errors, including the three steps not drawn above:
  12 to 16 h.
- Testing: 25 to 40 scripted calls in English and Spanish, owner test calls,
  latency tuning: 5 to 7 h.
- Texting registration (A2P 10DLC): about 1 h of paperwork, then 1 to 3 weeks
  waiting; calls and bookings can go live before it clears.
- Total about 26 to 35 h over 2 to 3 calendar weeks. Add 3 to 8 h if their
  CRM or invoicing tool is not HubSpot/QuickBooks; if their CRM has no API,
  fall back to a Google Sheet CRM (no extra time).
- Ongoing retainer work: 2 to 4 h a month (weekly call-log review, prompt
  fixes, inventory format issues, tool changes).

## Likelihood
- Winning the job: low to moderate. They asked for a full-time, entry-level
  human at $5-$15/hr and prefer Latin American hires; a retainer pitch
  contradicts the ask. In its favor: they already paid for a Retell
  investigation (April 2025), 0 interviews so far, and the pitch covers the
  back-office duties (invoices, CRM) a voice agent alone does not.
- Live-call latency: each mid-call hop (Retell to n8n to Sheets to Claude)
  adds about 2 to 4 s of silence. Retell can speak a filler line while the
  function runs; a fast model and a cached inventory cut it. Unverified until
  test calls.
- Spanish: Retell handles Spanish; callers who mix English and Spanish
  mid-call need testing. Unverified.
- Inventory source unknown. If it lives only on a listing site or in the
  owner's head, the first task is building the sheet, and someone must keep
  it current or the receptionist answers from stale stock.
- Phone system unknown. Most carriers support forwarding; conditional
  forwarding (after N rings, or after hours only) is the gentle rollout.
  Unverified for their carrier.
- CRM "very basic software" may have no API; HubSpot and QuickBooks are
  assumptions. QuickBooks sales tax on equipment is set in QuickBooks, never
  by the AI; amounts come only from the owner's form.
- Retell post-call webhook sends call_started, call_ended and call_analyzed;
  node 14 keeps only call_analyzed.
- Unverified for Lorenzo: Retell's current per-minute price and multilingual
  mode; the custom-function payload shape used here (`name`, `args`, `call`)
  and the inbound webhook response shape (`call_inbound.dynamic_variables`);
  n8n QuickBooks node field names (node 11 left at defaults); HubSpot batch
  upsert on a custom unique property. Frame honestly: built for them, shown
  with sample calls, nothing on their number until they sign off.

## Standard pricing
- Market setup for a Retell + n8n AI receptionist with CRM, calendar, texts
  and invoicing: about $2,500 to $6,000 one-time (agencies often $3,000 to
  $10,000).
- Market management retainer: about $300 to $1,000 a month plus usage;
  packaged AI receptionist services run about $300 to $1,500 a month.
- Recurring software (approximate, verify before quoting): Retell about $0.10
  to $0.15 a minute all in plus about $2 a month per number; Twilio texts
  under a cent per segment plus A2P registration fees (small one-time fees
  plus a monthly campaign fee); n8n Cloud Starter about $24 a month or
  self-hosted about $5 to $10; Claude API a few cents a call; HubSpot free.
- Their rate vs market: the post's $5-$15/hr full-time equals about $870 to
  $2,600 a month. Options that sit inside that: (a) setup $1,500 to $2,500
  plus $400 to $600 a month with usage at cost; (b) no setup fee, $700 to
  $1,000 a month all-in up to a call cap, 3-month minimum. Both are under
  the market setup price on purpose.

## Ask before quoting
1. Which phone carrier or system, how many numbers, and can it forward all
   calls or only unanswered and after-hours ones?
2. Open days and hours; how many calls come after hours; what share of
   callers speak Spanish?
3. Where the inventory lives today, how many machines, how often it changes,
   and who updates it.
4. The names of the "very basic software" for the CRM and invoices, and
   whether they have logins with API access.
5. Demo hours, who runs demos, how far ahead people can book, one at a time
   or several.
6. What the receptionist must never answer: price offers, financing,
   trade-ins, delivery, rentals.
7. Invoice terms: deposit, sales tax, payment methods, who decides an invoice
   goes out.
8. Should hot buyers be transferred live to someone's cell?
9. Have they tried a voice agent before, and what stopped it?
10. Are they open to a monthly retainer in place of paid hours?

## Flags
- Post/pitch mismatch: hourly, full-time, entry-level human. 19 connects.
- Preferred locations listed (US, Colombia, Mexico, Canada, Venezuela,
  Ecuador), not required; copy asserts no location.
- Account timezone America/Sao_Paulo while the client is in New Jersey;
  confirm the time zone before offering a call time.
- Very small lifetime spend ($271 over 3 contracts): price decides this.
- No portfolio demand; no rule against contact outside Upwork stated.
- Never claim it is live on their number; tools are representative.
- Contract shape: a retainer on Upwork is an hourly contract with a weekly cap
  or a fixed-price contract with monthly milestones; decide before the
  proposal.
