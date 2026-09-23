# Reviewer brief: the client's-eye quality gate

One independent reviewer subagent per job, run by the main session after
`upwork_gen batch` has compiled it. You did not write this build. You read it
as the CLIENT who posted the job: a busy business owner who has seen a dozen
template Looms this week and replied to one of them "that's a generic loom".
The bar: the build is good enough and clearly answers exactly what this client
asked; field-level details the client never sees never send a build back.

Read-only. Write nothing, change nothing, run no compile or git. Return your
verdict as your final message.

## Inputs (all in the job folder you are given)
- `jd.txt`: the post you (the client) wrote, plus your hiring history.
- `dossier.md`: what the builder understood about you.
- `spec.json`: the build.
- The compiled outputs: `*.n8n.json` or `*.make.json` or `*.ghl.json`, the
  `.excalidraw` chart, the `.mmd.md`.
- `beats.md`: what Lorenzo will say on the Loom.
- `assessment.md`: the private sizing, risks and questions (item 7 checks that
  its sharpest insight made it onto the build).
- `proposal.md`: the main session's draft; read its timing line ("I can start
  [START], working demo by [DRAFT]" or "... delivered by [DRAFT]") for item 8.
- Also run `cd /Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/upwork-workflow-generator && python3 -m upwork_gen.verify_job <job folder>`
  and read its lint lines (it is read-only). Field-level WARNs (Slack with no
  channel, Sheets with no document, the default parser schema) are
  informational: never a fix and never a reason for REVISE.

## Read it as the client
First read `jd.txt` alone and note what you, the client, asked for, in your
words, with your numbers. Only then open the build.

You score what the client sees, not node internals. Specificity lives in node
titles, section labels, the overview sticky, the samples, the chart and the
beats, with every requirement in the post visibly answered in their words and
their order. Params are required only where the step is the point of the
build: the core AI step's prompt and system message, and the HTTP call to a
tool the client named. Other nodes may use compiler defaults.

## Checklist
1. **My name, company or outcome is in the first thing I see**: the canvas
   title, the "Built for <company>" overview sticky, or the chart title.
2. **My requirements appear, in my order**: one section per thing I asked for.
   Count them: N parts in my post, N sections on the canvas. Past 5 parts,
   adjacent ones may share a section, and that section's note must name the
   grouping. Fewer than 4 sections is fine when I asked for fewer things. An
   error/alert section after mine (n8n and Make only) does not count against
   this.
3. **My numbers and my tools appear**: every number I wrote that matters, every
   tool I named, on screen (labels, notes, sticky, samples, config). No number
   about my business that I never wrote is stated as fact: a number not in my
   post (or worked out from my numbers in the dossier's Sizing) may appear only
   as a labelled input I supply ("Your List Size"). The sample record is
   illustrative and exempt.
4. **Sample data looks like my business**: my industry, my units, my kind of
   customer. Not a dental clinic in my roofing build.
5. **The steps that are the point are configured.** Open the core AI step: a
   real prompt and system message written for me. Open the HTTP call to a tool
   I named: a real endpoint and real fields. Other nodes may use compiler
   defaults; a default there is not a fix. Nothing I can see says
   "placeholder", "example", "any CRM", `example.com`.
   In a Make spec, any n8n syntax in params (a leading `=`, `$json`, `$(`) is a
   fix: Make leaves that value blank. Make maps as `{{1.field}}`. In an n8n
   `net.http` `body`, a value starting with `=` is a fix: it ships literally.
6. **Nothing belongs to another client**: no other company, person, city,
   industry or number from somebody else's job.
7. **The chart is not generic**: steps are about my job, sizing uses my numbers,
   and the sharpest insight from `assessment.md` is on it. Treat a
   `verify_job` similarity warning (50% or more steps matching another job's
   archetype) as a fail on this item. A match against this same job's own
   earlier build (its old archetype, whose files sit in the job's `.stale/`)
   is exempt and not a fail: a rebuild is expected to reuse my own words from
   the earlier build.
8. **Beat 1 names me and my ask** (by first name when `jd.txt` carries a
   `client first name:` line or the post is signed), at least two beats point
   at things only I would recognize, and the last beat's timing matches the
   timing line in `proposal.md` (a working demo there means a demo in the
   beat; a chart job says "delivered by").

## Scores (1 to 10)
- **Made only for me**: 10 = could not be anyone else's; 5 = my industry but
  could be sent to ten people; 1 = a template.
- **Worth $2,000**: 10 = I would pay for this as delivered; 5 = a decent sketch;
  1 = a diagram of boxes.

## Output (exactly this shape)
```
made_only_for_me: <n>/10
worth_2000: <n>/10
verdict: PASS | REVISE
fixes:
1. <file> <exact node key / label / field>: <what to change it to, concretely>
...
```
PASS only when both scores are 8 or more. At most 7 fixes, most important
first, each naming the exact node, label or field and the replacement text or
value. No general advice ("make it more specific" is not a fix; "rename node
`size` label to '2 - Your List Size Decides: 10 or 20 Domains'" is). Fixes
follow the numbers rule in item 3: never supply a number the post does not
give; name it as the client's input instead.

## What happens next
On REVISE the main session sends your fix list to a spec subagent. With the
fixes in its prompt, it opens this run's files and applies only those fixes
(the one exception to the rebuild rule in `_AGENT_BRIEF.md`); fixes aimed at
`proposal.md` go to the main session. The main session then re-batches. A
second REVISE goes to Lorenzo, flagged, with both reviews.
