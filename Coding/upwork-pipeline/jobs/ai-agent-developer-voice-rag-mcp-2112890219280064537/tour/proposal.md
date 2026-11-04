Hey there 👋 I read your post closely and turned it into the voice and RAG agent console your team would use, [N]-min product tour: https://www.loom.com/share/[LOOMURL]

The video walks through what your voice agent will look like once it's built and live, a phone call going in and a booked job coming out: the call coming in, the agent graph routing it, the answer pulled from your documents, the MCP tool calls that book the visit, the run trace with its reliability checks, and the outcomes view.

Under it, a router agent on Claude sends each call through a LangGraph graph: a policy agent searches your documents in a vector database and cites the passage it used, and a scheduling agent works through MCP tools. The reply only uses IDs the tools sent back, every run is saved with a trace behind a FastAPI service, and if a tool fails the call goes to a person.

The outcomes view starts empty on purpose. We'd measure how your team handles these tasks today, then compare calls handled without staff time, answers backed by a source, and workflows running in production.

On your questions: I have Claude and Grok agents deployed in my own agency and for numerous client companies, and I've built AI agents on a client's existing database for numerous companies. [VOICE AI AND RAG PROJECTS, only if true] I work daily in n8n, Make and Claude Code with MCP tools on live APIs. [MULTI-AGENT EXPERIENCE, only if true] My usual stack is Claude with MCP tools, with n8n or Make on the workflow side. [PYTHON, LANGGRAPH, FASTAPI, VECTOR DATABASE, only if you've shipped with them] Timeline and cost depend on which build goes first, so we can cover that on the call. I can start this week.

Which build would you want first: the voice agent, a RAG application, a multi-agent workflow or a workflow automation? Reply here and I'll send times for a quick 15 minute call.

Lorenzo

P.S. A few other things I've done:

-> Scaled my own AI agency to $10,000 a month on the same kind of system.
-> $750M+ in annual bid volume runs through a routing and follow-up system I built for a commercial roofing contractor, every estimate request tracked and followed up on, none lost to manual chasing.
-> Increased a software consultancy's qualified lead volume 35% with an outbound system that personalizes each message instead of blasting a template.
-> Generated $5M in loan applications in 30 days on $1,500 of ad spend for a lender, a 3,300x return on the media budget.

---

## Notes for Lorenzo (not part of the proposal)

**What the tour shows.** An "Agent console" for "your team" (no client name is known, so U-006 falls back to "your team"). It has a dark left rail (Calls, Tools, Run trace, Outcomes) and a pinned column with four quotes from the post and the stack the post names. It follows one made-up phone call to a made-up property manager, Brightwater Flats, in 9 steps: opening, the post's asks pinned, the live call with transcript, the LangGraph agent graph (router, policy agent, scheduling agent), retrieved passages with a citation, four MCP tool calls that return WO-2291 and BK-6107, the run trace with reliability checks and FastAPI endpoints, outcomes as goals, and a "pick the first build" dialog with the 15-minute call ask.

**Honesty choices.**
- Badge "Illustrative prototype · made-up data", title bar "Illustrative prototype, not a LangGraph screen", and in-panel notes (made-up caller, made-up documents, "Illustrative run. Nothing here ran in your systems.", "Sample timings").
- The post has no human approval step, so the tour doesn't invent one. The only handoff is the fallback to staff when a tool fails.
- Outcomes show direction only, each quoting the post, with empty "Baseline not measured yet" bars.
- The stack chips are labeled "Stack named in your post". They're the client's stack, not a claim about yours. No voice vendor is named.
- No price talk. The timeline and budget question gets "we can cover that on the call".

**Before you send.**
- Replace [N] and [LOOMURL].
- Fill or delete the three bracketed placeholders. The post asks for voice AI and RAG projects, multi-agent experience, and Python, LangGraph, FastAPI and vector database work. None of these are approved facts, so nothing claims them. Add only what's true.
- No required first word or keyword in the post.
- P.S. bullets are word for word, in the A, R, C, L order for AI builds. The agency tail stays because this is an AI agent build.

**Recording.** 9 steps, about 2 minutes. Press N for the script, H to hide the dock and top bar. Next or Right Arrow advances. Nothing advances on its own.
