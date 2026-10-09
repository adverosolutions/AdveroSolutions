# Assessment (private) - AI Chatbot Website & API Integration

## Time
- Test as posted: 3 to 5 hours. Snippet on staging and configured 1 h (longer if the staging site is a page builder with script restrictions or a CSP), receiving webhook + field check + test sheet 1 to 1.5 h, five test chats and a short written result 1 h, troubleshooting buffer 1 h. One to two calendar days, gated on staging access.
- Next phase (CRM contact + Google Calendar booking per client onboarding): 6 to 12 hours per client pattern once the CRM is known; then 1 to 3 hours per extra client site if the snippet and payload stay the same.

## Likelihood
- High for the test. Risks, weighted:
  - Their snippet may post to their own backend, not to a URL we set. Then "connect a webhook" means configuring their backend's outbound webhook, or reading their API docs. Unverified until we see the snippet.
  - Field names unknown: the check node maps name/email/phone/message aliases; a nested payload (lead.contact.email) needs the map edited. Five-minute fix, but ask for a sample payload.
  - Staging site behind basic auth or on a builder (Wix, Webflow, WordPress with a security plugin) can block inline scripts. Ask which platform.
  - CORS: if the widget calls the webhook straight from the browser, n8n must allow the staging origin. Known fix, still the most likely "integration issue".
  - Required fields name, email, phone, message are our read of "lead/contact information", not theirs. Confirm.
- CRM unnamed. GoHighLevel on the canvas is inferred from their hiring history, not stated. Frame it as "shown in GoHighLevel, your CRM goes here if different" only if asked; the Calendar booking needs a preferred time from the chatbot, which it may not collect today.

## Standard pricing
- Test: market $150 to $300 for a scoped integration test with a written result. Post is $100 fixed, bids avg $98.56 ($50-$100). The $100 is below market but it is an audition for the onboarding work.
- Next phase: $600 to $1,500 per CRM + Calendar integration pattern, then a per-client-site rate. Recurring: n8n cloud from about 24 EUR a month or self-hosted, Google Workspace they already have, CRM on their plan.

## Ask before quoting
1. Can you share the snippet and one sample payload the chatbot sends?
2. Does the chatbot post leads to a URL we set, or through your own backend/API?
3. What platform is the staging site on, and is it behind a login?
4. Which fields must a lead have to count as captured?
5. For the next phase: which CRM, and does the chatbot ask for a preferred call time?
6. How many client sites do you expect to onboard?

## Flags
- No location restriction, no portfolio demand, no off-Upwork rule in the post.
- High-volume small-job hirer: deliver something visibly working plus a short written result; that is what wins the follow-on.
