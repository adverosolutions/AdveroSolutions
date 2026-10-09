# Assessment (private) - Zoho CRM lead-gen build

## The build, in one breath (their "proposed approach")
One webhook takes every website and landing-page form, with the UTM tag from Google or Facebook ads. Apollo adds title, company, website and location. Zoho CRM upserts the lead, matched on email then phone, so a repeat form fill updates instead of duplicating, and only new leads start the follow-up. Email 1 goes from Gmail within a minute (BCC to Zoho), and a text goes the next day only if Zoho still shows the lead not contacted. Every Monday a Google Sheets "Lead Dashboard" tab refreshes leads, converted and conversion rate per source for the last 30 days.

Canvas: 13 spec nodes plus the Config node = 14. No error trigger on the canvas (ceiling); the setup list points the workflow at their n8n error workflow.

## Time
| Piece | Hours |
|---|---|
| Capture: webhook, hidden UTM fields on their form(s), a test lead per source | 1.5-2 |
| Apollo match and the no-match path | 1 |
| Zoho: OAuth2 credential, mapping to their Lead layout (mandatory and custom fields), Lead Source picklist, dedup tests (new, repeat by email, repeat by phone) | 4-5 |
| Follow-up: Gmail with BCC dropbox, wait, status check, Twilio, their approved copy | 2-3 |
| Report: Zoho pull, counting, Sheet tab with a chart | 2 |
| End-to-end test with real leads, error workflow, handover Loom | 3 |
| Revisions | 2-4 |
| **Total** | **16-20 hours** |

Calendar: about 2 weeks. Week 1: capture, Apollo and Zoho live on real test leads, Email 1 on. Week 2: next-day text, dashboard, handover. The text's go-live waits on Twilio's A2P 10DLC approval, which is outside our control (typically days to a few weeks; unverified for their account).

## Likelihood
Standard parts (webhook, Zoho REST, Gmail, Sheets): high. What breaks, weighted to their accounts:
1. **UTM tags (the biggest risk to their line 5).** If their forms don't pass utm_source, or their ads carry no UTM tags, every lead reads "Website" and the by-source report is flat. On the build (section 1 note, setup list) and in a beat.
2. **Zoho layout.** Custom mandatory fields or validation rules on their Lead layout make the upsert fail until mapped. Lead Source values outside the picklist may be rejected; setup adds Google Ads and Website. US data center (zohoapis.com) assumed; .eu or .in changes every URL.
3. **Zoho API credits and edition.** Daily API credits scale with edition and licences; unknown until we see their account.
4. **Apollo.** Match rate is low on personal Gmail/Yahoo addresses; the API needs a paid Apollo plan and spends credits per match. The flow keeps going on a miss (the Apollo node continues on error).
5. **Twilio A2P 10DLC.** US texting is filtered or blocked until the brand and campaign are registered.
6. **Returning leads take their newest Lead Source** (the upsert overwrites it: last touch). First touch needs a search-then-create step (+1 to 2 nodes, +1 hour). Ask them.
7. **The text's stop rule depends on reps updating Lead Status in Zoho.** If nobody does, every new lead gets the text.
8. **The report pulls the newest 200 leads.** Over 200 leads in 30 days needs the HTTP node's pagination (+30 min).
9. **Dedup checks Leads only.** An existing customer (a Contact) who fills the form becomes a new lead.

Unverified for Lorenzo, say it plainly to himself: Zoho CRM, Apollo and Twilio API work are not in his facts list, so nothing in the proposal or Loom claims a past Zoho build. Before recording, check on a Zoho trial: the upsert response's `data[0].action` (insert / update), `converted=both` and `$converted` on GET /Leads, and what Zoho returns on GET for a converted lead (the status check continues on error, and the gate then stays closed). Also confirm optional chaining (`?.`) in expressions on their n8n version (fine on n8n 1.x).

## Standard pricing
- Market for this scope: $50-$100/h n8n freelancers x 16-20 h = $800-$2,000; agencies $2,500-$5,000 fixed. Defensible fixed range: **$1,200-$2,000**.
- The post's rate vs market: the $25 is a placeholder (they ask for a fixed price or hourly estimate). Recorded bids average $107.89 (range $10-$1,020), and their history is $2,561.64 over 57 contracts, about $45 each. This client has never paid near market for one job.
- **Quote to give (they asked for both):** fixed **$1,200** in two milestones ($600: capture, Apollo, Zoho with dedup; $600: follow-up sequence and dashboard), or **$55/h, estimated 18-22 hours**. The milestone split lets a buyer who spends small say yes to the first half.
- Recurring software (theirs, rough, to confirm): n8n Cloud Starter about $24/mo or a self-hosted VPS about $5-10/mo; Apollo paid plan, roughly $49-$99 per user a month; Twilio number about $1-2/mo, about a cent per text, plus one-time 10DLC registration fees and a small monthly campaign fee; their existing Zoho CRM and Google Workspace.

## Ask before quoting
1. Which ad platforms and form tools? Landing-page forms with UTM tags, or Meta / LinkedIn instant forms (each instant-form source is its own trigger, +1-2 hours)?
2. Which enrichment API, if any, do they already pay for?
3. Follow-up: how many touches, which channels, sent as whom? Do they already have Twilio or WhatsApp Business?
4. Zoho: edition, data center, mandatory and custom Lead fields, their Lead Source values; first touch or newest source on returning leads?
5. Lead volume per month (Apollo credits, Zoho API credits, report paging).
6. Dashboard in a Sheet, or in Zoho's own reports / Zoho Analytics?
7. n8n Cloud or self-hosted, and whose account?
8. Should an existing customer (Zoho Contact) filling the form create a new lead?

## Flags
- No US-only requirement in the post.
- "Screen recording or portfolio link preferred over description": the Loom of this canvas is the screen recording. No portfolio link needed.
- HubSpot is in their skills tags but not in the scope. Don't raise it unless they do.
- Price-sensitive history (above): lead with the milestone split.
