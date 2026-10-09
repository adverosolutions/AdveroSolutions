# Dossier - n8n Automation Developer - CRM & Lead-Gen / GTM Workflow Build

url: https://www.upwork.com/jobs/~022103123878708204191

## Who they are
- First name: unknown (no `client first name:` line, post is unsigned)
- Company: unknown
- Industry: unknown business. The post's own category is "CRM & Lead-Gen / GTM"; they run lead sources ("ad platform / forms / website") into Zoho CRM and want follow-up sequences and reporting by source.
- Location / timezone: Virginia, US (America/New_York)
- Website read: none named

## Client (from `client.json`; write "no client intel" when the file is missing)
no client intel

## Tools they named
In the post, verbatim, in order: n8n, "[ad platform / forms / website]", "[API]", "[Zoho CRM]", "(email/WhatsApp/SMS)".
Skills tags: n8n, CRM Automation, Marketing Automation, Lead Generation, API Integration, Workflow Automation, Automated Workflow, HubSpot, Email Automation, WhatsApp, Business Process Automation.

Zoho CRM is the only tool they committed to (the brackets read like a reusable scope template). The blanks, committed:
- Ad platform / forms / website: their website and ad landing-page forms posting to one n8n webhook, with hidden UTM fields, so Google Ads and Facebook ad traffic arrives already labelled by source. Why: one capture point covers all three bracket words, and the UTM tag is what makes their fifth line ("by source") possible. Meta instant forms are the next add-on (n8n has a Facebook Lead Ads trigger).
- Enrichment API: Apollo People Match (work email in, job title, company, website, location out). The most common enrichment API for GTM teams, and it answers by email alone.
- Follow-up channel: email first (Gmail), then SMS (Twilio) the next day. US client, so SMS over WhatsApp; WhatsApp is one switch on the same Twilio node, named as room to add next.
- Dashboard: a "Lead Dashboard" tab in Google Sheets, refreshed from Zoho every Monday.

## Every number in the post
The post body has no numbers. From the metadata:
- "$25" fixed price, listed (a placeholder: they ask for "Fixed price or hourly estimate")
- "expert" level
- 57 contracts, 56 jobs with hires, 8 active
- "$2,561.64 spent" (about $45 a contract across 57)
- "5.0 over 49 reviews"
- 0 invites, 0 interviewing, 0 hired
- bids avg "$107.89", range "$10-$1,020"
- 14 connects
- Five scope lines (the count of their requirements)

Missing numbers they obviously have: monthly lead volume, number of lead sources, touches in the sequence, Zoho edition. Those go in "Ask before quoting" and appear on the build only as their inputs.

## Their requirements, verbatim, in their order
1. "Capture leads from [ad platform / forms / website]"
2. "Enrich lead data via [API]"
3. "Route into [Zoho CRM] with proper field mapping and dedup logic"
4. "Trigger automated follow-up sequences (email/WhatsApp/SMS)"
5. "Basic reporting/dashboard on lead volume and conversion by source"

Five parts in your post, five sections on the canvas.

Their "Please share" list (answered by the Loom and the assessment, not sections):
- "Relevant n8n workflows you've built (screen recording or portfolio link preferred over description)"
- "Your proposed approach and rough timeline"
- "Fixed price or hourly estimate for the scope above"

## The odd ask only they would recognize
The brackets. Their scope is a template with blanks: "[ad platform / forms / website]", "[API]", even "[Zoho CRM]" in brackets. The build fills every blank with one named tool (UTM-tagged forms, Apollo, Gmail then Twilio, a Sheets dashboard) and the overview says so. Second: "screen recording ... preferred over description", which the Loom itself answers.

## What their hiring history implies
57 contracts for $2,561.64 total is about $45 a contract: a high-volume hirer of small fixed jobs (growth strategy, promo video, YouTube editor, logo, structural drawing, SEO audit), rated 5.0 over 49 reviews. They judge on seeing something work, not on a strategy deck, and they are price-aware: a market-rate quote for this scope will be far above anything they have paid before. The $25 is a placeholder, but the history says to show a working core and price in phases.

## Their likely data
One lead from a Facebook ad landing on their website form, and the dashboard row it ends up in (illustrative):

```json
{
  "body": {
    "first_name": "Alicia",
    "last_name": "Moreno",
    "email": "alicia.moreno@tidewaterfreight.com",
    "phone": "(757) 555-0184",
    "company": "Tidewater Freight Partners",
    "message": "Saw your ad on Facebook. Can we get a demo for our sales team next week?",
    "utm_source": "facebook",
    "utm_medium": "paid_social",
    "utm_campaign": "fall-demo-offer"
  }
}
```

Zoho lead created: First_Name Alicia, Last_Name Moreno, Company Tidewater Freight Partners, Designation "VP of Sales" (Apollo), Website tidewaterfreight.com (Apollo), Lead_Source "Facebook" (from utm_source), Description "Inquiry: Saw your ad on Facebook..." Dashboard row: source Facebook, leads in the last 30 days, converted, conversion rate.

## Sizing (setup / infrastructure / method jobs only)
Not a setup job. No volume in the post, so lead volume stays their input ("your lead volume per month") and drives only the Apollo credit plan, Zoho API credits and whether the report pull needs paging (Zoho returns 200 leads per page).

## Three things they would recognize on screen
1. Zoho CRM, their one committed tool, on every CRM step: "3 - Zoho CRM: Match by Email or Phone, Then Create or Update", the status check before the text, and the report pull. Their words "field mapping and dedup logic" are in section 3's label.
2. Their five scope lines as the five section bands, in their order, with their blanks filled by name (overview sticky: "Your post left three blanks").
3. "Lead volume and conversion by source": section 5 and the dashboard sample row (source, leads, converted, conversion rate), fed by the UTM tag captured in section 1.

## Beat 1 draft
"Hi, this is lead capture into Zoho CRM for your GTM team."
