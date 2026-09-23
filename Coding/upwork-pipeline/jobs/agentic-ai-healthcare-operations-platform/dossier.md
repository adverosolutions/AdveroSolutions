# Dossier - Agentic AI Developer for Healthcare Operations Platform

url: https://www.upwork.com/jobs/~022102823599813958957

## Who they are
- First name: unknown (no `client first name:` line in jd.txt; the post is unsigned)
- Company: unknown (the post says only "a healthcare services business")
- Industry: "a healthcare services business that handles a high volume of
  patient-related administrative work". The poster looks like an operator or
  holding that runs or serves several businesses (their hires span Klaviyo,
  Shopify, Google Ads for kitchen and bath jobs); this post is for the
  healthcare one.
- Location / timezone: Florida (US), America/New_York
- Website read: none named

## Client (from `client.json`; write "no client intel" when the file is missing)
no client intel

## Tools they named
In the order they appear:
1. "OpenAI and/or Claude"
2. "existing internal tools or CRM-style systems" (not named)
3. "Python, API development, AI agent development, and full-stack implementation"
4. "FastAPI, Node.js, vector databases, PostgreSQL, Supabase, LangGraph,
   LangChain, LlamaIndex, or similar tools"

Committed for the build: Claude as the primary model, OpenAI as the fallback
and for embeddings (they named both); Supabase Postgres with pgvector for the
knowledge base, review queue, intake items and audit log (they named
Supabase, PostgreSQL and vector databases). Their internal tool is unnamed, so
the routing call is to "Your Internal Tools API" with the base URL as a
labelled config input, and which system it is goes under Ask before quoting.
The prop is n8n, framed honestly: the canvas is the working prototype of
workflow one; production is Python/FastAPI on Supabase, as they asked.

## Every number in the post
- "$1,300" fixed price, "expert" level
- 7 "Core Features" bullets, 5 "To Apply" items, 1 "Question"
- No volume given: "a high volume of patient-related administrative work"
  (their monthly item count is their input, never stated)
- Metadata that matters: 136 contracts, 119 jobs with hires, 1 active,
  $126.8k spent, 5.0 over 110 reviews, 780 hours; posted about 2026-09-23;
  0 invites, 0 interviewing, 0 hired; bids avg $1,626.33, range $10-$37,000;
  21 connects

## Their requirements, verbatim, in their order
1. "AI agent workflows for intake support, document triage, and internal task routing"
2. "RAG and knowledge-base architecture for policies, SOPs, forms, and service guidelines"
3. "OpenAI and/or Claude integrations with clear reasoning boundaries and fallback behavior"
4. "API integration with existing internal tools or CRM-style systems"
5. "Admin interface for reviewing AI outputs, editing knowledge sources, and managing workflows"
6. "Logging, permissions, and basic audit trail for actions taken by the system"
7. "Clean web interface for staff users, with practical UX rather than over-designed screens"

7 parts in your post, 5 sections on the canvas (plus an error section after
theirs):
- Section 1 = part 1 (intake support and document triage; the "internal task
  routing" half of part 1 happens in section 4, and the note says so)
- Section 2 = part 2 (RAG over policies, SOPs, forms, service guidelines,
  including the KB 1 to KB 4 re-index chain an admin edit triggers)
- Section 3 = part 3 (Claude first, OpenAI fallback, reasoning boundaries)
- Section 4 = parts 4 and 5 grouped (the API call into their internal tools,
  and the review queue behind their admin screen)
- Section 5 = parts 6 and 7 grouped (audit trail, permissions, logging, then
  the staff screen)

Also answered, not as sections (the main session puts them in the proposal):
the five "To Apply" items and "Question: What would you build first in this
platform, and how would you make sure the AI stays useful as the knowledge
base grows?"

## The odd ask only they would recognize
"The goal is not to replace clinical judgment". On screen: gate 10 "Confident,
Cited, Known Queue, Nothing Clinical?", the Claude system message (never
diagnose, never judge urgency of care, clinical content goes to a person),
the section 3 note, beat 5. Runners-up they would also recognize: "This should
be more than a simple chatbot" (the canvas has no chat at all, it acts
through APIs) and "practical UX rather than over-designed screens" (the staff
screen gets a plain status, owner, next steps and cited sources).

## What their hiring history implies
136 contracts and $126.8k spent is about $930 a contract: a high-volume hirer
of well-scoped fixed-price pieces who rewards delivery (5.0 over 110 reviews).
Their recent hires are marketing and e-commerce, so this is a new kind of
build for them and they will judge it on judgment and a working thing, not on
jargon. $1,300 fixed for a seven-feature platform means they are either
buying a first piece or have not priced it yet; bids up to $37,000 say some
applicants priced the whole platform. The honest pitch is a working workflow
one plus the architecture and phasing, with the rest as later milestones.

## Their likely data
One intake item as the staff portal would send it. Clearly invented, minimal,
no real-looking identifiers (the DOB and phone exist only to show the masking
step working):

```json
{
  "body": {
    "item_id": "INT-TEST-0001",
    "staff_user_id": "staff-test-017",
    "service_line": "all",
    "document_type_hint": "referral",
    "patient_ref": "TEST-PT-0001",
    "patient_display_name": "Test Patient A",
    "document_file": "test-referral-0001.pdf",
    "document_text": "TEST RECORD, NOT A REAL PATIENT. Referral for Test Patient A, DOB 01/01/1900, phone 000-555-0100. Reason for referral: new patient intake. Insurance card copy attached. Authorization section: blank. Please schedule the first available intake appointment.",
    "submitted_at": "2026-09-23T09:14:00-04:00"
  }
}
```

What staff see afterwards (the last node):

```json
{
  "item_id": "INT-TEST-0001",
  "status": "routed",
  "owner_queue": "Intake Coordination",
  "staff_summary": "Referral for a new patient with an insurance card copy attached. The authorization section is blank, so it is not ready to schedule.",
  "next_steps": ["Verify insurance eligibility before scheduling", "Request the missing authorization page from the referring office"],
  "cited_sources": ["Referral Intake SOP v3, Required documents", "Authorization Policy v2, When an authorization is required"],
  "ai_model": "claude",
  "ai_confidence": 0.91,
  "task_ref": "TASK-TEST-0412"
}
```

## Sizing (setup / infrastructure / method jobs only)
Not a setup job, but the budget against the scope, from their own numbers:
$1,300 fixed across 7 core features is about $186 a feature. That buys one
workflow end to end plus the architecture and phasing, not seven features.
The insight the client values, and the one that goes on the build: build
workflow one first on a shared base (knowledge base, model layer with
fallback, review queue, audit log), so every later workflow reuses it and
"new workflows can be added later without rebuilding the entire system", in
their words. On screen: the title ("... First"), the overview "setup" lines,
beat 2 and beat 7. The dollar figures stay private (assessment, proposal).
Their item volume ("high volume") is their input: monthly model cost = their
monthly item count x the per-item cost in the assessment.

## Three things they would recognize on screen
1. "not to replace clinical judgment": gate 10 label "10 - Confident, Cited,
   Known Queue, Nothing Clinical?", the Claude system message, section 3
   note, beat 5.
2. Their question ("What would you build first ... stays useful as the
   knowledge base grows"): title "Your Healthcare Operations Platform: Intake
   and Document Triage First", the KB 1 to KB 4 chain (admin edits a policy,
   SOP, form or guideline, it is re-indexed, the old version retired), the
   section 2 note, beats 2 and 4.
3. Their tools and "reliable, auditable": "8 - Claude Triages Using Only Your
   Documents", "9b - OpenAI Fallback: Same Rules, Same Sources", "6 -
   Supabase: Find the Matching Policy, SOP and Form Passages", "13 - Supabase:
   Write the Append-Only Audit Rows", section 5 note, beat 7.

## Beat 1 draft
"This is intake support and document triage for your healthcare services business."

## To Apply answers (source for the main session's proposal)
1. Examples built (facts only, never invented): his own outbound system,
   100k+ cold emails a month on Instantly with an agent researching and
   writing each message, plus a daily metrics dashboard; he builds in n8n and
   Make daily and uses Claude Code and the Anthropic API daily with MCP tools
   wired into live software; the routing and follow-up system behind $750M+
   in annual bid volume for a commercial roofing contractor (closest match to
   "internal task routing": every request tracked, none lost); the
   consultancy outbound system (+35% qualified leads); his own AI agency to
   $10,000 a month. No RAG system is in his facts: do not claim one. The
   prototype on the Loom is the RAG example.
2. Recommended stack and architecture: Python + FastAPI (their preference),
   each workflow a defined sequence of typed steps (intake, mask, retrieve,
   triage, gate, route or review, audit) so a new workflow is a new step list
   on the same services; LangGraph only where a workflow needs loops, not
   required for workflow one. Supabase: Postgres for intake items, tasks,
   review queue and an append-only audit log; pgvector for the knowledge base;
   Supabase Auth with row-level security for roles and permissions; Storage
   for uploaded documents. Claude primary with structured JSON output, OpenAI
   fallback on the same prompt and schema, OpenAI embeddings. One REST adapter
   per internal tool or CRM-style system. A plain React staff app and admin
   screen (review queue approve/edit/reject, knowledge-source editor with
   versions, workflow settings for queues, thresholds and prompts). n8n is the
   prototype now; production logic lives in FastAPI.
3. Preventing inaccurate or unsafe outputs: retrieval-only answers from the
   active version of their documents; every next step must cite a retrieved
   passage, and cited ids are checked against what was actually retrieved; no
   matching source means no AI answer, the item goes to a person and is
   logged as a knowledge-base gap; hard boundaries in the system prompt (no
   diagnosis, no symptom assessment, no treatment or urgency-of-care calls,
   clinical content goes to a person); the queue must be one of theirs;
   temperature 0 and a strict output schema; a confidence gate into a human
   review queue; OpenAI fallback runs the same rules and a double failure goes
   to a person; identifiers masked before any model call; an append-only
   audit row per action; a golden set of past items re-run on every prompt or
   knowledge-base change; the review-queue override rate as the running
   accuracy number.
4. Timeline and availability: working demo of workflow one by [DRAFT] (12 to
   16 hours); phase 1 production of workflow one in FastAPI and Supabase with
   minimal staff and admin screens in 5 to 7 weeks; the full platform MVP in
   10 to 14 weeks. Start [START]; weekly hours are Lorenzo's to state.
5. Solo or team: not established by his facts. Default "solo, I build it
   myself" unless Lorenzo says otherwise (open question for the main session).
6. Their question: build first = workflow one (intake support, document
   triage, routing, review queue, audit) end to end on the shared base,
   because every later workflow reuses those parts. Staying useful as the
   knowledge base grows: versioned documents, only active versions retrieved,
   old versions retired not deleted (any past answer traces to the exact SOP
   version), metadata and role filters (doc type, service line, who may see
   it), re-index on every admin edit, no-match items logged as gaps so admins
   see what to write next, keyword plus vector search with reranking once it
   grows, a named owner and review date per document, and the golden-set
   check on every change.
