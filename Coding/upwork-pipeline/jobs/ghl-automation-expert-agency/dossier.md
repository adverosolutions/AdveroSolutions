# Dossier - GoHighLevel Automation Expert Needed for Agency

url: https://www.upwork.com/jobs/~022102811395586794410

## Who they are
- First name: unknown (no `client first name:` line, post is unsigned)
- Company: unknown. Feedflare.co.uk appears in their hiring history, not in the
  post; the main session says not to assume it is the agency posting. Not used.
- Industry: "our agency", with "our clients" (post). The hiring history reads
  like a marketing / AI agency: social media manager, motion graphics and video
  editor "for our agency", Instagram and Facebook outreach "for AI Agency",
  "Seo and aio experts for agency".
- Location / timezone: client location not shown; timezone Africa/Casablanca.
- Website read: none named in the post (Feedflare.co.uk deliberately not fetched).

## Client (from `client.json`; write "no client intel" when the file is missing)
no client intel

## Tools they named
- "GoHighLevel (GHL)", then "GHL" twice. No other tool.
- Committed build tool: GoHighLevel workflows only (their tool), shown as a
  chart-only starting plan; nothing is built or imported anywhere yet. Inside GHL: a website form, the
  pipeline, SMS, email, If/Else, tasks, internal notifications, custom values.

## Every number in the post
- The post text has no numbers at all.
- Metadata (hiring context, not build facts): fixed price listed as "$5
  (placeholder)", expert level; 24 contracts, 17 jobs with hires, 15 active,
  "$44.9k spent", 4.46 over 5 reviews, 2,494 hours; 0 invites, 0 interviewing,
  0 hired; recorded bids avg $52.19, range $5-$750 (basis unspecified);
  8 connects.
- Missing numbers they obviously have (asked in assessment.md, never stated):
  number of client sub-accounts, leads per month per client, team size, GHL
  plan / SaaS mode, which processes they run by hand today.

## Their requirements, verbatim, in their order
1. "help automate processes within our agency and for our clients"
2. "uncover the full potential of GHL's automation capabilities"
3. "developing strategies that enhance workflow efficiency and improve client
   satisfaction"
4. "guide our team in implementing best practices"

4 parts in your post, 4 sections on the canvas. The post names no specific
automation, so the build is an honest starting example: one workflow that runs
both inside the agency and in every client sub-account (new lead follow-up),
and one that runs inside the agency (a client signs and is onboarded).
- Section 1 (part 1): a new lead, answered at once, same workflow for the
  agency's own enquiries and for each client's sub-account.
- Section 2 (part 2): the follow-up half of that workflow, the GHL features a
  team that "is knowledgeable" still tends to skip: an If/Else reply check
  before every follow-up and pipeline stages that move themselves.
- Section 3 (part 3): a client signs; one tag fires the welcome, the team alert
  and the setup tasks (efficiency, client satisfaction).
- Section 4 (part 4): the practice the team copies: a day-3 check-in, a reply
  goes to the account manager, silence becomes a call task.

## The odd ask only they would recognize
"Our team is knowledgeable, but we need your expertise to uncover the full
potential of GHL's automation capabilities" together with "within our agency
and for our clients". They do not want GHL basics explained; they want the
patterns a knowledgeable team misses, usable in their own account and in
clients' accounts. On screen: section 1 label names both places, section 2 is
titled as the features teams skip, the custom-value note shows how one workflow
ships to every client.

## What their hiring history implies
A steady, high-volume hirer ($44.9k, 24 contracts, 15 active right now) who
runs a team of specialists (social, video, outreach, SEO, a product manager, a
full stack developer). They hire roles, long-term. The $5 is a placeholder, so
they expect the proposal to set the scope and price. They will judge on whether
this person can slot in as the GHL specialist on a team that already knows the
tool: show patterns and judgment, not a tour of the builder. Timezone
Africa/Casablanca: working-hours overlap matters for "guide our team".

## Their likely data
A lead for the agency (or for one of its clients) coming in from a website
form, who later becomes a client. Illustrative only:

```json
{
  "form": "Website Enquiry",
  "contact": {
    "first_name": "Hannah",
    "last_name": "Reyes",
    "company_name": "Reyes Dental Studio",
    "email": "hannah@reyesdentalstudio.com",
    "phone": "+44 7700 900318",
    "website": "reyesdentalstudio.com",
    "message": "Looking for help with Instagram content and local SEO for our clinic."
  },
  "pipeline": "Your Agency - New Leads",
  "stage": "New Lead"
}
```

## Sizing (setup / infrastructure / method jobs only)
Not a setup job, and the post gives no numbers. Carried as their inputs, never
stated: how many client sub-accounts, leads per month per client, which form
starts the lead workflow in each client account, their booking, onboarding-form
and kickoff links (custom values). The sharp point that goes on screen instead
of a number: the lead workflow uses custom values for every link, so one
workflow loads into every client sub-account and only the values change.

## Three things they would recognize on screen
1. Their words "within your agency and for your clients": the title and the
   section 1 label and note.
2. "The full potential of GHL's automation": the section 2 label (features
   teams skip), with the If/Else reply checks and the auto stage moves under it.
3. "Improve client satisfaction" and "guide our team in implementing best
   practices": section 3 and 4 labels, the new-client tag trigger, the day-3
   check-in and the call task on silence.

## Beat 1 draft
"This is automating processes within your agency and for your clients."
(first name unknown, business type: agency)
