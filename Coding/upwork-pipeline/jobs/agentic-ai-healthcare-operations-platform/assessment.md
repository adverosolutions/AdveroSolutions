# Assessment (private) - Agentic AI Developer for Healthcare Operations Platform

## Time
Real hours, not the happy path.
- Working demo of workflow one (this canvas running on a test Supabase
  project, pgvector, a handful of invented policies and SOPs, test intake
  items, every arm exercised: refused, no-match, low confidence, fallback,
  routed, error): 12 to 16 hours, 1 week.
- Phase 1 production of workflow one in their stack: FastAPI service, Supabase
  schema with row-level security and roles, append-only audit log, knowledge
  ingest with versions (PDF/DOCX upload, chunking, embeddings), triage with
  Claude primary and OpenAI fallback, the confidence gate and review queue,
  one adapter into their internal tool, minimal staff screen and admin review
  screen, a golden-set check: 90 to 130 hours, 5 to 7 weeks.
- Full platform MVP (all seven core features: admin knowledge editor with
  versions, workflow settings for queues, thresholds and prompts, staff app
  polish, cost and usage logging, evals, deployment hardening, handoff docs):
  180 to 260 hours in total, 10 to 14 weeks.
- Add 15 to 30 hours if intake arrives as scanned faxes or photos (OCR and
  its error handling are not on the canvas).

## Likelihood
- Demo on test data: high, about 90%. The canvas nodes are unverified until
  run; several catalog entries (chainLlm 1.5, Postgres 2.5 executeQuery with
  array query parameters) are marked unverified, so test-run it once on a
  scratch n8n before recording if he plans to execute anything on camera.
- What breaks in production, weighted to their accounts and data:
  1. Their internal tool is unnamed. It may have no API, no sandbox, or a
     vendor that charges for API access. This moves phase 1 by weeks.
  2. Compliance, the biggest one. Real patient data cannot go to Anthropic,
     OpenAI, Supabase or an n8n host without a signed BAA and their
     compliance sign-off. Supabase's BAA sits on a higher paid tier (price
     unverified, check current plans); n8n Cloud may not sign one
     (unverified), so self-host n8n or keep production in FastAPI. Until
     then everything runs on invented test data. Never write or say "HIPAA
     compliant" or "HIPAA certified"; say "designed so it can run under your
     BAAs".
  3. The masking step is a regex pass. It reduces what reaches a model; it is
     not de-identification and must never be presented as such.
  4. Knowledge-base quality: contradictory or outdated SOPs push confidence
     down and flood the review queue in the first weeks. That is the system
     working, but they must expect it and assign an owner per document.
  5. Scope versus budget: $1,300 against seven features. If they expect the
     platform for $1,300 it fails on expectations, not on code.
- Unverified for Lorenzo (say it plainly, frame it honestly):
  - No healthcare project and no RAG system in his facts. Do not claim
    either. The prototype on the Loom is the RAG example; his live example
    of an AI agent is his own outbound system (an agent researching and
    writing each of 100k+ emails a month on Instantly, plus a daily metrics
    dashboard), and his closest routing example is the roofing bid-routing
    system.
  - FastAPI and React production builds are not in his facts. He builds in
    n8n and Make daily and uses Claude Code and the Anthropic API daily with
    MCP tools wired into live software. Frame production as "the same design,
    moved into FastAPI", never as past FastAPI projects.
  - No production claims for LangChain or LangGraph. Recommend LangGraph
    only as an option where a workflow loops, not as something he has shipped.
  - Solo or team is not in his facts; the answer is his.

## Standard pricing
Reference numbers (he bids below on purpose):
- Paid discovery plus the working workflow-one prototype and an architecture
  and phasing plan: $2,000 to $4,000 market.
- Phase 1, workflow one in production: $9,000 to $18,000 (90 to 130 hours at
  $100 to $140 an hour for a US expert; offshore teams lower).
- Full platform MVP: $18,000 to $40,000.
- The post's $1,300 fixed covers the prototype plus the architecture plan at
  most, roughly $186 per feature across their seven. Recorded bids run from
  $10 to $37,000 (avg $1,626.33), so others priced everything from a sketch
  to the full build; pitching $1,300 as phase 0 with priced later milestones
  is the defensible position.
- Recurring software, monthly (list prices, check before quoting):
  - Supabase: Pro from about $25; the BAA-covered tier costs materially more
    (unverified, check).
  - Self-hosted n8n on a small VM: about $20 to $40, or none if production
    logic lives in FastAPI.
  - FastAPI and staff app hosting on a cloud that signs a BAA: about $50 to
    $200 depending on setup.
  - Model usage: about 3,500 input and 400 output tokens per item on a
    Sonnet-class model is roughly 1 to 2 cents an item; embeddings are a
    fraction of a cent. Their monthly model cost = their monthly item count
    (unknown, "high volume") x that. Cost control: cheaper model first for
    easy items, escalate only when unsure; cap tokens per item.

## Ask before quoting
1. Which internal tools or CRM-style system do tasks land in, and is there
   API documentation and a sandbox?
2. What is "high volume": items per day or month, and how many staff users?
3. What arrives: typed forms, PDFs, scanned faxes, photos? (OCR moves the
   estimate.)
4. How many policies, SOPs, forms and service guidelines exist today, in what
   format, and who owns keeping each current?
5. Staff roles and queues: who submits, who reviews AI outputs, who edits
   knowledge sources?
6. Compliance posture: are they a covered entity or a business associate, do
   they already have BAAs with a cloud provider, and will they sign with
   Anthropic, OpenAI and Supabase?
7. Is the $1,300 for a first milestone (prototype plus architecture) or meant
   to cover the platform?
8. Hosting preference and existing stack (Python or Node), and is there an
   existing staff web app to plug into or is it new?

## Flags
- Not marked US-only, but a Florida healthcare business means US patient data
  and HIPAA context: copy asserts no location and no HIPAA certification.
- Portfolio demand: "Examples of AI agents, RAG systems, or automation
  platforms you have built". He has agent and automation examples, no RAG
  example: answer with what is true and let the prototype carry RAG.
- No rule against contact outside Upwork is stated.
- Budget: $1,300 fixed for a seven-feature platform at expert level; 0
  invites, 0 interviewing, so the field is open.
- Strong payer: $126.8k spent, 5.0 over 110 reviews, 136 contracts. They buy
  scoped fixed-price pieces; a clean phase 0 fits how they hire.

## To Apply answers (for the proposal and the Loom)
1. Examples built: his own outbound system (agent researches and writes each
   of 100k+ cold emails a month on Instantly, plus a daily metrics
   dashboard); n8n and Make builds daily; Claude Code and the Anthropic API
   daily with MCP tools wired into live software; the routing and follow-up
   system behind $750M+ in annual bid volume for a commercial roofing
   contractor; the consultancy outbound system (+35% qualified leads); his own
   agency to $10,000 a month. No RAG claim.
2. Stack and architecture: FastAPI (Python); each workflow a defined list of
   typed steps on shared services (retrieval, model layer with fallback,
   review queue, audit log), so a new workflow is a new step list, not a
   rebuild; Supabase Postgres, pgvector, Auth with row-level security,
   Storage; Claude primary, OpenAI fallback and embeddings; one REST adapter
   per internal tool; a plain React staff app and admin screen; LangGraph
   only if a workflow needs loops. The n8n canvas is the prototype.
3. Unsafe-output prevention: answers only from retrieved active documents;
   every next step cites a retrieved passage and cited ids are checked against
   what was retrieved; no source means no AI answer (the item goes to a person
   and is logged as a knowledge gap); hard boundaries in the prompt (no
   diagnosis, symptoms, treatment or urgency-of-care calls; clinical content
   goes to a person); the queue must be one of theirs; strict output schema at
   temperature 0; a confidence gate into the human review queue; OpenAI
   fallback on the same rules, and a double failure goes to a person;
   identifiers masked before any model call; an append-only audit row per
   action; a golden set of past items re-run on every prompt or knowledge
   change; the review-queue override rate tracked as the accuracy number.
4. Timeline and availability: demo by [DRAFT]; phase 1 in 5 to 7 weeks; full
   MVP in 10 to 14 weeks; start [START]; weekly hours are his to state.
5. Solo or team: his call (not in his facts). Default "solo".
6. Their question: build first = workflow one end to end on the shared base,
   because every later workflow reuses it. Staying useful as the knowledge
   base grows: versioned documents, only active versions retrieved, old
   versions retired not deleted, role and service-line filters, re-index on
   every admin edit, no-match items logged as gaps, keyword plus vector search
   with reranking once it grows, an owner and review date per document, and
   the golden-set check on every change.

## Sharp insight, and where it is on the build
Build workflow one on a shared base so later workflows reuse it and nothing
is rebuilt ("new workflows can be added later without rebuilding the entire
system", their words): the title ("... First"), the overview setup lines,
beats 2 and 7. The data risk (no real patient data before BAAs): the
overview's need-from-you line and beat 3. The dollar figures stay here.
