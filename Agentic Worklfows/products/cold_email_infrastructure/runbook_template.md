# {CLIENT} cold-email infrastructure runbook

Filled in per client and handed over on day 5. This is the deliverable they keep. Replace every `{PLACEHOLDER}`. A runbook with a placeholder left in it is worse than none, because it reads as finished.

Prepared by Lorenzo, {DATE}.

## 1. What you have

| | |
| --- | --- |
| Sending domains | {DOMAIN_LIST} |
| Inboxes | {INBOX_COUNT} ({PERSONAS} on each domain) |
| Daily ceiling per inbox | 25 |
| Total daily ceiling | {TOTAL_PER_DAY} |
| Sending platform | {PLATFORM}, account {ACCOUNT} |
| Registrar | {REGISTRAR} |
| Warm-up started | {WARMUP_START} |
| **Safe to send real volume from** | **{GO_LIVE_DATE}** |

Everything above is in your name, on your card, in your account.

## 2. DNS records, per domain

Repeat this block per domain. Verified externally on {VERIFY_DATE}.

| Record | Host | Value | Verified |
| --- | --- | --- | --- |
| SPF | `@` | `{SPF}` | yes |
| DKIM | `{DKIM_SELECTOR}._domainkey` | `{DKIM}` | yes |
| DMARC | `_dmarc` | `v=DMARC1; p=none; rua=mailto:{DMARC_INBOX}` | yes |
| MX | `@` | `{MX}` | yes |

DMARC is at `p=none` on purpose. It reports without rejecting, so a misconfiguration shows up as a report instead of as lost mail. Tighten it to `quarantine` after {DMARC_REVIEW_DATE}, once the reports are clean.

## 3. Inboxes

| Address | Persona | Daily limit | Warm-up | Health |
| --- | --- | --- | --- | --- |
| {ADDRESS} | {NAME} | 25 | on | {HEALTH} |

Signature on every inbox: {SIGNATURE}.

## 4. Settings and why

| Setting | Value | Why |
| --- | --- | --- |
| Open tracking | off | The pixel is a spam signal and the number it gives you is wrong anyway |
| Link tracking | off | A rewritten link on a new domain is the single clearest spam signal there is |
| Text only | on | HTML mail from a new domain to a stranger is unusual. Plain text is what a person sends |
| Stop on reply | on | Never chase someone who answered |
| Sending window | {WINDOW} {TZ} | |
| Per-inbox daily limit | 25 | Ceiling, not target |

## 5. Weekly checks, ten minutes

1. Warm-up health, every inbox. Below 98 percent, pause that inbox and tell {OWNER}.
2. Bounce rate. Above 2 percent for a week, take the inbox out and find out why before putting it back.
3. Reply rate per domain. A domain that falls to less than half its own four-week average has a problem, not a bad week.
4. Spam complaints. Any at all, stop and read the last week of sends.

## 6. When something breaks

| Symptom | First thing to check | Then |
| --- | --- | --- |
| Bounces jumped | The list, not the domain. A bad import is the usual cause | Pause the campaign, verify the list, resume |
| Replies dropped by half | Warm-up health and placement | Pause the worst inbox, test placement, do not change the copy first |
| An inbox is locked out | The provider's admin console | Pause it in the platform, or it keeps trying and makes it worse |
| Somebody complained | The address and the send that caused it | Add them to the blocklist the same day, then look for others from the same import |
| A domain stops authenticating | The registrar. A record was changed | Section 2 has every original value |

## 7. Who to call

{OWNER} owns this day to day. Lorenzo is at {CONTACT} for anything in section 6 that does not resolve in an hour.
