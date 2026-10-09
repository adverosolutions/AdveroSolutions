# Dossier - HubSpot CRM & Workflow Automation Needed for Real Estate Company

url: https://www.upwork.com/jobs/~022104659199702069541

## Who they are
- First name: unknown (no `client first name:` line, post is unsigned)
- Company: unknown
- Industry: "a growing real estate company" whose sales team speaks with "potential buyers and sellers"
- Location / timezone: United States (timezone unknown)
- Website read: none named

## Client
no client intel

## Tools they named
1. HubSpot ("We already have HubSpot set up")

## Every number in the post
- "Fixed $10" (budget, metadata; reads as a placeholder, not a real budget)
- No other numbers. Missing and obviously held by them: HubSpot tier and hubs, contact count, number of agents, lead volume per month, lead sources. These go under "Ask before quoting" and appear on the prototype only as sample data (labelled sample once) or as illustrative figures.

## Their requirements, verbatim, in their order
1. "help us clean up our CRM"
2. "automate our lead management process" / "improve how we capture, qualify, assign, and follow up with leads", split into:
   2a. "capture"
   2b. "qualify"
   2c. "assign"
   2d. "follow up with leads"
3. "so our sales team can spend more time speaking with potential buyers and sellers" / "reduce the amount of manual work our team has to do" (the outcome)

Six parts in the post (clean up, capture, qualify, assign, follow up, the outcome for the team). Seven scenes in the prototype: an Overview scene first, then one scene per part in the post's order: Clean up, Capture, Qualify, Assign, Follow up, Your team.

## The odd ask only they would recognize
"so our sales team can spend more time speaking with potential buyers and sellers". The outcome is agent time with buyers and sellers, not a dashboard. It is the final scene (the team's week shifting from manual work to conversations) and the last Play beat. Second detail: "HubSpot already set up", so the build works inside their existing portal, and clean-up comes first.

## What their hiring history implies
Client record not pulled. $10 fixed on an intermediate post means the budget field is a placeholder; they expect to discuss scope. A short, plain post from a growing company that already bought HubSpot and knows the four verbs (capture, qualify, assign, follow up): they want the process working, not a strategy deck.

## Their likely data
One buyer inquiry on a listing (sample, illustrative):

```json
{
  "contact": "Maya Chen",
  "phone": "(555) 014-7720",
  "email": "maya.chen@example.com",
  "lead_type": "Buyer",
  "source": "Website - listing page",
  "listing": "214 Linden Ave - 3 bd, 2 ba, 1,860 sq ft - $489,000",
  "created": "Mon 9:42 PM",
  "timeline": "Within 60 days",
  "pre_approved": "Yes - up to $520k",
  "home_to_sell": "No, renting",
  "areas": "Northside, Riverside",
  "lifecycle_stage": "Sales qualified lead",
  "lead_score": 86,
  "contact_owner": "Jordan Reyes (buyer's agent, Northside)",
  "deal_stage": "Showing scheduled - Sat 11:00 AM"
}
```

A seller record rides alongside: Tom Alvarez, home value request for 18 Birch Rd, routed to the listing agent.

## Sizing
Not a sizing job. No volumes in the post, so every count on screen is sample or illustrative.

## Three things they would recognize on screen
1. HubSpot named as the home of every record: the contact card, owner, lifecycle stage, deal stage (scenes 2 to 6), with no vendor UI imitation.
2. Their four verbs as the scene names in their order: Capture, Qualify, Assign, Follow up, after Clean up (the top tabs and presenter bar).
3. "buyers and sellers": a buyer (Maya) and a seller (Tom) both run through the system, and the final scene shows the team's hours moving to conversations with buyers and sellers.

## Beat 1 draft
"This is a working prototype of your HubSpot lead management process."
