# Private assessment — NOT for the proposal

**Job:** Cold Email Outreach Setup (infrastructure only) · hourly, rate not shown, avg bid ~$30/hr, US client, intermediate, part-time
**URL:** https://www.upwork.com/jobs/~022097751877937707326

## Time
8 to 12 hours of actual work, spread across 3 to 4 calendar weeks. The work itself is a
couple of sittings: domains and mailboxes day one, DNS day one or two, tool connection
day two. Then warmup is 2 to 3 weeks of waiting that nobody can compress, plus ~30 min
a week checking health scores and pulling weak inboxes. Final handover call and runbook
is another 1 to 2 hours. Bill the wait as light monitoring, not idle hours.

## Likelihood
Verified home turf — Lorenzo runs his own 100k+/month Instantly infrastructure, so every
step here is something he does for himself. The risk is not the skill, it is the client's
accounts:

- **Access is the overrun.** Everything must live on their billing, so he needs delegated
  admin on their registrar and their Google Workspace / Microsoft 365 tenant, plus their
  card on the sending tool. If they drip-feed access this stretches over days.
- **Google Workspace friction.** New tenants routinely hit identity verification and
  bulk-mailbox limits on the first day; DKIM can take hours to propagate. Budget one
  re-check cycle, which is exactly what the "All DNS Records Pass Verification?" gate is.
- **Tool tier gates inbox count.** Instantly and Smartlead price by inbox and by plan.
  How many mailboxes they can run is their subscription decision, not a build decision.
- **"Connect to Claude" is undefined in the post** and is the whole differentiator. Both
  Instantly and Smartlead have APIs he can wire to Claude for reply classification and
  drafting. If they mean something narrower or wider, scope shifts. Ask.
- **Warmup can fail on a domain.** A domain with bad history or a slow-propagating record
  can sit at a low health score; the fix is more time, not more work.

## Standard pricing
Market for cold email infrastructure setup at this size (3-5 domains, 10-15 inboxes,
full DNS, warmup, unified inbox) is **$1,000 to $2,500 flat**, or **$50 to $85/hr** from
someone who actually runs their own sending at volume. The post's ~$30/hr average bid is
below that band; it is the rate of a VA following a checklist, not of an operator. The
Claude connection is not in that range at all and should carry its own line.

Recurring software the client pays (not him): domains ~$12-15/yr each; Google Workspace
~$7/seat/mo or Microsoft 365 ~$6/seat/mo (a paid seat plus 2 aliases per domain is the
standard cost-saver, roughly a third the seat cost); sending tool ~$37-100/mo plus per-inbox
warmup fees. Put those numbers in front of them early — infra has a monthly floor and
clients who did not expect it stall at handover.

## Ask before quoting
1. How many inboxes, and what daily/weekly sending volume are you aiming for?
2. Instantly or Smartlead — do you have a preference or an existing account?
3. Google Workspace or Microsoft 365 for the mailboxes?
4. Who controls the registrar, and can I get delegated admin rather than your password?
5. What does "connect to Claude" mean to you — classifying and drafting replies, or
   something else?
