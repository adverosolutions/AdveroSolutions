---
name: make-blueprint-research-method
description: How to find real Make.com blueprint exports for verifying module identifiers (GitHub code search is blocked; use Sourcegraph + Make forum attachments)
metadata: 
  node_type: memory
  type: reference
  originSessionId: 48768ada-c4a2-4ebd-bf89-c575caa04150
  modified: 2026-08-01T01:44:37.790Z
---

Finding real Make.com blueprint JSON exports to verify module ids (`slack:CreateMessage` etc.):

- **GitHub code search is unusable unauthenticated** — the HTML page demands sign-in and `api.github.com` core is rate-limited to 0 without a token. `gh` CLI is not installed on this machine.
- **Sourcegraph's public streaming API works with no auth** and is the best code-search substitute:
  `https://sourcegraph.com/.api/search/stream?q=<urlencoded>&v=V3&t=literal` — parse `event: matches` SSE lines. It returns commit-pinned paths, which convert to stable `raw.githubusercontent.com` citation URLs. Supports boolean `(a AND b)` and `lang:JSON`.
- **The richest source by far is community.make.com forum attachments** (`community.make.com/uploads/short-url/*.json`) — real user scenario exports, and the only place several apps (Shopify, Stripe, Pinecone, Postgres, Twilio, WordPress) appear at all. Sourcegraph does not index them; find them via forum-thread search.
- `raw.githubusercontent.com` is uncapped; `grep.app` is Vercel-gated; Make's own template API requires login.

**Authenticity matters — hand-written/LLM "blueprints" are common on GitHub and carry plausible-but-wrong ids** (`slack:createMessage` wrong case, `gmail:sendEmail` — Gmail is really `google-email`, `whatsapp-business:*` — really `whatsapp-business-cloud`, a fabricated `builtin:BasicScheduler`). Test that worked: accept an id only if it is in the official `integromat/make-skills` repo, OR appears in 2+ independent repos, OR comes from a file carrying exporter bookkeeping (`__IMTCONN__`, `metadata.restore`, `metadata.parameters` field-spec dump) with no `REPLACE_WITH`-style placeholders. That rejected 28 of 586 harvested ids.

Output of this work lives in the repo: `Coding/make_module_catalog.json` (556 entries), `make_blueprint_structures.md`, `make_catalog_report.json`.
