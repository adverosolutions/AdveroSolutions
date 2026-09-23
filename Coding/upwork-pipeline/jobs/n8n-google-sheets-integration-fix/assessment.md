# Private assessment (not for the proposal)

**Time.** 1 to 3 hours of real work once he has access to the workflow and one failed
execution, same day turnaround. Diagnosis is most of it; the fix is usually a handful of
node settings. The hardened version on the canvas is a pattern he already builds weekly,
so rebuilding their sheet step with guards on top adds maybe an hour, not a day.

**Likelihood.** High. "No longer updating Google Sheets correctly" is a short list of
causes and he can name all of them on camera before he ever sees the account, which is the
whole pitch. Realistic root causes, in rough order of frequency: an expression type
mismatch (numbers arriving as strings like "1,249.00", dates arriving as ISO text or as a
raw serial), a renamed sheet or tab or a changed or reordered column header, an expired or
revoked Google OAuth credential (or a service account that lost access when the file was
re-shared), a 429 rate limit on bursts where Sheets throttles writes, and an append step
where it should be an update with a matching column, which looks like "not updating" but is
actually duplicating. Main risk is access: if they will not export the workflow JSON or
share a screen, this stalls. Second risk is the sheet itself being the problem (100k plus
rows, formulas, filter views), which is a different and bigger job. Cap scope at the one
workflow they show him.

**Standard pricing.** Market for a diagnosed and tested fix on one broken n8n to Sheets
integration is roughly $75 to $250 fixed, or $75 to $125 an hour. This post is $10 fixed,
so it is far under market and he knows it. Take it at their number anyway. The client
record is the real prize: 59 contracts, 54 hires, $2.5k spent, 5.0 across 54 reviews, and a
steady habit of small one-day fixed tickets (scraper fixes, Webflow, DMCA, Walmart
listings, lead lists). This is a door opener into a stream of small paid fixes, not a rate.
Do not anchor future work to $10; deliver fast, then ask what the next task on the list is.
No recurring software to quote, Sheets and Slack are free at this volume.

**Ask before quoting anything beyond this ticket.**
- n8n cloud or self hosted, and which version?
- When did it last work correctly, and what changed around then (sheet edits, credential
  re-auth, n8n upgrade, new columns)?
- Can they send a screenshot or export of the failing execution log?
- Is the Google credential a service account or OAuth, and who owns it?
- How big is the sheet, how many rows and tabs, and is anything else writing to it?
- Should it update matched rows or append, and which column is the unique key?
- How many records per run and per day, so backoff and batch size are sized right?

**Flags.** Client is in Texas, Chicago timezone; do not assert a location in copy.
Application asks for relevant n8n plus Sheets experience and examples of similar
troubleshooting work; the Loom answers both, the P.S. carries the proof. 14 connects.
