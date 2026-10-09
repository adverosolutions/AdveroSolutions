# Assessment (private, never in the proposal)

## Time
- 1.5 to 3 hours real work: read the export (20 min), reproduce with a pinned execution (20 min), rewrite the mapping (30 to 45 min), validation node + retry + error branch (30 min), run the edge-case payloads (20 min), short note (10 min).
- Calendar: same day once the export and one failing execution are in hand.

## Likelihood
- High if the failure is what the post implies: a path mismatch (`body` vs `body.data`), item shape (`$input.first()` vs `$input.all()`, bare object return), type casting. These are the usual Code/Set node failures after a sender changes its payload.
- Unverified for Lorenzo: the downstream API's schema and auth. If the API rejects on something outside the mapping (auth, rate limits, a field the sender never sends), the fix grows. Also unknown whether they run n8n cloud or self-hosted (affects error workflow and env vars).
- Risk: they paste an export with credentials stripped; testing the POST needs either a sandbox endpoint or their go-ahead to hit production.

## Standard pricing
- Market for a scoped n8n debug: $60 to $150 fixed; experts bill $75 to $120 an hour for 1 to 3 hours. The post's $60 is at the floor; bids average $55.64.
- No recurring software.

## Ask before quoting
- The workflow export (JSON) and one failed execution's input (pinned data).
- The downstream API's docs or one request that is known to work.
- Cloud or self-hosted n8n, and version.
- Where alerts should go (Slack, email).

## Flags
- $60 fixed, expert: low value, fast close. Client record not pulled.

## Pricing path (Lorenzo only)
- Value per year: assumption, a broken intake webhook that silently drops records costs a few hours a week of manual re-entry; 3 h/week x 50 x $40 = $6,000/yr (assumption).
- 10 to 20% of value: $600 to $1,200. The post caps this one at $60; take it at $60 as the land offer.
- Land offer (milestone 1): the fix itself at the post's $60.
- Upsell after: monitoring and hardening on their other n8n workflows (error workflow shared across all, execution alerts, a test-payload suite per workflow), then a small monthly maintenance retainer.
- Milestones for the upsell (not this job): 1) audit of all workflows, 30%, paid once the audit is delivered and you've signed off; 2) shared error workflow + alerts, 30%, paid once it is delivered and you've signed off; 3) test suites per workflow, 25%, paid once they are delivered and you've signed off; 4) handover note, 15%, paid once it is delivered and you've signed off.
