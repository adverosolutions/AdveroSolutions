Hey there 👋 I read your post closely and turned it into the support email autopilot your team would use, [N]-min product tour: https://www.loom.com/share/[LOOMURL]

The video walks through what your support email workflow will look like once it's built and live, a support email going in and a reply in the same Gmail thread coming out: the email captured from Gmail, the support check, the Pinecone matches, the reply in thread, the triage log with escalations and retries, and the test plan and handover.

Under it, an n8n Gmail trigger keeps the sender, subject, body, message ID and thread ID. An OpenAI model checks if it's a support request, and anything else leaves with no reply. The question goes to your Pinecone index as an OpenAI embedding, and OpenAI writes the reply only from matches that clear the score bar. Below the bar, the email is labeled for a person with the closest matches attached. Gmail or OpenAI errors retry, then hand off, keys stay in n8n credentials, and the triage log shows your team where every email went.

The goals view starts empty on purpose. Before launch we'd measure your inbox today, then compare support emails answered from the knowledge base, replies sent to non-support emails and time to first reply.

I work daily in n8n, Make and Claude Code with MCP tools on live APIs, and I have AI agents deployed in my own agency and for numerous client companies. [LORENZO: one or two n8n workflows you've built, and your OpenAI, Pinecone, RAG and Gmail experience, only what's true] Before starting I'd confirm who gets escalated emails, the score bar for replies, and how your Pinecone index is set up. I can start this week.

Where should escalated emails go: a Gmail label your lead watches, a forward to one person, or somewhere else? Reply here and I'll send times for a quick 15 minute call.

Lorenzo

P.S. A few other things I've done:

-> Scaled my own AI agency to $10,000 a month on the same kind of system.
-> $750M+ in annual bid volume runs through a routing and follow-up system I built for a commercial roofing contractor, every estimate request tracked and followed up on, none lost to manual chasing.
-> Increased a software consultancy's qualified lead volume 35% with an outbound system that personalizes each message instead of blasting a template.
-> Generated $5M in loan applications in 30 days on $1,500 of ad spend for a lender, a 3,300x return on the media budget.

---

## Notes for Lorenzo (not part of the proposal)

**What the tour is.** One made-up app, "Support autopilot", a run console for the n8n workflow in their post (Gmail, classify, Pinecone search, write reply, reply in thread). 9 steps: opening, their four goals pinned (word for word), the email captured with the five fields they list, the support check, the Pinecone matches with scores and the reply bar, the reply landing in the same Gmail thread, a triage log (non-support skipped, weak match sent to a person, Gmail error retried) with the escalation reasons and failure settings, their seven test scenarios plus the five handover pieces and goals, then the 15-minute call.

**Honesty choices.**
- Badge, "not an n8n or Gmail screen" title bar, and in-panel notes ("Sample email", "Made-up sender and business", "Illustrative run. Nothing here ran in your n8n or Gmail.", "Illustrative log, not a real run").
- Test scenarios all show "Planned", never passed. Goals show direction only with "Baseline not measured yet".
- The 0.75 score bar and "retries 3 times" are labeled sample or planned settings, not their config.
- No approval step is shown because the post doesn't ask for one; the human path is the escalation.
- Name: two separate client reviews mention "Saqib" (U-006 allows it). The tour and proposal use "your team". If you want, finalize with --name Saqib (same length as "there", preview unchanged).

**Before you send.**
- Replace [N] and [LOOMURL].
- Fill or delete the [LORENZO: ...] bracket. Their "How to Apply" asks for one or two n8n workflow examples and your OpenAI, Pinecone, RAG and Gmail experience. None of that is in the approved facts, so nothing is claimed. The finalizer does NOT catch this bracket, so remove it by hand.
- Their client history shows two earlier closed contracts with nearly the same title (Sept 2026), so they've tried this before. Worth asking on the call what didn't work.
- P.S. order A, R, C, L (AI build for an agency client), agency tail kept since this is an AI agent build.
- Opener uses the product-tour wording from the live-tour template, not "finished and connected" / "The build is done", because this is a prototype. Your pick on locked opener wording is still open.

**Recording.** About 2 minutes. N shows the script, H hides the dock and top bar. Nothing auto-advances.
