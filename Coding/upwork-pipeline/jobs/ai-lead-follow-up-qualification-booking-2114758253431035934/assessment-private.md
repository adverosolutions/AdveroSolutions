# Private notes, pick 2 (4h batch 2026-10-26)
- Source: Vollna RSS description (full body, 175 words). Upwork get returned PERMISSION twice (12:40 CT). Client unchecked; no INDEX.csv match for the job id.
- No name, business or CRM named in the post: personalization omitted (recipient falls back to "your team"); CRM shown as an n8n HTTP Request plus the custom workspace record, never a vendor screen.
- Stack choice: n8n (named in the post, supported adapter). Team alert uses the n8n Slack node as a sample channel; booking link email uses the n8n Gmail node. Calendar tool unnamed, so no booking widget screen and no confirmed booking is shown; the story ends at "booking link sent".

## Scene map (2-minute Standard route)
| Stop | Purpose | New fact | Visible evidence | Seconds |
| --- | --- | --- | --- | --- |
| Cover | Frame the problem: slow follow-up on web and Facebook leads | One sample lead, Dana Ruiz | Title, 3 preview steps | 10 |
| 1 n8n workflow | Show the mechanism | Form, clean details, AI check, save to CRM, worth a call?, alert, booking link; missing-answers branch asks questions | Nodes light up along the sample path; context panel states | 45 |
| 2 Messages (workbench) | Show what people see | Dana's form text, the team alert with summary, the booking link email | Three messages in order | 30 |
| 3 Outcome (workbench) | Show the result | One CRM-style record with answers, AI result, owner, stage "Booking link sent" | Stage tracker, fields, 2 illustrative tiles | 20 |
| Close | Metrics and call | Reply time, good leads offered a call, leads left waiting | 3 directional metrics, blue CTA | 15 |
