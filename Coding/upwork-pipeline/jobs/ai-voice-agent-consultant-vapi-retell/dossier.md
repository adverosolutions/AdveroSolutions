# Dossier - AI Voice Agent Consultant | Conversational AI | n8n | Twilio | Claude Code

url: https://www.upwork.com/jobs/~022104600558041437519

## Who they are
- First name: unknown (no `client first name:` line, post is unsigned)
- Company: unknown
- Industry: a business (or agency) that wants "AI voice agents and conversational AI systems for legitimate business workflows"; the post names no vertical. The prototype uses a generic sample home services company (plumbing, heating, electrical), labelled as sample.
- Location / timezone: Australia (metadata only; not used on screen)
- Website read: none named

## Client (from `client.json`; write "no client intel" when the file is missing)
no client intel

## Tools they named
Vapi, Retell, Twilio, OpenAI, Claude, n8n, APIs, CRM integrations, Calendar, SMS, Claude Code.
Not named, committed to: HubSpot for the CRM, Google Calendar for the calendar (most common), Twilio for SMS (already named for numbers).

## Every number in the post
- "Fixed $15, intermediate" (metadata; budget is a placeholder, not a scope)
- Recorded bids avg $82.61 (metadata)
- No business numbers (call volume, lines, hours, CRM size) in the post.

## Their requirements, verbatim, in their order
1. "AI Voice Agents & AI Receptionists"
2. "Inbound & Outbound Calling Systems"
3. "Lead Qualification & Lead Follow-up"
4. "Appointment Scheduling Agents"
5. "Customer Support Voice Agents"
6. "AI Sales & Calling Assistants"
7. "Twilio, Vapi & Retell Integrations"
8. "CRM, Calendar & SMS Integrations"
9. "Voice Agent -> CRM -> Follow-up Automation"
10. "Custom AI Workflows with n8n"
11. "AI Agent Development with Claude Code"
Plus the framing line: "a complete conversational workflow that connects calls with business systems and automates appropriate next steps."

11 parts in the post, grouped into 5 working screens plus Overview:
- AI Receptionist (live inbound call): parts 1, 2 (inbound), 3 (qualification), 4, 5, 9
- Outbound Follow-up: parts 2 (outbound), 3 (follow-up), 6
- Agent Setup: parts 1, 5 (voice, prompts, guardrails, knowledge)
- Integrations: parts 7, 8, 10, 11
- Call Analytics (illustrative)

## The odd ask only they would recognize
"legitimate business workflows" and "appropriate follow-up" / "appropriate next steps": they care that the agent stays inside lines. On screen: the agent says it is an AI in its first sentence, never quotes a price or gives safety advice, hands off to a person mid-call, outbound only calls people who enquired, inside calling hours, and honours an opt-out on the spot.

## What their hiring history implies
Client record not pulled. The $15 fixed budget against an $82 bid average says the number is a placeholder; the post reads like a scoping post for an ongoing consultant. They will judge on whether the whole loop (call -> systems -> next step) is thought through, not on a voice demo.

## Their likely data
```json
{
  "call_id": "call_7f3a91",
  "direction": "inbound",
  "caller": "Megan Doyle",
  "phone": "(555) 014-2290",
  "intent": "new job",
  "job": "Gas water heater, no hot water, no leak",
  "address": "14 Alder Street, Brookfield",
  "occupancy": "renter, landlord approval needed",
  "booked": "Sat 9:30 AM",
  "handoff": "pricing question, warm transfer to office",
  "duration_s": 118
}
```

## Sizing
Not a setup job; no numbers to size. Call volume, number of lines and after-hours cover go under "Ask before quoting".

## Three things they would recognize on screen
1. The full loop they wrote, "Voice Agent -> CRM -> Follow-up Automation", as the right-hand rail of the live call (CRM record, SMS, n8n run).
2. "Appropriate next steps": the handoff-to-human moment and the guardrails list on Agent Setup, and outbound rules on Outbound Follow-up.
3. Their named stack, Twilio, Vapi, Retell, OpenAI, Claude, n8n, Claude Code, on the Integrations map, with Vapi or Retell as a swappable runtime.

## Beat 1 draft
"This is a working prototype of your complete conversational workflow."
