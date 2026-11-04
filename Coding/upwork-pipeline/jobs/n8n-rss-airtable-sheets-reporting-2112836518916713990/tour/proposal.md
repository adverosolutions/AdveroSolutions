Hey there 👋 I read your post closely and turned it into the n8n RSS feed desk your team would use, [N]-min product tour: https://www.loom.com/share/[LOOMURL]

The video walks through what your RSS reporting workflow will look like once it's built and live, your RSS feeds going in and a Gmail report coming out: the scheduled run pulling four feeds, the merge, filter and limit step, the new Airtable records and Google Sheets rows, the summary email, the follow-up rule, and the outcomes view.

Under it, an n8n schedule trigger reads every feed in one run, merges the results and drops duplicates by link, then filters and limits them to your criteria. Each item becomes an Airtable record and a row appended to your sheet, an aggregate step builds the summary, and Gmail sends it. An IF step checks your follow-up rule on every run, and if a feed is down the run keeps going and the report names it.

The outcomes view starts empty on purpose. Before launch we'd measure how your team handles these feeds today, then compare manual steps per run, runs that finish on time, and items missed or saved twice.

I work daily in n8n, Make and Claude Code with MCP tools on live APIs, and I deploy systems daily. I can start this week.

Which feeds and criteria would you want set up first, and who should get the report? Reply here and I'll send times for a quick 15 minute call.

Lorenzo

P.S. A few other things I've done:

-> Scaled my own AI agency to $10,000 a month.
-> $750M+ in annual bid volume runs through a routing and follow-up system I built for a commercial roofing contractor, every estimate request tracked and followed up on, none lost to manual chasing.
-> Increased a software consultancy's qualified lead volume 35% with an outbound system that personalizes each message instead of blasting a template.
-> Generated $5M in loan applications in 30 days on $1,500 of ad spend for a lender, a 3,300x return on the media budget.

---

## Notes for Lorenzo (not part of the proposal)

**What the tour shows (9 steps, about 2 minutes).** One made-up app, "Feed desk · your team", with a dark icon rail (Run, Records, Digest, Goals) and a pipeline strip across the top (Schedule, Pull feeds, Merge and filter, Save, Summary, Follow-up) that lights up stage by stage and stays on screen the whole time. Views: the run board (your checklist quoted from the post, four sample RSS sources with item counts, a 48 to 41 to 12 to 10 merge, filter and limit funnel), saved records (an Airtable style grid and a Google Sheets style log with 10 rows appended under yesterday's), the digest (the Gmail summary email plus the IF/AND/THEN follow-up rule checking three records), the goals view, then the 15-minute call card.

**Honesty choices.**
- Labelled three ways: the page badge ("Illustrative prototype · made-up data"), the title bar ("Illustrative prototype, not an n8n, Airtable or Gmail screen") and in-panel notes ("Sample feeds", "Made-up items", "Sample email. Nothing was sent.", "Illustrative run. Nothing here ran in your n8n.").
- Feeds, companies, criteria keywords, schedule time (weekdays 7:00 AM) and counts are invented samples. The criteria panel says your real criteria replace them on the call.
- Outcomes show direction only with "Baseline not measured yet", and quote the post ("minimal manual work", "reliable, maintainable workflows").
- No client name (post has none, U-006 fallback "your team"). No price talk.
- I used the tour opener from the live-tour README instead of the deck line "finished and connected / The build is done", because the tour is a prototype with made-up data and nothing ran in their accounts.

**Recording.** Press N for the script, H to hide the caption dock and top bar. Nothing advances on its own; Right Arrow or Next.

**Before you send.**
- Replace [N] and [LOOMURL].
- The post asks for "strong experience with n8n", Airtable, Google Sheets, RSS and Gmail automation. Only "works daily in n8n, Make and Claude Code" and "deploys systems daily" are approved, so no Airtable, Sheets, RSS or Gmail experience is claimed. Add a line only if it's true.
- P.S. order A, R, C, L (automation build). The agency bullet ends at "$10,000 a month." because this reporting build is not what the agency itself runs on.
- No screening questions or required first word in the post.
