# Assessment (private) - Make.com Automation for Lead Follow-Up & CRM Setup

Prop: Make blueprint, 13 modules (plus Make's own Sample Input and Final Output
stand-ins), four sections in their words. GoHighLevel committed as the CRM via
API v2 HTTP calls; the post never names a CRM.

## Time
- Review of their current setup (Make scenarios, GHL sub-account, forms): 1.5-2 h
- Form to Make webhook, field mapping, test submissions: 1-2 h (more if the
  form tool cannot post to a webhook, see Likelihood)
- AI read-and-reply step, prompt tuned on 10-15 of their real past enquiries: 1.5 h
- GHL calls (upsert, note, opportunity, SMS, workflow enrol, task) with a
  Private Integration token, plus the failure route and alert: 2-3 h
- GHL follow-up sequence: 0.5 h if theirs exists and only needs "stop on
  reply" and a booked-appointment goal; 2-3 h if it has to be written
- End-to-end testing with real numbers, handoff notes, short Loom: 1.5 h
- Total: 8-12 h realistic, 14 h if the sequence has to be written from scratch.
  Calendar: 1 week part time, 3-4 working days if access arrives on day one.

## Likelihood
- CRM unconfirmed. GoHighLevel is inferred from their hires (GHL A2P 10DLC via
  Twilio, a GHL website). If they run a different CRM, steps 4-10 change;
  the flow shape stays. Ask first.
- Lead source unconfirmed. Their history shows a Squarespace form + Acuity job
  and a Wix Studio form build. As far as Lorenzo knows, Squarespace form blocks
  store to email, Google Drive, Mailchimp or Zapier and cannot post to a Make
  webhook; the workarounds are a Make mailhook on the form's notification
  email or swapping in a GHL form embed. Wix can send a webhook from Wix
  Automations on paid plans. Both unverified for this account; check on the
  call. Never mention their hiring history to the client.
- SMS: texting US numbers from GHL needs an approved A2P 10DLC brand and
  campaign or carriers filter the texts; their registration job closed on
  2026-09-17, so approval may still be pending. UK numbers do not need it. The AI
  step converts 07 mobiles to +44 because a GHL location set to US reads a UK
  local number wrongly; confirm the location's country.
- GHL API access: Private Integration tokens come from the sub-account
  settings; whether their plan and role allow creating one is unverified. The
  opportunity create call fails if the pipeline blocks duplicate
  opportunities and the contact already has one, which is why only new leads
  reach step 8.
- Make specifics to handle in the real build: a customer message containing
  quotes or line breaks breaks a raw JSON body (map it through Make's
  JSON module or escape it); the reliability route in the live build is an
  error-handler route on step 4 with "Evaluate all states as errors" set so
  the failure reaches the email, plus "Allow storing of incomplete executions"
  switched on. The blueprint shows it as a router because the compiler draws
  no error-handler routes.
- The router conditions (real enquiry, saved, new vs returning) do not carry
  over into the blueprint; set them on camera or before the demo
  (`{{3.result.is_real_lead}}`, `{{5.statusCode}}`, `{{5.data.new}}`).
- Make's OpenAI module needs the "parse JSON response" toggle (or
  response format JSON) so `{{3.result.first_name}}` resolves; check on import.
- Lorenzo has not verified the GHL `/opportunities/`, `/contacts/{id}/tasks`
  and `/contacts/{id}/workflow/{id}` calls on a live sub-account for this
  build; test each once before the demo.

## Standard pricing
- Market for a Make + GoHighLevel lead follow-up build with a review of the
  existing setup: $700-$1,400 fixed (10-12 h at $70-$120 an hour).
- Their post: $5-$40 an hour, so at most about $320-$480 for 8-12 hours.
  That is a third to a half of market. Their record ($720 across 52 contracts,
  about $14 each) says they buy small and cheap; quote a capped number of hours
  rather than an open hourly contract.
- Recurring: Make Core about $10-11 a month (each new lead uses about 7-9
  operations; the free plan's monthly allowance covers a small volume only);
  OpenAI roughly a cent or less per enquiry; GoHighLevel and its SMS fees they
  already pay.

## Ask before quoting
1. Is GoHighLevel your CRM? If not, which one?
2. Which form tool is on your site, and how many forms or lead sources feed
   leads today (site form, ads, booking page)?
3. What does your current Make setup do, and what goes wrong with it now?
   Can I get access to Make and your GoHighLevel sub-account for the review?
4. Do you already have a follow-up sequence in GoHighLevel, or should I
   write it? (moves the estimate by 2-3 h)
5. Roughly how many leads a month? (sets the Make plan)
6. First reply by text, email or both? Are your leads mostly UK or US
   numbers? Who takes the call-back tasks for repeat enquiries?

## Flags
- Low budget ($5-$40 an hour) against a real build and an audit; cap hours.
- Short-term, part time. No US-only restriction, no portfolio demand, no ban
  on contact outside Upwork in the post.
- 1 invite, 0 interviewing, 14 connects; bids average $44.04 (basis unknown).
- Their hiring history steers the tool choice only; it never appears in the
  build, the beats or the proposal as something we looked up.
