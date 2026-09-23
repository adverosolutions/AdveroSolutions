# Private assessment — not for the proposal

**Post:** $200 fixed, expert level, client in Canada. Avg bid ~$203.

## Time
10-14 focused hours, spread over 5-8 calendar days. Two Make scenarios (outbound
on the Workiz event, inbound on the Quo reply) plus a third small one for the
approve/edit callback. The build itself is maybe 4 hours. The rest is account
work: getting a Workiz webhook to actually fire on "assigned to me", getting a
Quo/OpenPhone API key and an inbound-message webhook, and testing against a real
number. Add 2-3 hours if the pre-approved template library has to be written
rather than handed over.

## Likelihood — what actually breaks
- **Workiz webhooks are the top risk.** Workiz has an API and webhook support,
  but whether a *job assigned to a specific technician* event is exposed, and on
  which subscription tier, has to be confirmed in his account before quoting. If
  it is not exposed, the fallback is polling the Workiz API on a schedule, which
  changes the build and adds Make operations.
- **Quo / OpenPhone API access is plan-gated.** Sending from his existing number
  by API, and receiving inbound-message webhooks, has historically required a
  higher plan tier. Verify he has API access on his current plan, not just the
  app.
- **The approval loop needs a real surface.** Slack is the clean default. If he
  wants approval inside a Quo internal thread instead, that is a parsing problem
  (read the internal comment, decide approve vs edit) and is meaningfully more
  work than a Slack button. Ask which one before quoting.
- **Canada SMS compliance.** These are commercial electronic messages under CASL,
  so consent has to already exist for the number being texted, every message
  needs sender identification and a working opt-out, and STOP has to actually
  stop the sequence. Not a blocker for a service-appointment text to an existing
  customer, but it needs a consent field checked before the first SMS fires and
  an opt-out branch. Worth naming out loud; most bidders will not.
- **AI picking a template is the easy part.** Constraining it to a fixed library
  with a confidence score and a human gate is well-trodden. The failure mode to
  design for is low confidence, which should route to "no suggestion, rep writes
  it" rather than a bad guess.

## Standard pricing
Market for this scope: **$1,200-2,000 fixed**, or $90-130/hr. A three-scenario
Make build with an AI classifier, a template library, and a human-in-the-loop
approval step is not a $200 job. The post is at roughly 10-15% of market and the
average bid confirms nobody is correcting it.

Recurring costs the client carries: Make plan (~$10-30/mo at this volume),
OpenAI API (a few dollars a month at realistic job counts), and whatever
Quo/OpenPhone tier the API requires.

Bid low on purpose if he wants the logo and the review, but go in knowing $200
buys roughly the build and one round of testing, not open-ended iteration on
their account access.

## Ask before quoting
1. Which Workiz plan, and are webhooks already enabled? Which event fires when a
   job is assigned?
2. Quo/OpenPhone plan tier — is API access and an inbound-message webhook
   available on it today?
3. How many jobs per day, so Make operations can be sized?
4. Where does the rep approve: Slack, a Quo internal thread, or a text back?
5. Do the pre-approved templates already exist, and how many?
6. Is customer consent to text already recorded in Workiz, and is there an
   existing opt-out process?
7. Who owns the Make and OpenAI accounts, and will he get access or does this
   get built in Lorenzo's and handed over?
