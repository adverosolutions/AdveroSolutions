# Assessment (private, Lorenzo only)

## Time
- Portal audit (properties, lifecycle stages, owners, pipelines, workflows already live): 3-4 h
- Clean-up: dedupe rules and merge, owner and stage backfill, buyer/seller lead type property, phone and email normalisation: 6-12 h (row count decides)
- Capture: website and listing-page forms, open house sign-in form, portal inquiry emails parsed into contacts, call/text source: 5-8 h
- Qualify: qualifying properties, lead score, SMS or chat qualifier with Claude writing to HubSpot properties, lifecycle stage rules: 8-12 h
- Assign: rotation by area, lead type and open-lead count, 5-minute accept rule with reassignment, agent SMS alert: 4-6 h
- Follow up: instant text, call tasks, similar-listings email, stop-on-reply, deal pipeline stages: 5-8 h
- Dashboard (speed to lead, follow-up coverage, showings, stage movement): 2-3 h
- Testing on real sources + recorded handover: 4-5 h
- Total: 37-58 real hours, 2-4 calendar weeks including review rounds.

## Likelihood
- High for the HubSpot side if they are on Professional: workflows, lead rotation by rules, sequences and custom reports all need Pro-level hubs. Starter limits workflows and sequences heavily. Tier is unverified; ask first.
- AI SMS qualifier needs an SMS channel (HubSpot's own SMS add-on, or Twilio via n8n) and consent language on the forms. Unverified which they have.
- Listing portal inquiries usually arrive by email; parsing them is reliable but each portal's format needs a sample.
- Clean-up is the unknown: contact count and how messy owners and stages are. Merges are irreversible in HubSpot; export a backup first and agree the "which record wins" rule with them.
- Lorenzo's HubSpot facts to lean on: GHL and CRM setups often, AI agents on existing databases for numerous companies, the roofing routing and follow-up system.

## Standard pricing
- Market for a HubSpot clean-up plus capture/qualify/assign/follow-up automation at this scope: $3,500-8,000 one-time. The post's "$10 fixed" is a placeholder, not a budget; treat scope as open.
- Recurring software on their side: HubSpot seats at their tier; SMS (HubSpot SMS add-on or Twilio, roughly $20-60/month at small volume); n8n (self-hosted about $10-20/month) only if the qualifier runs outside HubSpot; Claude API a few dollars a month at small lead volume.

## Ask before quoting
- HubSpot tier for Marketing and Sales Hubs, and seat count?
- How many contacts, and roughly how many duplicates or ownerless records?
- Lead sources today (website, listing portals, open houses, calls, referrals) and monthly volume?
- How many agents, split into buyer's and listing agents, and do they work by area?
- Do they text leads today, and from which number or app?
- Current follow-up: who calls, how fast, and where it falls through?

## Flags
- Fixed $10 budget (placeholder); client record not pulled, so spend, hires and verification unknown. Flags only, not a reason to skip.
- US client; consent for automated texts (TCPA) must be on every capture form before the SMS qualifier goes live.

## Pricing path (Lorenzo only)
- Value per year (assumption: 6 agents each saving 4 hours a week of data entry and chasing, at $40/hour) = 6 x 4 x 52 x $40 = about $50,000 a year. Plus faster speed to lead on inquiries, not counted.
- Price range at 10-20% of value: $5,000-10,000; the market range above keeps a first quote around $4,500-6,500.
- Land offer (milestone 1): CRM audit and clean-up, backup first, so HubSpot is trustworthy before anything automates on it.
- Upsell after: AI qualifier on SMS and chat, then a monthly retainer for new sources, reporting and tuning.
- Milestones:
  1. 25%: paid once the audit, backup, dedupe and owner/stage/lead-type clean-up are delivered and you've signed off.
  2. 25%: paid once every lead source captures into HubSpot and the qualifying properties and score are delivered and you've signed off.
  3. 30%: paid once assignment rules, agent alerts and the follow-up sequences are delivered and you've signed off.
  4. 20%: paid once the dashboard, live test on real leads and the recorded handover are delivered and you've signed off.
