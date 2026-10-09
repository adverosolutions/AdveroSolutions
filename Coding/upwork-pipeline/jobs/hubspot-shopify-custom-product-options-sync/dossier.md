# Dossier - HubSpot & Shopify Integration Specialist - Custom Product Options, Automated Workflows & Reporting

url: https://www.upwork.com/jobs/~022103201821592918024

## Who they are
- First name: unknown (no `client first name:` line, post is not signed)
- Company: unknown (no store name or domain in the post)
- Industry: a Shopify brand that sells products with "advanced product options in Shopify (line-item properties, metafields, and custom product configurations)". What they sell is not stated.
- Location / timezone: Colorado, US (Mountain Time)
- Website read: none named

## Client (from `client.json`; write "no client intel" when the file is missing)
no client intel

## Tools they named
In order of appearance: HubSpot, Shopify, the native HubSpot-Shopify integration app (named as not enough), Shopify Flow, Webhooks, Make/Zapier, a custom HubSpot Private App, HubSpot Deals, Line Items and Contact records, Shopify Metafields, Liquid/API payloads, HubSpot Custom Objects / Line Item APIs, Make, Zapier, serverless webhook/API implementations, HubSpot certifications (Inbound Marketing / Workflows / Reporting).

Build commits to: Shopify order webhooks into a Make scenario, the Shopify Admin GraphQL API for line-item properties and metafields, and HubSpot's CRM v3 API with a private app token (question 3 asks for the preferred tool; the canvas answers it).

## Every number in the post
The post body has no numbers about their business (no order volume, product count, option count, list size or dates). From the metadata paragraph:
- "Hourly $20-$40, expert, full time" (pitched as a retainer Lorenzo runs, not full-time hours)
- "5 contracts, 5 jobs with hires, 3 active"
- "$12,022.94 spent"
- "5.0 over 2 reviews"
- "9.83 hours"
- History: "Shopify Development" (hourly, 2024), "Shopify Developer Needed for Site Maintenance and Bug Fixes" (active since 2025-01), "Paid Search and Social Campaign Manager" (2025), "CRM PowerApp" (2021)
- Posted about 2026-09-24; "0 invites, 0 interviewing, 0 hired"
- "Recorded bids avg $36, range $13-$150"
- "Connects to apply: 21"
- 3 application questions

Missing numbers they obviously have: monthly order volume, orders/updated events per order, products using options, number of option fields and metafield keys, HubSpot tier. These go to "Ask before quoting" and appear on the build only as their inputs.

## Their requirements, verbatim, in their order
1. "Design and implement a sync solution (using Shopify Flow, Webhooks, Make/Zapier, or a custom HubSpot Private App) to bypass native integration limits."
2. "Map Shopify custom product options, line-item properties, and metafields to custom properties on HubSpot Deals/Line Items."
3. "Ensure clean data handling to prevent duplicate contact creation or corrupted deal pipelines."
4. "Build post-purchase, upsell, and re-engagement email sequences that dynamically pull custom product option choices into email tokens."
5. "Set up custom Abandoned Checkout / Cart sequences that reflect specific line-item options selected prior to checkout."
6. "Configure responsive, branded drag-and-drop HTML templates with dynamic personalization tokens (product previews, custom selections, order summary details)."
7. "Build custom dashboards in HubSpot tracking revenue, Customer Lifetime Value (CLV), workflow conversion rates, and sales performance by product option variations."

7 parts in the post, 4 sections on the canvas (past 5, adjacent parts grouped, each note names its grouping):
- Section 1, parts 1 and 2: the webhook and the Shopify pull that captures line-item properties and metafields for mapping.
- Section 2, part 3: order ID search, contact upsert by email, update arm for orders already synced.
- Section 3, parts 4 to 6: the deal with its options (deal tokens), the contact's last-order tokens and product image feed the sequences and templates; abandoned checkout is named as room to add next; the deal ID goes back to Shopify (their "bi-directional").
- Section 4, part 7: one line item per product with its option and metafield values, the fields the dashboards group by.
Parts 4 to 7 are built inside HubSpot (workflows, templates, dashboards), not as Make modules; the section notes name them as what the synced properties feed.

## The odd ask only they would recognize
"the native HubSpot-Shopify integration app will not suffice" for "line-item properties, metafields, and custom product configurations", and those choices must reach "email tokens" and "Abandoned Checkout / Cart sequences that reflect specific line-item options". On screen: section 1 label and node 2 ("Pull Line-Item Properties and Metafields"), the contact's last-order token fields in step 4a, section 3 note. Named in beats 2, 5 and 6.

## What their hiring history implies
$12k across 5 hires, 3 still active, 5.0 rating: a small, steady buyer who keeps people on. They already pay a Shopify developer for site maintenance (active since 2025-01), have run paid search and social, and had a custom CRM app built in 2021. They run a live store with real traffic and judge by whether things keep working in production ("test edge cases before deploying to a live production environment"). Full-time hourly at $20-$40 says they want ongoing ownership of HubSpot, not a one-off; a monthly retainer fits that without the hours.

## Their likely data
One Shopify order webhook (orders/create or orders/updated), flat payload as Make receives it. The product and its option names are illustrative (the post never says what they sell); their own option names replace them.

```json
{
  "id": 5550123456789,
  "admin_graphql_api_id": "gid://shopify/Order/5550123456789",
  "name": "#1042",
  "email": "jenna.alvarez@gmail.com",
  "created_at": "2026-09-24T10:14:32-06:00",
  "financial_status": "paid",
  "fulfillment_status": null,
  "total_price": "132.00",
  "customer": {"id": 7012345678901, "first_name": "Jenna", "last_name": "Alvarez"},
  "line_items": [
    {"title": "Custom Walnut Cutting Board", "variant_title": "Large", "sku": "CB-WAL-L", "quantity": 1, "price": "132.00",
     "properties": [
       {"name": "Engraving Text", "value": "The Alvarez Family - Est. 2019"},
       {"name": "Font", "value": "Serif"},
       {"name": "Gift Wrap", "value": "Yes"},
       {"name": "_Configuration ID", "value": "cfg_88213"}]}
  ]
}
```
Product metafields from the Shopify pull: `custom.material` = "Black walnut", `custom.lead_time` = "10 business days".

## Sizing (setup / infrastructure / method jobs only)
Not a setup job; Make credit use per order, from the scenario's own steps (no volume in the post, so volume stays their input):
- New order: webhook + Shopify pull + deal search + contact upsert + deal create + Shopify write-back + iterator = 7, plus 1 per line item.
- Order already synced (an orders/updated event): webhook + pull + search + deal update = 4.
- Monthly credits = your orders a month x (7 + line items per order) + your orders/updated events a month x 4. orders/updated fires on payment, fulfillment and edits, so update events can outnumber orders; the count is theirs to pull from Shopify.

## Three things they would recognize on screen
1. Their "native HubSpot-Shopify integration app will not suffice": section 1 note ("the native integration's limits never apply"), node 2 "Shopify: Pull Line-Item Properties and Metafields", beat 2.
2. Their "prevent duplicate contact creation or corrupted deal pipelines": section 2 label "NO DUPLICATE CONTACTS OR CORRUPTED DEALS", nodes 3 and 4a, beats 3 and 4.
3. Their "Deals, Line Items, and Contact records" plus "sales performance by product option variations": title, node 5 and node 8 ("Create Each Line Item With Its Options"), section 4 note, beat 7.

## Beat 1 draft
"This is custom product options syncing into HubSpot, for your Shopify store"
