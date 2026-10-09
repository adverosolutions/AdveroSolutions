# Dossier - GoHighLevel & Pipedrive Setup Expert Needed

url: https://www.upwork.com/jobs/~022104544519995218927

## Who they are
- First name: unknown (no `client first name:` line, post is unsigned)
- Company: unknown
- Industry: unknown. A sales team running two CRMs side by side (GoHighLevel for lead follow-up, email/SMS; Pipedrive for sales pipelines and activities). No industry named.
- Location / timezone: United States (NJ), Eastern
- Website read: none named

## Client
no client intel

## Tools they named
GoHighLevel (GHL), Pipedrive, Zapier, Make, n8n, "APIs, webhooks", email/SMS. The build commits to n8n for the connection (named in their own list), GHL API v2 and Pipedrive API v2.

## Every number in the post
- "Fixed $10, intermediate" (metadata; budget placeholder, not the real scope)
- "3 hires, 43% hire rate, $80 spent, 5.0 feedback" (metadata)
- "1 invite, 1 interviewing, 0 hired" (metadata)
- To Apply list: 5 items (examples, migrations/integrations, tools, rate and availability, approach)
- No numbers about their business: no lead volume, no count of contacts or opportunities to migrate, no number of pipelines, stages, users or lead sources. All of these are their inputs.

## Their requirements, verbatim, in their order
1. "Set up and configure Pipedrive CRM"
2. "Set up GoHighLevel sub-account and CRM structure"
3. "Build and customize sales pipelines and stages"
4. "Configure custom fields, tags, and lead sources"
5. "Create automated lead follow-up workflows"
6. "Set up email/SMS automation where required"
7. "Configure lead assignment and routing"
8. "Connect GHL and Pipedrive using APIs, webhooks, Zapier, Make, or n8n"
9. "Migrate and organize existing contacts and opportunities"
10. "Set up pipeline movement and activity automation"
11. "Test all workflows and integrations"
12. "Provide documentation and basic training"
Plus from Requirements: "Strong attention to CRM data quality", "Ability to troubleshoot existing automations and integrations".

The canvas is the integration piece (the main session's direction): the parts of the post that live in the connection between the two CRMs, in their order.
- Section 1: part 4 plus "CRM data quality" (custom fields, tags, lead sources; clean record; dedupe by email).
- Section 2: part 7 (lead assignment and routing).
- Section 3: part 8 (connect GHL and Pipedrive).
- Section 4: part 10 (pipeline movement and activity automation), the Pipedrive-to-GHL direction of the stage sync.
- Section 5: error alert (after theirs; covers "troubleshoot").
Parts 1-3, 5, 6, 9, 11, 12 are account setup, migration, testing and docs: they go in the overview sticky (setup and need_from_you) and the assessment, not as canvas nodes. 4 of their parts on the canvas as 4 sections, plus the error section.

## The odd ask only they would recognize
"Connect GHL and Pipedrive using APIs, webhooks, Zapier, Make, or n8n" together with "Strong attention to CRM data quality": two CRMs holding the same leads is the thing that creates duplicates and stages that disagree. On screen: the dedupe step (search Pipedrive by email before creating anyone) and the two-way stage sync that ignores its own echo. Also "take ownership of the CRM setup from configuration through testing and launch".

## What their hiring history implies
3 hires, $80 spent, 43% hire rate, 5.0 feedback: a small-budget buyer who hires small fixed jobs and rates well. $10 fixed is a placeholder against a 12-item scope; they are likely shopping for an owner of the whole setup and will judge on whether the approach looks like someone who has done CRM architecture, not on a pitch. They asked for "a brief explanation of how you would approach this setup": the canvas is that explanation.

## Their likely data
A GHL opportunity webhook (sent from a GHL workflow's Webhook step, custom data added) for one new lead:

```json
{
  "contact_id": "k3Lq9XfA2bT7wPzR1mNe",
  "first_name": "  dana ",
  "last_name": "MORALES",
  "email": "Dana.Morales@Gmail.com ",
  "phone": "(732) 555-0148",
  "contact_source": "Facebook Lead Ad",
  "tags": ["new-lead"],
  "customData": {
    "event": "opportunity_stage_changed",
    "opportunity_id": "Yp2cR8sKd4LmQ0vHt6Wa",
    "opportunity_name": "Dana Morales - Facebook Lead Ad",
    "stage_name": "New Lead",
    "lead_value": "2500",
    "pipedrive_deal_id": ""
  }
}
```

Sample is illustrative. Stage names, lead source names and value are examples; their real ones are inputs.

## Sizing
Not a volume job. No numbers in the post. Inputs they supply: number of lead sources and which rep owns each, GHL pipeline stages and their Pipedrive equivalents, count of existing contacts and opportunities to migrate.

## Three things they would recognize on screen
1. Their two tools by name on every call: "GoHighLevel: ..." and "Pipedrive: ..." node labels, and the title "Your GHL and Pipedrive, Connected".
2. Their words as section labels: "CUSTOM FIELDS, TAGS AND LEAD SOURCES", "LEAD ASSIGNMENT AND ROUTING", "CONNECT GHL AND PIPEDRIVE", "PIPELINE MOVEMENT AND ACTIVITY AUTOMATION".
3. "CRM data quality": node 3 "Pipedrive: Search for This Person by Email Before Creating Anyone" and node 2's clean record (names, phone format), shown with the messy sample ("  dana ", "MORALES", "(732) 555-0148").

## Beat 1 draft
"This is your GHL and Pipedrive connected, one clean record in both."
