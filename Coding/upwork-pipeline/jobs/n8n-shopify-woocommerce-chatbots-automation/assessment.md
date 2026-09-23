# Assessment (private, never in the proposal)

Job: n8n and Shopify/WooCommerce chatbots and automation tasks. $30 fixed, "long-term". No store or platform named.

Prop: n8n canvas, 15 flow nodes plus the Config node. The chatbot handles order status, product questions and a person taking over. One Config value (`store_platform`) plus the switch "3 - Your Store: Shopify or WooCommerce?" pick between a Shopify Admin GraphQL lookup and a WooCommerce REST lookup. A code step turns either result into the same shape and only describes an order when the email matches. After that: a late-order flag (their "automation task"), a Google Sheets chat log, a Gmail handoff with reply-to set to the shopper, and an error path.

## Time
- One platform, to production:
  - chat trigger, sorting, store lookup, normalizer, reply and response: 8-10 h
  - late flag, chat log, handoff and error path: 3-4 h
  - embedding the chat widget in their theme: 1-2 h
  - testing against real orders and tuning the prompts: 3-4 h
  - **Total: 15-20 h.**
- Both platforms live: add 4-6 h (a second auth setup, order-number quirks, the tracking plugin on WooCommerce).
- Calendar: 1.5 to 2 weeks. Most of that is waiting on store access and a real test order, not build time.
- Ongoing work once it is live: realistically 5-15 h a month (tuning from the chat log, the next automation tasks, fixes).

## Likelihood
The core is likely to work because both lookups use the official Shopify and WooCommerce APIs. What breaks, weighted to their accounts:
- **Shopify app access (unverified this session).**
  - The app needs `read_orders` and `read_products`.
  - By default an app sees only the last 60 days of orders. Older orders need `read_all_orders`. This is on node 4a's note.
  - The order `email` field is protected customer data. Apps made through Shopify's Dev Dashboard or Partner route have to request that access. Check at setup whether a store-owned custom app needs approval in 2026, and whether custom apps can still be created in the admin.
  - Config sets `shopify_api_version` to `2026-07`, which follows Shopify's quarterly naming. Confirm the current stable version at setup.
- **WooCommerce.**
  - The REST API needs HTTPS and pretty permalinks.
  - Wordfence or Cloudflare rules often block `/wp-json`.
  - Sequential order-number plugins make the order number differ from the ID. The build searches and matches on `number`, which covers this.
  - Core WooCommerce has no tracking field. The build reads `_wc_shipment_tracking_items` (WooCommerce Shipment Tracking and Advanced Shipment Tracking). Other plugins store it elsewhere.
- **Chat surface.** The prop embeds n8n's chat widget in their theme. If they already run Shopify Inbox, Tidio, Gorgias, WhatsApp or Instagram DMs, the trigger becomes that tool's webhook. "Improving workflows" may mean an existing bot, so ask.
- **Misroutes.** Claude will sometimes misclassify a message. The handoff and the chat log catch these, and each week's fixes come from the log.
- **Unverified for Lorenzo.** His facts list has no Shopify or WooCommerce production build. Frame it honestly: he builds in n8n daily and uses the Claude API daily, and the store side uses the official APIs. The demo is tested on a free Shopify development store and a local WooCommerce install before touching theirs. Make no claim of past store bots.
- **Budget.** This is the biggest risk. See pricing.

## Standard pricing
- **Market for this build** (one platform, order status and product answers, handoff, one automation, chat log, error path, in n8n): $900-$2,000 fixed. Both platforms: $1,200-$2,500.
- **Long-term work as a retainer:** $500-$1,200 a month for a block of 8-15 hours. That covers tuning from the chat log, new automation tasks and fixes, with a stated response time. This is roughly $50-$90/h for intermediate n8n work.
- **Recurring software (client pays):**
  - n8n Cloud Starter, about $20-$25 a month (verify the current tier). Each chat message is one execution, so volume sets the tier. Self-hosting on a $5-$10 VPS is the alternative.
  - Claude API: roughly a cent or two per chat at Sonnet-tier rates (verify current per-token pricing). Moving the sort step to Haiku cuts that.
  - The Shopify and WooCommerce APIs cost nothing. Gmail and Sheets are on their existing accounts.
- **Post rate vs market:** $30 is about 2-3% of the market price for this build. It buys one small scoped fix, not a chatbot. Their history ($38 across 8 hires, all last week) says $30 is a trial task. Recorded bids average $113.96 (range $15-$1,200).
- **Structure (reference; Lorenzo decides):**
  1. Treat the $30 as a small but real paid first milestone, for example: connect their store and return live order status for one test order in n8n.
  2. The full build as a fixed milestone.
  3. The monthly retainer for the "long-term opportunity".

## Ask before quoting
1. Shopify, WooCommerce or both? One store or several (the title says "Chatbots")? Store URL.
2. Where should the chat live: a site widget, Shopify Inbox, WhatsApp, Instagram, or an existing bot they want improved?
3. n8n Cloud or self-hosted? Do they already have workflows running?
4. Roughly how many chats and orders a month? This sets the n8n tier and the Claude cost. It is carried only as their input.
5. Their shipping promise in days (`ship_within_days` in Config). On WooCommerce, which tracking plugin?
6. Who takes handed-off chats, and in what: Gmail, a helpdesk, Slack?
7. Which automation tasks come next? This is the retainer scope.
8. Budget for the build and a monthly figure for ongoing work.

## Flags
- Very low budget: $30 fixed, $38 lifetime spend, a pattern of tiny gigs. Don't invest beyond the Loom until scope and budget are confirmed.
- No US-only line, no portfolio demand, no "no contact outside Upwork" line.
- Location is New York, but the timezone shows Etc/UTC.
- No store named. The sample chat (order #1047, linen pillow covers) is invented, and the overview sticky says so plainly.
- Design choice: the one store automation runs inside the chat flow (a late order gets flagged when a shopper asks about it), so the canvas reads left to right in the post's order. A standalone scheduled or webhook automation is natural first retainer work.
- Sharp points the client would value that are also on the build and in the beats:
  - The email must match before an order is described (node 5 note, beat 4).
  - The platform switch (node 3 note, beat 2).
  - The 60-day order window on Shopify (node 4a note).
