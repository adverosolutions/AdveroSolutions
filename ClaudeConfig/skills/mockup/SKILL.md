---
name: mockup
description: "Render a GoHighLevel or Zapier builder mockup from a pasted job description, as a visual prop for a proposal Loom. Use when a post asks for GoHighLevel/GHL or Zapier automation, or when the user invokes /mockup."
---

# GoHighLevel / Zapier Builder Mockup

## Current process, reconciled 2026-11-04

Read [process authority](../../PROCESS_AUTHORITY.md) before operational work. This dated update supersedes conflicting rules below; the remaining details are retained only where consistent. Source snapshots are process evidence, not live-action approval.

- For a current Upwork job, read the maintained master handoff and DIRECTIVES.md before choosing a prop. Premium job-specific animated demos are the current general path; this historical builder-mockup format applies when Lorenzo requests that format or the job-specific brief calls for it.
- Preserve job facts, native tool shapes and the no-invented-proof rule. Do not publicly publish or claim a mockup is a tested live automation.

Current sources:

- [LEAN_ORG.md](../../grok-source/2026-11-04/first-export/advero/state/org/LEAN_ORG.md)


> **Retired 2026-09-09.** GHL and Zapier posts now use the native Excalidraw flowchart from `/upwork` (load with `job <name> flow`). Lorenzo rejected the builder mockup on camera; do not use this path unless he asks for it by name.

Neither GoHighLevel nor Zapier has a public import format, so there is no file
to hand a client and nothing to paste into a canvas. This renders the
automation as a page that **looks like the builder itself** — the same beat in
the Loom, reached a different way.

Project root: `/Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/platform-mockup-generator`

This is a **separate tool** from `/upwork`. For n8n or Make.com postings, use
`/upwork` — it produces a real importable workflow, which is strictly better
when the platform allows one.

**Speed is the metric.** Do not narrate, do not summarize the post back, do not
ask which platform unless the post genuinely names neither. Author the spec, run
the build, report one line.

## Procedure

Write the spec straight to `/tmp/mockup.json`, then:

```bash
cd /Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/platform-mockup-generator && python3 -m mockup build /tmp/mockup.json
```

It writes `out/<slug>.<platform>.html` and opens it in a browser tab. Add
`--both` to render GoHighLevel and Zapier from the one spec, `--no-open` to skip
the tab, `--platform ghl|zapier` to override, `--browser Arc` to pick the app.

**Pick the platform from the post**, and only fall back to `ghl` when neither is
named — GoHighLevel postings outnumber Zapier ones heavily in this niche.

## Authoring a spec

A vertical list of steps that may split once. This is not the n8n graph model
and does not need to be — these builders have no free-form canvas.

```json
{
  "title": "Speed to Lead — Inbound Qualification",
  "platform": "ghl",
  "account": "Client Business Name",
  "trigger": { "app": "Facebook Lead Ads", "label": "New Lead Form Submission",
               "note": "Fires the moment a lead submits, day or night." },
  "steps": [
    { "type": "action", "app": "GoHighLevel", "label": "Create or Update Contact",
      "note": "Matches on phone first, then email." },
    { "type": "ai", "app": "Claude", "label": "Score Intent & Draft Reply" },
    { "type": "branch", "label": "Intent score is 70 or higher",
      "branch_labels": ["Qualified", "Nurture"],
      "yes": [ { "type": "action", "app": "Twilio", "label": "Send SMS Within 60 Seconds" } ],
      "no":  [ { "type": "wait", "label": "Wait 2 Hours" } ] }
  ],
  "input_sample":  { "…": "renders inside the trigger card" },
  "output_sample": { "…": "renders inside the last card" }
}
```

**`type` — closed set:** `action` `ai` `branch` `wait` `filter` `code`

**Rules that matter:**

- **`action` and `ai` must name an `app`.** The coloured app tile is what makes
  a card read as a product card instead of a box. `wait` / `filter` / `code`
  draw a native glyph and take no app.
- **`account`** puts the client's business name in the top bar. Always set it —
  it is the single cheapest signal that the build is theirs and not a template.
- **One branch, and put it late.** Both builders split at most once legibly, and
  a split near the top pushes everything below into two narrow columns.
- **`branch_labels`** should be domain words ("Qualified" / "Nurture"), not
  "Yes" / "No".
- **`note`** is the grey line under a card title. Two or three cards with notes
  reads as considered; a note on every card reads as filler.
- **Sample data is the pitch.** `input_sample` renders in the trigger card and
  `output_sample` in the visually last card. Make the output show work having
  been done — scores, ids, timings, an assignee — not an echo of the input.

Aim for **6–12 cards**. The tool warns below 4 and above 16.

## On camera

Say what it is. *"Here's the build laid out the way it'll look in your
GoHighLevel"* is accurate and normal for a proposal. Do not imply it is already
running in their account — the page is a mockup, and the pitch is stronger for
being straight about it: there is no import format for these platforms, so the
alternative was a wireframe.

No logos are used; app tiles are drawn from initials on a generated colour.

## Checks

```bash
python3 -m pytest tests/ -q
```
