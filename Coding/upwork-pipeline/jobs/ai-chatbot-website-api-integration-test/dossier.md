# Dossier - AI Chatbot Website & API Integration

url: https://www.upwork.com/jobs/~022103558387831786888

## Who they are
- First name: unknown
- Company: unknown
- Industry: a team that has built an AI chatbot and is rolling it out to its own clients' websites ("our client onboarding work")
- Location / timezone: Europe/Berlin timezone, country not shown
- Website read: none named

## Client
no client intel

## Tools they named
In the post: "AI chatbot" (already built, their own), "code snippet", "test/staging website", "API/webhook", "JavaScript", "CRM", "Google Calendar".
No CRM named. Commit to GoHighLevel for the next-phase CRM step: their history includes "GoHighLevel (GHL) CRM & Automation Expert Needed". Receiving side built in n8n (webhook), capture log in Google Sheets (a test sheet anyone on their side can open), Gmail for the missing-field flag.

## Every number in the post
- "Fixed $100" (budget), "a small paid test"
- Metadata: 193 contracts, 180 jobs with hires, 16 active, $13,633.25 spent, 4.86 over 150 reviews, 100% hire rate, 1 invite, bids avg $98.56 (range $50-$100), 14 connects.
- No lead volume, no number of client sites, no field count given. Required fields name, email, phone, message are our choice from "lead/contact information", shown as their check list, not stated as their spec.

## Their requirements, verbatim, in their order
1. "Add the chatbot to a test/staging website"
2. "Configure the provided code snippet"
3. "Test lead/contact information collection"
4. "Connect or test a simple API/webhook"
5. "Verify that chatbot data is being passed correctly"
6. "Troubleshoot any integration issues"
Next phase: "CRM and Google Calendar integrations" for "client onboarding work".

6 parts in the post. Grouped into 4 sections plus the next phase and one error section:
- section 1 = parts 1 and 2 (staging site and snippet: the snippet posts to the webhook)
- section 2 = part 3 (lead/contact collection check)
- section 3 = part 4 (the webhook: log every capture, answer the chatbot)
- section 4 = parts 5 and 6 (verify passed correctly, flag and troubleshoot what is missing)
- section 5 = the next phase they named: CRM + Google Calendar
- section 6 = if a run breaks (error alert)

## The odd ask only they would recognize
"The chatbot is already built" - they do not want a chatbot, they want proof its data lands. The canvas is the receiving end only, plus a test sheet that shows every capture with what was missing.

## What their hiring history implies
Very high-volume hirer of small fixed dev jobs (193 contracts, 100% hire rate, $13.6k spent, so mostly small tickets). Uses paid tests to pick people, then continues with the one who delivers. Judges on "it works and I can see it works", not strategy. Has hired a GoHighLevel expert before.

## Their likely data
One lead captured by the chatbot on the staging site:

```json
{
  "source": "staging-chatbot",
  "session_id": "cb_7f3a91e2",
  "page_url": "https://staging.PASTE-YOUR-STAGING-DOMAIN/contact",
  "name": "Julia Weber",
  "email": "julia.weber@weber-physio.de",
  "phone": "+49 151 2847 3310",
  "message": "Hi, we'd like the chatbot on our practice site. Can we talk Thursday afternoon?",
  "preferred_time": "2026-10-01T14:00:00+02:00",
  "captured_at": "2026-09-25T10:42:17+02:00"
}
```

## Sizing
Not a setup job. None.

## Three things they would recognize on screen
1. "Staging" and "your code snippet" in the first section label and the webhook node label (parts 1 and 2).
2. The four fields name, email, phone, message named in the check node and in the "Missing" column of the test sheet (parts 3 and 5).
3. The tail labelled as their next phase: CRM contact + Google Calendar booking (their "client onboarding work").

## Beat 1 draft
"This is proof your chatbot's leads land, for your client rollouts"
