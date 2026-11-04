# Private scene map (deck rebuild, 2026-10-22 7:39 PM CT)
Story reused from tour/: brief "Complimentary engraving / Oval solitaire ring / Proposal season / Thu Nov 12 10 AM PT", products oval solitaire + pave band + diamond studs, copy A/B, banner "The Solitaire Edit", Klaviyo draft, segment "Bridal, engaged 90 days", 12 UTM links, approval.
1. workflow (n8n, post names n8n): brief in, Shopify pull, Claude copy, banner render, Klaviyo draft build. New fact: how brief becomes a draft. Evidence: active nodes + context states. ~40s
2. messages (workbench): drafted email A and B, SMS, social post, all drafts. New fact: what the copy actually says. ~35s
3. outcome (workbench): campaign waiting for approval, then approved and scheduled; checklist metrics. New fact: nothing sends until team approves. ~30s
Cover ~10s, close ~15s. About 2 minutes.
Surfaces: n8n workflow (legacy canvas, webhook + http_request only), workbench messages, workbench outcome. No Klaviyo/Shopify native screens.
