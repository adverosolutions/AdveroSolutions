# Dossier - GoHighLevel Workflow Expert with Claude AI Integration

url: https://www.upwork.com/jobs/~022103174644722289052

## Who they are
- First name: unknown (no `client first name:` line, post unsigned)
- Company: unknown (the post names no company or site)
- Industry: "a design-build outdoor living company in Texas (patios, outdoor
  kitchens, pergolas)" that runs its "full lead engine" in GoHighLevel
- Location / timezone: Texas, US (Central time)
- Website read: none named

## Client (from `client.json`; write "no client intel" when the file is missing)
no client intel

## Tools they named
1. GoHighLevel (GHL), "our CRM", one sub-account
2. Zoom or Google Meet (for the call)
3. Claude, "connected to our GHL sub-account through the API/MCP connector. It
   can read and write contacts, tags and opportunities."
4. GHL native pieces: "webhooks, custom actions, AI steps"
5. In the requirements: "the API, MCP, webhooks, Zapier/Make or n8n"
6. Buildertrend ("a plus")

## Every number in the post
- "paid 60 minute consultation" (the whole engagement)
- "~2,400 contacts" ("cleaned contact data")
- "sales, careers and reactivation pipelines" (3 pipelines, counted from the
  names)
- "discovery and in-home consult calendars" (2 calendars)
- "an intake/lead-routing workflow" (1)
- "8 follow-up workflows (speed-to-lead, consult reminders, proposal chase,
  nurture, reactivation, reviews and referrals)": 8 workflows, but only 7 names
  (6 if "reviews and referrals" is one workflow). Which one is unnamed is a
  question for the client.
- 4 asks under "What we want from the consultation"
- 3 screening questions
- Metadata: Hourly $15-$35, intermediate, part time; 33 contracts, 31 jobs with
  hires, 18 active, $115,677.99 spent, 5.0 over 14 reviews, 3,148.83 hours;
  active "Construction Company Claude AI Setup" since 2026-07-06; bids avg
  $26.74, range $10-$89.76; 0 invites, 0 interviewing, 0 hired; 22 connects.

## Their requirements, verbatim, in their order
1. "Workflow review: check our triggers, branching, timing and routing logic,
   and whether anything overlaps or collides with our older workflows."
2. "Claude strategy: which tasks Claude should handle through the API and which
   should run natively in GHL (webhooks, custom actions, AI steps). We also want
   to use Claude to monitor, audit and maintain the system over time."
3. "Testing and reporting: how to catch silent failures, such as empty merge
   fields or leads that never enter a workflow."
4. "Next steps: a prioritized list of improvements to make."

4 parts in your post, 4 sections on the chart. Each band also carries its
share of the 60 minutes (Sizing).

Hiring requirements (not sections): "Proven hands-on experience building
GoHighLevel workflows. Please share examples or screenshots." / "Practical
experience connecting GHL with Claude or other LLMs through the API, MCP,
webhooks, Zapier/Make or n8n." / "Clear communication in English." /
"Experience with Buildertrend is a plus."

## The odd ask only they would recognize
"whether anything overlaps or collides with our older workflows": they rebuilt
the lead engine next to workflows that still exist. On screen as gate 3
("Collides With One of Your Older Workflows?") and named in a beat. Second
detail they would recognize: Claude is already live on their sub-account and
they want it to "monitor, audit and maintain the system over time".

## What their hiring history implies
A steady, well-rated hirer (33 contracts, $115,677.99, 3,148.83 hours, 5.0 over
14 reviews) running a construction business through Upwork freelancers: a VA, a
draftsman, cost codes and take-offs, app review. They pay low hourly rates
($15-$35 here) and buy practical work. The active "Construction Company Claude
AI Setup" contract (since 2026-07-06) is very likely who connected Claude to
GHL, so this call is a second opinion on work already done: review it
respectfully, no knocking the current build. They built the engine already and
want a checklist and priorities from someone who has done it, not a pitch. The
real prize is follow-on implementation hours.

## Their likely data
One GHL contact the way their intake would create it, showing both silent
failures they name (blank merge field, no workflow entered). Illustrative.

```json
{
  "contact": {
    "firstName": "",
    "lastName": "Whitaker",
    "phone": "+1 512-555-0187",
    "email": "rwhitaker.atx@gmail.com",
    "city": "Round Rock",
    "state": "TX",
    "source": "Website form - Outdoor Kitchen"
  },
  "customFields": {
    "project_type": "Outdoor kitchen + pergola",
    "property_type": "Single family, existing concrete patio"
  },
  "tags": ["new-lead", "outdoor-kitchen"],
  "opportunity": {"pipeline": "Sales", "stage": "New Lead"},
  "calendar": {"discovery_call": null, "in_home_consult": null},
  "created": "2026-09-22 18:41 CT"
}
```

## Sizing (setup / infrastructure / method jobs only)
- The call: 60 minutes over 4 asks. Workflow review is the biggest ask (every
  workflow), so: workflow review 20, Claude strategy 15, testing and reporting
  15, next steps 10 (20 + 15 + 15 + 10 = 60).
- Workflow review load: 1 intake/lead-routing + 8 follow-ups = 9 workflows,
  plus the older ones (count unknown, their input). 20 minutes / 9 = about 2
  minutes per workflow. The call can only cover triggers, collisions and
  routing; step-by-step reading has to happen before the call (their access or
  screenshots) or it does not happen.
- Claude as auditor: by their own description the connector "can read and
  write contacts, tags and opportunities". It cannot see a workflow's steps or
  who is enrolled. So enrollment has to leave a mark Claude can read: each of
  the 9 workflows adds an entry tag in its first step. A contact past intake
  with no entry tag is a lead that never entered a workflow. This is the
  sharpest insight: on the chart (step 6) and in a beat.
- ~2,400 contacts: a filtered pull (no entry tag, blank merge fields) finds the
  exceptions and Claude reads only those, not all ~2,400 every run (step 8).

## Three things they would recognize on screen
1. Their 9 workflows by name: band 1 note lists the intake/lead-routing
   workflow and the 8 follow-ups (speed-to-lead, consult reminders, proposal
   chase, nurture, reactivation, reviews and referrals); step 4 names the
   discovery and in-home consult calendars.
2. "Older workflows": gate 3, "Collides With One of Your Older Workflows?".
3. ~2,400 contacts and their 3 pipelines: step 8 ("Filter ~2,400 Contacts...")
   and step 9 ("Stuck in Sales, Careers, Reactivation").

## Beat 1 draft
"This is your GHL and Claude review for your outdoor living company."
