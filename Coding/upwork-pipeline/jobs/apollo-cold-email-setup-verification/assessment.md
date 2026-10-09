# Assessment (private, never shown to the client)

## Time
- Real work: 2 to 4 hours.
  - Campaign config review in Apollo (mailboxes, schedule, limits, stop rules, tracking, opt-out): 30 to 45 min.
  - Email flow review and rewrite of every step, variables and fallbacks: 60 to 90 min.
  - DNS check per sending domain (SPF, DKIM, DMARC, MX), mailbox connection and warm-up status: 30 min, plus waiting time if a record has to be added by whoever holds the DNS login.
  - List/email verification pass and test sends to seed inboxes (Gmail, Outlook, Yahoo), link and unsubscribe check: 30 to 45 min.
- Calendar: 1 to 2 days. DNS changes and a list verification export can add a day if they depend on the client.

## Likelihood
High that it can be done; the risk is access and what is already in place.
- Unverified: how many mailboxes and domains they have, whether the domains are separate from their main domain, whether mailboxes are warmed, which Apollo plan they are on (sending limits and verification credits depend on it), list size and where it came from.
- DNS fixes need someone with registrar access. If they cannot give it, Lorenzo writes the exact records and they paste them.
- Apollo's own email status (verified / guessed / unavailable) is not a full verification. A second pass (MillionVerifier or similar) may cost credits they have not planned for.
- If they are sending from their main domain or from brand-new unwarmed mailboxes, "ready to launch" is honestly "not yet"; that is a finding, not a failure, but it needs saying early.

## Standard pricing
- Market for an expert pre-launch audit and setup of one Apollo sequence: $150 to $400 fixed. Full infra setup (domains, mailboxes, warm-up) is a separate $500 to $1,500 job plus mailbox software.
- The post's $20 fixed is far below market (roughly one tenth of the low end). Treat it as a land offer at best.
- Recurring software on their side: Apollo plan; optional verification credits; mailboxes if they need more.

## Ask before quoting
1. How many mailboxes and sending domains, and are they separate from your main domain?
2. Are the mailboxes warmed, and for how long?
3. List size, and was it pulled from Apollo or imported?
4. How many steps are in the sequence now, and is copy written?
5. Who has DNS access for the sending domains?
6. Target launch date.

## Flags
- $20 fixed, 1 invite, client record not pulled: price-sensitive or testing the market. Not a reason to skip.
- Short-term, scoped: good first contract to move into ongoing campaign management.

## Pricing path (Lorenzo only)
- Value per year: assumption, not in the post. If the campaign books even 2 extra meetings a month and one deal a quarter is worth ~$5,000, a correctly set up campaign vs a burned domain is worth ~$20,000 a year.
- Price range at 10 to 20% of value: $2,000 to $4,000 for a full managed setup; this post's scope (audit and verify) sits at $150 to $400.
- Land offer (milestone 1): do the verification pass for their budget-ish figure, deliver the fix list.
- Upsell path: rewrite the full sequence, add domains/mailboxes and warm-up, then monthly campaign management with reply handling and weekly numbers.
- Milestones (if they take the full audit):
  1. 30%: paid once the config and DNS audit with fix list is delivered and you've signed off.
  2. 35%: paid once the rewritten email flow (all steps, variables, fallbacks) is delivered and you've signed off.
  3. 35%: paid once list verification, test sends and the launch checklist are delivered and you've signed off.
