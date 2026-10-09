# Assessment (private, never in the proposal)

## Time
- The prototype's system for real (one Claude agent with 6 tools, 2 to 3 n8n workflows, audit log, monitoring view): 25 to 40 hours, 1.5 to 2 calendar weeks including their API access and a review round.
- A narrower first slice (agent + one n8n workflow on their real intake): 10 to 15 hours, about one week.

## Likelihood
- Unknown scope is the main risk. The post names no business, no system and no data; the real ask may be much smaller (configure an existing n8n flow) or much larger.
- Breaks usually come from their side: API keys and scopes, a CRM plan tier without API access, n8n self-hosted vs cloud (webhook URLs, credentials), and messy policy docs the agent has to cite.
- Unverified for Lorenzo: which CRM and business system they run, whether they host n8n, whether they already have a Claude Code project or want one from scratch.

## Standard pricing
- Market for a scoped Claude agent + n8n implementation: $1,500 to $4,000 for the first system; $500 to $1,500 a month for changes and monitoring.
- Recurring software (theirs): n8n cloud $24 to $60 a month or self-hosted server $10 to $20; Anthropic API usage, roughly cents per run, scales with volume.
- The post's $20 fixed is far below market. Treat it as a paid test or placeholder; the post itself says "potential for additional work".

## Ask before quoting
1. Which requests or tasks should the agent handle first, and roughly how many a week?
2. Which systems does it need to read and write (CRM, database, helpdesk, email)?
3. Is n8n already running (cloud or self-hosted), and do you have a Claude Code project yet?
4. Should the agent send on its own within rules, or always wait for approval?

## Flags
- Budget $20 fixed vs avg bid $133.52.
- Client record not pulled; no hiring history known.
- "legitimate, authorized systems ... platform and service terms" line: benign compliance wording, but confirm the systems are theirs before touching credentials.

## Pricing path (Lorenzo only)
- Value (assumption: the agent handles 30 requests a day at 6 minutes each for a person, about 3 hours a day, 750 hours a year at $30/hour): about $22,500 a year in time saved. Assumption, not from the post.
- Price range at 10 to 20%: $2,250 to $4,500.
- Land offer (milestone 1): one agent flow on their real intake with approve-first mode.
- Upsell: more tools and workflows, the weekly summary, monitoring and a monthly retainer for changes.
- Milestones:
  1. 30%, paid once the agent handles one request type end to end in approve-first mode on your data and you've signed off.
  2. 30%, paid once the CRM, business-system and n8n side-effect workflows are connected and delivered and you've signed off.
  3. 25%, paid once evals, audit log and monitoring are delivered and you've signed off.
  4. 15%, paid once the handover (CLAUDE.md, runbook, a recorded walkthrough) is delivered and you've signed off.
