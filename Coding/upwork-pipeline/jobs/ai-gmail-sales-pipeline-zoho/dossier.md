# Dossier - AI-Powered Gmail Automation for Sales Pipeline

url: https://www.upwork.com/jobs/~022104649178725478693

## Who they are
- First name: unknown (no `client first name:` line, post is unsigned)
- Company: unknown
- Industry: a sales team that runs its pipeline out of Gmail, "preferably Zoho CRM". What they sell is not stated.
- Location / timezone: United States (timezone not given)
- Website read: none named

## Client
no client intel

## Tools they named
Gmail, Google Workspace, Zoho CRM ("preferably"), OpenAI, Claude, "workflow automation platforms and/or APIs" (none named). Committed platform for the build: n8n (Lorenzo builds in it daily), with Claude as the model and OpenAI as the named alternative.

## Every number in the post
- "Hourly $10-$20" (metadata)
- "intermediate, part time" (metadata)
- "Recorded bids avg $22.60 (basis unspecified)" (metadata)
- Posted 2026-09-28
No lead volume, team size, email volume, deal size or stage count. Those go under "Ask before quoting". Any number on the prototype is sample data or labelled illustrative.

## Their requirements, verbatim, in their order
1. "Building AI-powered workflows around Gmail and our sales pipeline"
2. "Automating lead follow-ups and reminders"
3. "Using AI to analyze incoming and outgoing email communication"
4. "Identifying when a lead needs a response or follow-up"
5. "Helping determine appropriate next actions based on email conversations"
6. "Automating or assisting with personalized email responses"
7. "Organizing and categorizing leads based on communication"
8. "Reducing repetitive manual tasks"
9. "Creating a reliable workflow that can be maintained and expanded over time"
Application asks: "Please explain how you would prevent the AI from sending inappropriate or incorrect follow-ups." and "Any experience integrating Gmail with Zoho CRM or other CRMs."

9 parts in the post plus the guardrail question; 6 scenes in the film. Grouping:
- Scene 1 Overview: part 1 (and "how you would approach building an AI system around Gmail and a sales pipeline").
- Scene 2 Inbox: parts 3 and 7 (reads incoming and outgoing mail, sorts every lead).
- Scene 3 Next action: parts 4 and 5.
- Scene 4 Guardrails: part 6 plus the guardrail question (draft in their voice, seven checks, pricing held for a person, follow-ups stopped).
- Scene 5 Zoho: part 2 plus the Zoho ask (stage moves, contact added, task, follow-up ladder that stops on reply).
- Scene 6 This week: parts 8 and 9 (run log, editable rules, illustrative week).

## The odd ask only they would recognize
"Please explain how you would prevent the AI from sending inappropriate or incorrect follow-ups." Plus "think beyond simple triggers and actions ... understand the context of sales conversations." On screen: scene 4's seven checks catch a draft that agreed to a 15% discount, remove the line and hold the email for a person; the same scene lists follow-ups the system refused to send (a lead who said no, an out-of-office, an unsubscribe). Named in beat 5.

## What their hiring history implies
Client record not pulled. $10-20/hr with "possible ongoing work" and "part time": a small team testing AI in sales, likely to judge on whether it looks safe to switch on and whether it can grow. The guardrail question says they have seen or fear an AI emailing a lead something wrong.

## Their likely data
One Gmail thread with a lead, one Zoho deal. Sample only (their product is unknown, so the sample stays product-neutral: quote, terms, a call).

```json
{
  "thread": "Re: Revised quote",
  "from": "Priya Shah <priya.shah@corvane.co>",
  "received": "Mon Sep 28, 8:02 AM",
  "body": "Could you send the revised quote before our review on Thursday? I'm looping in Dan Okafor, our CFO. Is 15% possible if we sign this month?",
  "zoho_deal": {"Deal_Name": "Corvane Logistics - 2026 contract", "Stage": "Proposal", "Amount": 48000, "Owner": "Alex", "Contact_Roles": ["Priya Shah"]},
  "agent_output": {"intent": "revised quote + meeting", "deadline": "Thu Oct 1", "new_contact": "Dan Okafor, CFO", "pricing_request": "15%", "next_stage": "Negotiation", "send_mode": "hold for approval"}
}
```

## Sizing
Not a setup job with volumes. Nothing to size from the post.

## Three things they would recognize on screen
1. Gmail and Zoho CRM by name: the inbox in scene 2, the Zoho deal record and pipeline in scene 5, the stack in scene 6.
2. Their guardrail question answered visibly: scene 4 "Seven checks on every email", the 15% promise struck out and held for a person, three follow-ups stopped.
3. "Identifying when a lead needs a response or follow-up": scene 2 sorts seven threads into Reply needed / Follow-up due / Waiting on them / No action, and scene 5 stops Ben's follow-ups when he replies.

## Beat 1 draft
"This is a working prototype of your AI-powered Gmail sales pipeline."
