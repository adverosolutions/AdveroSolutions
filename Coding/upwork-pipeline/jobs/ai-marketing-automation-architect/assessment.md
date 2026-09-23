# Private assessment, not for the proposal

**The post itself.** $50 fixed price for "design and implement an AI-driven marketing automation system" covering acquisition, nurture, retention, performance and scalability. The skill tags on it are Graphic Design / Illustrator, which have nothing to do with the text. Bid range is $50 low, $50.46 avg, $57.31 high, meaning nobody bidding is treating the number as real either. Read this as a low-quality or placeholder post: either a copy-paste template, a budget field left at the floor, or a client who has no idea what this scope costs. Worth one proposal with a real build attached because "ongoing project" is the only signal that matters here, but do not do work before a conversation.

**Time.** 20 to 30 hours for the build as specced, over 2 to 3 calendar weeks. Roughly: 4 hours on the segmentation agent and the parser contract, 6 to 8 on the three journey arms and the nurture loop with its cap, 4 on CRM field mapping, 3 on the metrics sheet and the Monday digest, and the rest on testing against their real list and fixing what the first live send exposes. Add 5+ hours if their contact data is messy, which it usually is.

**Likelihood.** The n8n side is routine for me. What overruns is everything in their account: CRM field and lifecycle-stage mapping, deliverability and sending domain setup, whether their email tool actually exposes opens and clicks over API (Gmail alone does not, so open/click tracking needs their ESP or a tracking layer), and consent/unsubscribe handling on a win-back list that has been quiet 30 days. The build in the video uses HubSpot and Gmail as stand-ins; if they run GoHighLevel, Klaviyo, ActiveCampaign or Mailchimp, the middle third of the build gets rewritten around that platform's API and that is a different estimate.

**Standard pricing.** $3,500 to $8,000 fixed for this scope built once and handed off, or $85 to $150/hr for the same work hourly. Ongoing management of the campaigns and copy runs $1,500 to $4,000/mo. Recurring software: n8n cloud $25 to $50/mo (or self-hosted), Anthropic API $30 to $150/mo depending on send volume, plus whatever their ESP and CRM already cost. The $50 on the post is off by roughly two orders of magnitude and it is fine to say so on a call in neutral terms.

**Ask before quoting anything.**
1. What CRM do you run today, and what email platform sends your campaigns? (This decides the whole middle of the build.)
2. How many contacts are on the list, and how many new leads a month?
3. Is the $50 the real budget for this scope, or a placeholder on the post?
4. Do you have opens and clicks available over API today, or does that need building?
5. Who writes the campaign copy, you or me?
6. Ongoing means what here: build once and hand off, or manage it monthly?
