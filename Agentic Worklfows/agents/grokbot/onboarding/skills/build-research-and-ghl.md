---
name: build-research-and-ghl
description: "Reference for build props. How to find and trust real Make.com module ids (Sourcegraph, Make forum exports, the three-way authenticity test), and the GoHighLevel facts learned in Lorenzo's own sub-account (import lane, what the API can and cannot create, verified step shapes, browser traps). Use when a Make or GHL build needs a module id or step shape that isn't verified, when a GHL import lands half-built, or when a GHL API call fails with 401 or 403."
---

# Build research and GHL facts

## Current process, reconciled 2026-11-04

Read [process authority](../../../../../ClaudeConfig/PROCESS_AUTHORITY.md) before operational work. This dated update supersedes conflicting rules below; the remaining details are retained only where consistent. Source snapshots are process evidence, not live-action approval.

- The existing module-authenticity and GHL research procedure remains a technical reference; it is not evidence that a connector, import lane or account capability is still live.
- For current Upwork demo work, use the maintained local handbook and DIRECTIVES.md first. For a live GHL build, re-read the current account shape using available tools and keep live-write approval and dry-run rules. No live GHL changes are authorized by this maintenance task.

Current sources:

- [LEAN_ORG.md](../../../../../ClaudeConfig/grok-source/2026-11-04/first-export/advero/state/org/LEAN_ORG.md)


The `upwork` skill already covers when each prop type is used (n8n, Make, GHL,
chart), the 10-to-15-node target, charts that read like sentences, and the GHL
chart-by-default rule. The `mockup` skill covers the Zapier and GHL builder
mockups. This skill holds the research method and the platform facts behind
them.

- **Charts on a vague post:** when the post is vague, the chart steps are the
  automations Lorenzo would really put in for that kind of business, not
  guesses about the client's current setup.

## Make.com: trusting a module id

Make rejects an import that uses a wrong module id. Hand-written and
LLM-written "blueprints" are common online and carry ids that look right but
aren't:

| looks right | real |
| --- | --- |
| `slack:createMessage` | `slack:CreateMessage` (case matters) |
| `gmail:sendEmail` | Gmail's namespace is `google-email` |
| `whatsapp-business:sendTextMessage` | namespace `whatsapp-business-cloud` |
| `openai:CreateChatCompletion` | namespace `openai-gpt-3` |
| `builtin:BasicScheduler` | made up; does not exist |

**Accept an id only if one of these holds:**
1. It is in the official `integromat/make-skills` repo.
2. It appears in blueprints from 2 or more independent repositories.
3. It comes from a single file that carries exporter bookkeeping
   (`__IMTCONN__` connection ids, `metadata.restore`, or the
   `metadata.parameters` field-spec dump) and has no `REPLACE_WITH`-style
   placeholders.

That test rejected 28 of 586 harvested ids. The verified catalog has 556
entries.

**Where to search:**
- **Sourcegraph's public streaming API** needs no auth:
  `https://sourcegraph.com/.api/search/stream?q=<urlencoded>&v=V3&t=literal`.
  Parse the `event: matches` lines. Results come as commit-pinned paths,
  which turn into stable `raw.githubusercontent.com` URLs to cite. It
  supports `(a AND b)` and `lang:JSON`.
- **Make community forum attachments**
  (`community.make.com/uploads/short-url/*.json`) are real user exports and
  the richest source. They're the only place Shopify, Stripe, Pinecone,
  Postgres, Twilio and WordPress modules show up at all. Sourcegraph doesn't
  index them, so find them through forum-thread search.
- `raw.githubusercontent.com` has no rate cap.
- Dead ends:
  - GitHub code search needs sign-in, and the unauthenticated API is rate
    limited to 0.
  - `grep.app` is gated.
  - Make's own template API needs a login.

**Make structure facts, from real exports:**
- A router (`builtin:BasicRouter`) is a normal module with an extra `routes`
  array. Each route holds its own `flow`.
- A route's condition is normally a `filter` on the first module inside that
  route, not on the route itself. A route with no filter always runs.
- More than one router route can run for the same bundle. With
  `builtin:BasicIfElse`, only the first matching branch runs.
- Module ids are unique across the whole scenario, not per route.

## GoHighLevel: facts from his own sub-account

**The import lane (since 2026-09-22):**
- GHL's public API and its official MCP cannot create workflows. The spec is
  compiled to import JSON, and Lorenzo loads it with the "GHL Workflow Backup
  & Audit" Chrome extension into an empty workflow in his own sub-account
  ("AdveroSolutions"), never a client's. The extension is free for 5 imports,
  then $19.99 one-time.
- Leave the workflow in Draft. Never Publish or Test it: a published copy with
  SMS, email, call or review steps on live tags would message real contacts.
- Extension popups and file pickers need Lorenzo's own click. The import is
  his step.
- Build one short workflow per trigger event (booked, cancelled), not one long
  flow with a long wait and a goal. He found the single long flow hard to
  follow.
- Never use or change his real "Sales" pipeline. Name each demo pipeline after
  the client.
- If an imported step is wrong, fix the spec or the compiler and re-import
  into a fresh empty workflow. Never hand-edit a step on camera.

**Only a real export is a trustworthy format.** Public reverse-engineered repos
disagree with each other. The first import (12 of 12 steps) left the trigger
tag filter, the tag goal and the add-task step half-built, because those shapes
were guessed. A hand-checked export (2026-09-23) settled these:
- The AI step is type `chatgpt` with `event` "simple-prompt", `promptText`,
  `model` "gpt-5-mini" and `temperature` "0.2" as a string. A step named
  `gpt_powered` did not survive import.
- A review request is type `review_request` with
  `overrideReviewLink: "default"` and `review_type: "sms"`.
- A task needs `dueDate`, `assignedTo` ("contact.assigned_user"),
  `workflowsActionType` INTERNAL and `stepIndex`, or it imports with no icon.

Still unverified: every trigger except the tag and form triggers (for example,
whether the appointment trigger is `appointment` or `appointment_status`), and
some condition bodies. Check those steps for orange dots before recording.

**Stop-on-reply pattern** (reply is not a goal type):
- The main workflow ends with a goal that fires on a "<x>-replied" tag and
  otherwise ends. The no-response steps go before the goal, the reply steps
  after it.
- A companion workflow (customer replied, contact tag includes "<x>-sent",
  add "<x>-replied") makes the goal fire.

**API facts (REST, first live use 2026-09-22/23):**
- `services.leadconnectorhq.com` sits behind Cloudflare. It answers Python's
  default User-Agent with HTTP 403 "Error 1010". Any named User-Agent gets 200.
- A Private Integration token with 8 scopes (tags, custom fields, custom
  values and opportunities, read and write each) creates tags, contact fields
  and custom values. `POST /opportunities/pipelines` answers 401 "not
  authorized for this scope", and opportunities.write isn't enough for it.
  Until a scope that covers pipelines is found, Lorenzo makes pipelines by
  hand in the GHL UI and a dry run refreshes the id map.
- The first create on a new account or a new token waits for Lorenzo to see
  the dry-run output and say go. Creates never delete or modify anything.

**Browser traps on the workflow canvas:**
- Never type on the canvas without a focused field. Keystrokes fire builder
  shortcuts: `n` opens Notes, and on 2026-09-21 a typed prompt renamed the
  workflow and created a dozen empty drafts.
- The workflow area is a cross-origin iframe, so DOM tools can't see into
  it. Use coordinates only, and screenshot again after any resize.
- After "Save action", the canvas often stops taking clicks until the page is
  reloaded.
- Build Using AI (the fallback lane only): use the dropdown item, since the
  standalone button doesn't respond. Type one character first to confirm
  focus, and never press cmd+a on that page.
