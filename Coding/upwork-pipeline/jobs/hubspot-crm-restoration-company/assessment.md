# Assessment (private, Lorenzo only)

## Time
- Discovery session + write-up: 3 h
- Data model, associations, parent/child hierarchy, association labels: 6-8 h
- Properties + dictionary (about 40-60 properties) with naming convention: 6-8 h
- Account Type / referral source taxonomy + validation rules: 3 h
- Job pipeline, stage requirements, automation for office assignment: 5-6 h
- Territories, teams, users, permission sets: 3-4 h
- Import plan + cleanup of exports (dedupe, standardize, map, test import, full import): 8-14 h depending on row counts and mess
- Three dashboards (about 12-15 reports): 6-8 h
- Integration recommendations + Outlook and QuickBooks connect: 4-5 h
- Documentation + recorded handoff: 5-6 h
- Total: 50-65 real hours, 3-5 calendar weeks at part time (review rounds included).

## Likelihood
- High for the architecture itself; it is standard HubSpot configuration.
- Tier drives several items and is unverified: custom report builder and custom association labels beyond the basics, field-level permissions and teams hierarchies lean on Pro/Enterprise; custom objects are Enterprise only. The prototype designs Jobs as Deals so it does not depend on custom objects.
- Parent/child company is available broadly; confirm on their tier.
- RMS/Luxor: Lorenzo has not verified whether it has an API or a native HubSpot integration. Frame as "recommendation after we see their access": native if it exists, else middleware (Zapier/Make/n8n), else scheduled CSV. Do not promise a live sync.
- Import cleanup is the unknown in hours; dirty adjuster data (same person at two carriers, personal vs carrier emails) is the main risk.

## Standard pricing
- Market for a HubSpot partner architecture + onboarding like this: $6,000-12,000 one-time. Post range $20-100/h, recorded bids avg $56.35; 55 h x $56 is about $3,100, below market.
- Recurring software: HubSpot Sales Hub seats on their side (tier decides); middleware for RMS/Luxor if needed, about $20-100/month.

## Ask before quoting
- HubSpot tier and number of seats (per office)?
- Row counts in the contact and company exports, and where they come from (Outlook, spreadsheets, RMS/Luxor)?
- Does RMS/Luxor have API access on their plan?
- Is reconstruction a separate contract from mitigation (one deal or two)?
- Who needs to see the other office's jobs?

## Flags
- US client (South Florida); copy asserts no location.
- Part-time hourly; scope is fixed-shaped, so milestones fit better.

## Pricing path
- Value (assumption): average referred job $12,000 (Lorenzo's assumption); better adjuster and property-manager follow-up recovers 3 extra jobs a year = $36,000; admin/reporting time saved 4 h/week x 52 x $35 = $7,280. About $43,000 a year.
- Price range: 10-20% = $4,300-8,600.
- Land offer (milestone 1): discovery session + data model + property dictionary.
- Upsell path: RMS/Luxor sync build, BD activity automation (adjuster touch cadences, sequences), monthly CRM admin retainer.
- Milestones:
  1. 25%, paid once the discovery summary, data model and property dictionary are delivered and you've signed off.
  2. 30%, paid once properties, account types, the job pipeline, territories, teams and permissions are built in your HubSpot and you've signed off.
  3. 30%, paid once the cleaned import and the three dashboards are delivered and you've signed off.
  4. 15%, paid once Outlook and QuickBooks are connected, the integration recommendations and documentation are delivered, the handoff is recorded and you've signed off.
