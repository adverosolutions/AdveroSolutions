# Assessment (private) - HubSpot & Shopify Integration Specialist: Custom Product Options, Automated Workflows & Reporting

The prop is a 10-module Make scenario: Shopify order webhook, one Admin GraphQL pull for line-item properties and metafields, deal search by Shopify order ID, contact upsert by email, deal create with its options, deal ID written back to the order, one HubSpot line item per product with its options and metafields. Their parts 4 to 7 (sequences, abandoned checkout, templates, dashboards) are HubSpot builds fed by those properties, named in the section notes, not modules.

## Time
Real hours, including test orders and a review round with them:
- The sync on their real option names and metafields: 12 to 16 h. HubSpot properties and the unique `shopify_order_id` (2 h), Shopify token and the two webhooks (1 h), mapping every option and metafield into steps 4a, 5 and 8 (4 to 6 h), edge-case test orders (4 h: multi-item orders, an order edit, a refund, no email, an engraving with a quote mark in it), handoff notes (1 h).
- Abandoned checkout: a second small scenario on Shopify's checkout webhook writing cart options and the checkout URL to the contact, plus the HubSpot workflow: 6 to 10 h.
- Post-purchase, upsell and re-engagement workflows with option-based branches: 10 to 16 h, more if Lorenzo writes the copy.
- Two or three branded drag-and-drop templates with option tokens and the product image: 6 to 10 h.
- Dashboards (revenue, CLV, workflow conversion, sales by option variation): 6 to 10 h.
- Backfill of past orders, if they want history in the dashboards (not asked): 4 to 8 h.

Total 40 to 62 h plus any backfill. Calendar: working sync on their store in week 1, everything in 4 to 5 weeks at retainer pace, gated mostly by their copy, brand assets and HubSpot access.

## Likelihood
- The sync: high. Every call is a documented endpoint and the logic is short. What breaks is their data and their accounts, not the design.
- Unverified for Lorenzo, check on day 1 with one test call each:
  - HubSpot contact upsert with `idProperty: email` on `/crm/v3/objects/contacts/batch/upsert`. If their portal refuses it, step 4a becomes a contact search plus create, which adds a router.
  - Unique-value custom property on Deals (`shopify_order_id`). HubSpot search can lag a few seconds behind a new deal, so the unique value, not the search, is what stops a second deal when orders/create and orders/updated arrive together. Sequential processing in Make narrows the window.
  - Shopify Admin API version 2026-07 and how they get an Admin API token (an existing custom app, or a new one through Shopify's developer dashboard). `customer.amountSpent` needs protected customer data access on that app.
  - HubSpot's newer native Shopify integration may sync orders to its Orders and Carts objects rather than Deals. Confirm what theirs does today; they asked for Deals and Line Items, so the build uses those.
  - Make expressions: `[1]` indexing, `map()`, `flatten()` and `formatDate()` are standard Make functions; test the exact mappings on the first real order.
- Data risks worth a test before live:
  - Raw JSON bodies break if a customer types a double quote or a line break into a personalization field. Test order 1 has one; the fix is escaping in the mapping or Make's Create JSON module.
  - Orders with no email (POS, some draft orders) fail step 4a. Decide: skip the contact and create the deal, or skip the order.
  - Make deactivates a scenario after repeated consecutive errors; incomplete executions plus error emails cover it.
  - If the native HubSpot app stays installed with deal sync on, orders can land twice (on the build, section 2 note, beat 4).
- HubSpot tier decides parts 4 to 7: workflows and the custom report builder need Professional; custom objects need Enterprise and are not needed here, since line items carry the option properties (section 4 note, beat 7).
- Lorenzo has not done a Shopify-options-to-HubSpot project. The honest frame: the core is built and shown working on the Loom; the HubSpot side (workflows, templates, dashboards) is standard configuration on top of those properties. [LORENZO] confirm he is comfortable owning HubSpot email template design, or scope templates as their designer's job with Lorenzo wiring the tokens.

## Standard pricing
- Market: HubSpot plus Shopify custom integration work runs $60 to $120 an hour on Upwork for someone who can show it working, $100 to $175 at a HubSpot partner agency. As fixed scope: the sync alone $2,500 to $4,500; sync plus abandoned checkout, three sequences, templates and dashboards $7,000 to $12,000.
- The post: $20 to $40 an hour, full time. At 160 hours that is $3,200 to $6,400 a month, below market for the "expert" level they list.
- Pitch a monthly retainer Lorenzo runs, not full-time hours. Reference points: build month $4,000 to $6,000 covering the sync, abandoned checkout, the three sequences, templates and dashboards; then $1,500 to $2,500 a month to own it (new products and options mapped, new sequences, report changes, watching failed runs). Lorenzo sets the actual bid.
- Recurring software (theirs): Make on a paid plan sized to their credits (see sizing in the dossier: about 7 credits per new order plus 1 per line item, 4 per orders/updated event); HubSpot at Professional or above for workflows and custom reports if they are not already there; their Shopify plan.

## Ask before quoting
- Monthly order volume and roughly how many orders/updated events per order (Make plan size).
- Which products use options, the full list of line-item property names and metafield keys, and which options app writes them.
- HubSpot hubs and tier (Marketing Hub Professional? Enterprise?), and whether the native HubSpot-Shopify app is installed now and what it syncs.
- Deals and Line Items as posted, or HubSpot's Orders object if their native app already uses it.
- The pipeline and stages Shopify orders should land in, and which status moves a deal.
- Do they want past orders backfilled for the CLV and option-variation reports?
- Who writes the email copy and supplies brand assets for the templates?
- Abandoned checkout timing: how long after the cart before the first email, and any discount.
- Can their Shopify developer (active since 2025-01) create the Admin API app, or does Lorenzo get staff access?

## Flags
- Full time, hourly $20 to $40: pitch the retainer above.
- "HubSpot Certified (Inbound Marketing / Workflows / Reporting preferred)": [LORENZO] which HubSpot certifications he holds, if any. Do not claim one otherwise.
- "Proven experience integrating Shopify with HubSpot for brands using advanced product options": he has none. Question 2 answers that honestly and points at the build.
- No US-only line, no portfolio-link demand, no rule against contact outside Upwork in the post.
- 21 connects; fresh post (0 invites, 0 interviewing).

## Their questions: draft answers for Lorenzo

**1. How do you recommend capturing Shopify line-item properties and sending them to HubSpot Line Items or Deals without using the native integration?**
Point Shopify's orders/create and orders/updated webhooks at a Make scenario, then make one Admin GraphQL call for each line item's properties and the product metafields, since the webhook doesn't carry metafields. The scenario searches HubSpot deals for the Shopify order ID, upserts the contact by email, creates the deal tied to that contact, and writes each line item with its options as custom line item properties associated to the deal. A unique-value shopify_order_id property on the deal backs up the search when two webhooks arrive at once.

**2. Briefly describe a past project where you integrated Shopify advanced product options or metafields with HubSpot.**
I haven't done a Shopify-options-to-HubSpot project before, so I built the core of yours for this application: the Make scenario in my video pulls line-item properties and metafields from a Shopify order and writes them to HubSpot Contacts, Deals and Line Items without duplicates. I build in Make daily. [LORENZO: add a Shopify or HubSpot project here only if you have a real one.]

**3. What is your preferred tool for this setup (e.g., Shopify Flow, Make/Zapier, or custom HubSpot Private App), and why?**
Make, calling HubSpot's CRM API with a private app token. This sync is a chain of calls that depend on each other (find the deal, upsert the contact, create the deal, loop the line items), and Make runs that chain with every run visible and replayable and no server for you to host. If order volume ever outgrows Make's pricing, the same HubSpot calls move into a custom private app.

## On the build and in a beat
- Native app double-sync risk: section 2 note, beat 4.
- Order ID search plus contact matched on email: nodes 3 and 4a, beat 3.
- Line items instead of custom objects for option reporting: section 4 note, beat 7.
- Abandoned checkout as the next add-on on Shopify's checkout webhook: section 3 note, beat 6.
