# Dossier - n8n Automation Expert Needed for AI, API & Webhook Workflows

url: https://www.upwork.com/jobs/~022104561987790155342

## Who they are
- First name: unknown
- Company: unknown
- Industry: unknown ("my business"; the post names no business or vertical)
- Location / timezone: United States
- Website read: none named

## Client (from `client.json`; write "no client intel" when the file is missing)
No client intel. Client record not pulled.

## Tools they named
n8n, OpenAI ("OpenAI and other AI APIs"). No CRM, chat or sheet tool named, so the
prototype commits to the most common ones: HubSpot (CRM), Slack (team alerts),
Google Sheets (logs), Gmail (inbox), Anthropic Claude as the second AI API.

## Every number in the post
- "Fixed $30, entry level" (metadata)
- "2 invites" (metadata)
- "Recorded bids avg $31.54" (metadata)
No number about their business (volumes, lead counts, workflow counts). Every volume
on the prototype is sample data, labelled illustrative.

## Their requirements, verbatim, in their order
1. "Build custom n8n workflows"
2. "Integrate OpenAI and other AI APIs"
3. "Connect REST APIs and webhooks"
4. "Integrate different apps and services"
5. "Automate repetitive data processing tasks"
6. "Set up triggers, actions, filters, and conditions"
7. "Test and troubleshoot workflows"
8. "Fix and improve existing n8n workflows when needed"
Plus the closing line: "clean, reliable, and easy-to-manage workflows rather than just
basic automations."
8 parts in the post, 8 screens in the prototype in the same order, plus an Overview
(the live run) and a ninth screen for "clean and easy to manage".

## The odd ask only they would recognize
"clean, reliable, and easy-to-manage workflows rather than just basic automations".
On screen: its own screen (naming conventions, sticky-note docs, error workflow,
versioning) and the Overview's "why it's built this way" row.

## What their hiring history implies
Not pulled. $30 fixed, entry level, 2 invites, bids around $31: either a first small
paid task to test someone before bigger work, or a buyer who has not priced n8n work
yet. They will judge on whether it visibly works and whether they could manage it.

## Their likely data
Unknown business, so the sample is a neutral inbound lead from a website contact form
(the direction's "new lead" webhook). Illustrative:

```json
{
  "name": "Dana Whitfield",
  "email": "dana@whitfield-studio.example",
  "phone": "(512) 555-0148",
  "message": "Looking for help automating our quote follow-ups. Budget is approved and we'd like to start next month.",
  "source": "website-contact-form",
  "submitted_at": "2026-09-28T14:02:11Z"
}
```

## Sizing
Not a setup job; no numbers to size. Sharpest point for the build: reliability comes
from the unglamorous parts (retries on 429s, an AI fallback, an error workflow, a test
payload set), so those are shown working, not listed.

## Three things they would recognize on screen
1. Their eight asks, in their words and order, as the left rail (every screen).
2. OpenAI named on the AI step, with "other AI APIs" as a Claude fallback (Overview
   canvas, AI screen).
3. "Clean, reliable, easy-to-manage" as the Overview's why-row and its own screen.

## Beat 1 draft
"This is a working prototype of your clean, reliable n8n workflows."
