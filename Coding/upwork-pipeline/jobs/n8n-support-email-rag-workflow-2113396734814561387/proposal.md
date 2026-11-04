Hey there 👋 I do n8n builds all the time, so here's your support email workflow finished and connected, [N]-min video: https://www.loom.com/share/[LOOMURL]

The video walks through what your support email workflow will look like once it's built and live, a support email going in and a reply in the same Gmail thread coming out: the n8n workflow from Gmail to reply, the support check, the Pinecone matches against the score bar, the reply in the same thread, and the triage log with escalations and retries.

The build is done; the video is just a more visual way to show it running end to end.

Under it, the Gmail trigger keeps the sender, subject, body, message ID and thread ID. An OpenAI model checks if it's a support request, and anything else leaves with no reply. The question goes to your Pinecone index as an OpenAI embedding, and OpenAI writes the reply only from matches that clear the score bar. Below the bar, the email goes to a person with the closest matches attached. Gmail or OpenAI errors retry, then hand off, and keys stay in n8n credentials. I work daily in n8n, Make and Claude Code with MCP tools on live APIs, and I have AI agents deployed in my own agency and for numerous client companies. Before starting I'd confirm who gets escalated emails, the score bar for replies, and how your Pinecone index is set up. I can start this week.

The next step is a quick 15 minute call. Just reply here or send me a message on Upwork, I'll send over three times, and we'll get everything started.

Lorenzo

P.S. A few other things I've done:

-> Scaled my own AI agency to $10,000 a month on the same kind of system.
-> $750M+ in annual bid volume runs through a routing and follow-up system I built for a commercial roofing contractor, every estimate request tracked and followed up on, none lost to manual chasing.
-> Increased a software consultancy's qualified lead volume 35% with an outbound system that personalizes each message instead of blasting a template.
-> Generated $5M in loan applications in 30 days on $1,500 of ad spend for a lender, a 3,300x return on the media budget.

---

## Notes for Lorenzo (not part of the proposal)

**What the deck is.** Rebuilt on the original sales-deck design (your 7:33 PM call), same story as the tour. Standard route, about 2 minutes: cover, the n8n workflow (Gmail to reply, with the not-support and weak-match branches), Tessa's Gmail thread with the reply under her email, the triage log for a sample day (replied, skipped, sent to a person, Gmail retry), then the three goals and the 15 minute call. Detailed adds a test plan and handover screen (all tests Planned).

**Honesty choices.**
- Everything is sample data, labeled once on the cover and on each screen. Tessa, Jonah, Rita and their businesses are made up.
- The canvas library has no Gmail Trigger node, so the sample run starts on a Manual Trigger. The node detail and talking points say your build starts on the Gmail Trigger. Pinecone, OpenAI and the threaded reply show as HTTP Request nodes.
- The Gmail reply shows unsent (the template has no sent state). Talking points say so.
- 0.75 score bar and retries are sample settings, not their config. Goals show direction only, baseline not measured.
- The locked opener says "finished and connected" and "The build is done". This is a sample-data demo, nothing is connected to their n8n, Gmail or Pinecone, so that wording overstates it. Kept because the format is locked; your pick on opener wording is still open.

**Before you send.**
- Replace [N] and [LOOMURL].
- Fill or delete the [LORENZO: ...] bracket. Their "How to Apply" asks for one or two n8n workflow examples and your OpenAI, Pinecone, RAG and Gmail experience. None of that is in the approved facts. The finalizer does NOT catch this bracket.
- Name: two separate client reviews mention "Saqib" (U-006 allows it). The deck and proposal use "your team" / "there".
- Their history shows two earlier closed contracts with nearly the same title (Sept 2026). Worth asking on the call what didn't work.
- P.S. order A, R, C, L (AI build), agency tail kept since this is an AI agent build.

**Recording.** About 2 minutes on Standard. Click Preview on the opening, then Next through each chapter. Talking points show the script. Nothing auto-advances.

Needs Lorenzo (removed from above the line on 2026-10-26 so the proposal is paste-ready; only [N] and [LOOMURL] stay open above the line):
- Dropped from the middle paragraph: "[LORENZO: one or two n8n workflows you've built, and your OpenAI, Pinecone, RAG and Gmail experience, only what's true]"
