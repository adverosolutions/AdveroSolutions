# Spintax diagnosis — Instantly preview + send failures

**When:** 2026-10-02 ~07:50 CT  
**Scope:** diagnose + propose only. No live PATCH. No user message.  
**Dry-run sample:** `/workspace/instantly_spintax_diag/dryrun_cleaning_trigger_step1_fixed.html`

---

## Root cause (1–2 sentences)

Every live campaign was given classic single-brace spintax `{option A|option B}`, but Instantly only resolves **`{{RANDOM | option1 | option2}}`** (double braces + required `RANDOM` keyword). Instantly treats `{a|b}` as plain text, so previews and actual sends both show the literal braces and pipes.

The wrong format was baked into the 2026-09-29 brief (`20260929_spintax_brief_copywriter.md` line: `Format: {option A|option B|option C}`), then into drafts, then into the apply that landed on all six cold campaigns (and later AI Agents copies).

---

## Preview vs send

**Same failure on both.** This is not a preview-only / resolve-on-send quirk.

- Live campaign bodies still contain `{a|b}` with **zero** `{{RANDOM ...}}` blocks.
- Sent emails from this morning (2026-10-02 ~07:33–07:41 CT) still contain the literal spin strings after personalization filled (e.g. `{Hey|Hi} Darrell,` and `{Know this is out of left field|This is a bit out of left field}`).

Official Instantly help: https://help.instantly.ai/en/articles/6384663-how-to-use-spintax  
Troubleshooting there: check `{{RANDOM | option1 | option2}}` and verify curly braces `{{ }}`. No separate “enable spintax” campaign toggle found — syntax is the switch.

---

## Exact broken pattern in live HTML

Not an HTML-wrap / split-across-`<div>` / entity-encoding bug. Each `{a|b}` sits intact inside a single `<div>`. Braces are literal `{` / `}`, not `&#123;`. Variables like `{{firstName}}` are fine and adjacent to broken spins.

### Evidence snippets

**1. cleaning_reactivation step1 (live API `8086b41e-…`):**
```html
<div>{Know this is out of left field|This is a bit out of left field}, if I could help recover the money from accounts that cancelled or stopped renewing their contracts in exchange for a commission on the accounts I bring back, {would you be open|are you open}? I work mostly on performance and am building my network.</div>
```

**2. cleaning_trigger step1 (live `f347604e-…`):**
```html
<div>{If this interests you|If this is of interest}, {let's hop on|happy to jump on} a short 15 minute call. Just reply {Yes|yes} and I can {shoot you over|send} a calendar invite.</div>
```

**3. recruiting_reactivation / step2 greeting pattern (shared across niches):**
```html
<div>{Hey|Hi} {{firstName}},</div>
```

**4. Sent email body (GET /emails, campaign cleaning_reactivation, 2026-10-02T12:40:24Z / ~07:40 CT) — spin NOT resolved on send:**
```html
<div>{Hey|Hi} Darrell,</div><div><br /></div><div>{Checking in|Bumping this|Circling back}, in case the first one {got buried|got lost|slipped by}. {Quick version|Short version}:</div>
```

Counts from live GET `/api/v2/campaigns/{id}`: every cold campaign has `single_brace_spins > 0` and `RANDOM_blocks = 0`. HTML-encoded braces = 0. No spins split across tags.

---

## Instantly-correct format

```
{{RANDOM | option1 | option2 | option3}}
```

Examples from Instantly Help Center:

- `{{RANDOM | Hi | Hey | Hello}} {{firstName}},`
- `{{RANDOM | Thanks | Regards | Cheers,}}`

Notes:
- Double curly braces required.
- Leading `RANDOM` keyword required (without it Instantly may treat `{{first|second}}` as a variable/fallback, not a random spin).
- Spaces around `|` are what Instantly documents; match that.
- Variables may nest inside options: `{{RANDOM | Hi {{firstName}} | Hello there}}`.
- Fallback (different feature): `{{firstName | there}}` — do not confuse with spin.

**Wrong (what we applied):** `{Hey|Hi}`  
**Right:** `{{RANDOM | Hey | Hi}}`

---

## Subjects: Instantly A/B vs fake spintax

Subjects are **not** using fake `{a|b}` spintax.

- cleaning_reactivation step1: Instantly native **two variants** — subjects `{{firstName}}, question` and `cancelled accounts` (same broken body on both).
- cleaning_trigger step1: variants `{{firstName}}, question` and `walkthroughs`.
- recruiting_reactivation: single subject `{{firstName}}, question`.

Backup dir `instantly_campaigns_20260929_subject_ab/` holds post-spintax / pre–subject-A/B snapshots (1 variant each, bodies already had `{a|b}`). Subject A/B was applied later as real Instantly variants — leave that alone; only rewrite body spins.

---

## Campaigns affected

### Six cold campaigns (2026-09-29 spintax apply — all `ok` in apply log)

| Key | ID | Live status* | Broken spins |
|---|---|---|---|
| cleaning_trigger | `f347604e-48c7-4813-831c-dc7b9d4b50ae` | 2 | step1×2 variants + step2 |
| cleaning_reactivation | `8086b41e-b546-4b36-9fa0-2d01f5cc119a` | 2 | step1×2 variants + step2 |
| recruiting_reactivation | `1d4d5bb3-40a7-4333-bf34-b269d2cc9955` | 2 | step1 + step2 |
| bookkeeping_reactivation | `f00c5e28-fdc4-4d84-a7e6-dfba9695f35d` | 2 | step1 + step2 |
| bookkeeping_trigger | `87ebb167-9b64-4b6f-b658-88f3d1af9980` | 2 | step1 + step2 |
| recruiting_outbound | `cd2e251c-3b5a-40d2-a3dc-d07c4004a48c` | 2 | step1 + step2 |

\*API `status` at diagnosis time: 2 (paused per workspace skill). Sent mail with literal spins still observed earlier the same morning before/around pause updates (~12:45Z).

### AI Agents campaigns (inherited same wrong `{a|b}` syntax)

All listed campaigns in workspace also show single-brace spins and zero `{{RANDOM}}`: Bookkeeping & tax, Service, MSP, Insurance brokers, Landscaping, Recruiting, Marketing agencies, Pest control AI Agents. Same rewrite rule applies if/when those are used.

---

## Recommended fix steps (ask Lorenzo before any live PATCH)

1. **Confirm pause** on any campaign still queuing sends until bodies are rewritten (literal `{a|b}` is already going to prospects).
2. **Rewrite rule (mechanical, meaning-preserving):** replace every `{opt1|opt2|…}` with `{{RANDOM | opt1 | opt2 | …}}`. Do **not** alter `{{firstName}}` / `{{companyName}}` / `{{personalization}}` / `{{specialty}}`. Do **not** change subject A/B variant structure.
3. **Backup** each campaign JSON before PATCH (same pattern as `instantly_campaigns_20260929_pre_spintax/`).
4. **Apply** via Instantly API `PATCH /campaigns/{id}` with full `sequences` (API replaces whole), HTML bodies kept as `<div>…</div>` wrappers — only the spin tokens change inside existing divs.
5. **Verify** in Instantly UI preview that spins resolve; spot-check one sent/test email for absence of literal `{`…`|`…`}`.
6. **Update source artifacts** so this does not recur: brief + drafts + any copywriter skill notes that say `{a|b}` → document Instantly `{{RANDOM | a | b}}`. Refresh Google Doc / `copy_doc_approved` after go-live.
7. **Optional dry-run already done** for cleaning_trigger step1 v0:  
   `/workspace/instantly_spintax_diag/dryrun_cleaning_trigger_step1_fixed.html`  
   Meta: `…/dryrun_cleaning_trigger_step1_meta.json` (5 spins → 5 `{{RANDOM}}`, 0 remaining single-brace).

### Example rewrite (cleaning_trigger CTA line)

Before:
```html
{If this interests you|If this is of interest}, {let's hop on|happy to jump on} a short 15 minute call. Just reply {Yes|yes} and I can {shoot you over|send} a calendar invite.
```

After:
```html
{{RANDOM | If this interests you | If this is of interest}}, {{RANDOM | let's hop on | happy to jump on}} a short 15 minute call. Just reply {{RANDOM | Yes | yes}} and I can {{RANDOM | shoot you over | send}} a calendar invite.
```

---

## What was ruled out

- Spins split across `<div>` tags — not present.
- HTML-encoded braces (`&#123;`) — not present.
- Nested wrong with `{{firstName}}` — variables OK; problem is spin token shape.
- Subject lines using fake spintax — subjects use Instantly A/B variants or plain `{{firstName}}, question`.
- Preview-only behavior — **sent** mail also keeps literals.

---

## Artifacts

| Path | What |
|---|---|
| `/home/box/advero/state/handoffs/20261002_spintax_diagnosis.md` | This file |
| `/workspace/instantly_spintax_diag/*.json` | Live campaign pulls + email sample |
| `/workspace/instantly_spintax_diag/dryrun_cleaning_trigger_step1_fixed.html` | Corrected sample body (not live) |
| Instantly docs | https://help.instantly.ai/en/articles/6384663-how-to-use-spintax |

---

## Fix applied (2026-10-02 ~07:58 CT)

Lorenzo approved live fix. Converted classic `{a|b}` → Instantly `{{RANDOM | a | b}}` on **all 14** workspace campaigns (6 cold + 8 AI Agents).

- Backup: `/home/box/advero/state/backups/instantly_spintax_random_fix_20261002/`
- Apply log: `/home/box/advero/state/handoffs/20261002_spintax_random_fix_log.md`
- All PATCH 200; verify leftover classic spins = 0 on every campaign; no restores.
- Subjects / variant structure / `email_list` / merge tags untouched.
- UI preview still recommended to confirm Instantly resolves `{{RANDOM}}` in the editor.
