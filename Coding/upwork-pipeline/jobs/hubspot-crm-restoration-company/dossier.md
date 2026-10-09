# Dossier - HubSpot CRM Architect - Clean Setup for Multi-Location Restoration Company

url: https://www.upwork.com/jobs/~022104599336215815216

## Who they are
- First name: unknown
- Company: unknown
- Industry: "property restoration company (water, fire, mold, reconstruction)", referral-driven
- Location / timezone: United States (South Florida), two offices: Palm Beach and Treasure Coast (Eastern time)
- Website read: none named

## Client (from `client.json`; write "no client intel" when the file is missing)
no client intel

## Tools they named
HubSpot, Outlook, QuickBooks, RMS/Luxor ("job management runs in RMS/Luxor")

## Every number in the post
- "two offices in South Florida" (Palm Beach, Treasure Coast)
- Metadata: Hourly $20-$100, intermediate, part time; 9 invites; recorded bids avg $56.35
- No contact/company counts, user counts, job volume or HubSpot tier given (asked in assessment)

## Their requirements, verbatim, in their order
1. "Discovery session to understand how we win and track work"
2. "Design the data model: objects, associations, and parent/child company hierarchy (e.g., carrier -> regional office -> adjuster)"
3. "Custom properties with clear naming conventions and a property dictionary"
4. "Account Type / referral source classification that supports reporting"
5. "Deal pipeline(s) matched to our job lifecycle (lead -> inspection -> mitigation -> reconstruction -> closed)"
6. "Office/territory segmentation for two locations (Palm Beach, Treasure Coast)"
7. "Users, teams, and permissions"
8. "Data import plan and cleanup of existing contact/company exports (dedupe, standardize)"
9. "Core dashboards: referral source performance, pipeline by stage/office, BD activity"
10. "Integration recommendations for our stack (Outlook, QuickBooks; job management runs in RMS/Luxor)"
11. "Documentation and a recorded handoff/training session"

11 parts in the post, 11 screens in the prototype (plus an Overview), same order.

## The odd ask only they would recognize
"carrier -> regional office -> adjuster" hierarchy, and "not a generic SaaS sales funnel": the pipeline is their job lifecycle (lead -> inspection -> mitigation -> reconstruction -> closed), and referral credit has to roll up from the adjuster to the regional office to the carrier.

## What their hiring history implies
Client record not pulled. 9 invites and an architecture-first brief ("done right from day one, not patched later") suggest an owner or ops lead who has seen a messy CRM and wants a documented, defensible design, judged on clarity of the model and reporting, not on volume of automation.

## Their likely data
```json
{
  "deal": "Water loss - 2nd floor condo, Jupiter",
  "loss_type": "Water (Category 2)",
  "date_of_loss": "2026-09-14",
  "claim_number": "CM-44871-26",
  "stage": "Inspection scheduled",
  "office": "Palm Beach",
  "referral_source": "Adjuster referral",
  "referring_adjuster": "Dana Whitcomb (sample)",
  "regional_office": "Coastline Mutual - Southeast Region (sample)",
  "carrier": "Coastline Mutual (sample)",
  "est_mitigation": 8400
}
```

## Sizing
Not a sending/infrastructure job. Sizing inputs they have not given: number of users per office, contact and company export row counts, HubSpot tier (drives custom report builder, field-level permissions, custom objects). Carried as inputs.

## Three things they would recognize on screen
1. Carrier -> regional office -> adjuster hierarchy as the clickable data model (Data model screen).
2. Their lifecycle lead -> inspection -> mitigation -> reconstruction -> closed as the pipeline, with a referred water loss crediting adjuster and carrier (Pipeline screen, live moment).
3. Palm Beach / Treasure Coast segmentation by county, and RMS/Luxor named in integrations (Territories and Integrations screens).

## Beat 1 draft
"This is a working prototype of your HubSpot for restoration referrals."
