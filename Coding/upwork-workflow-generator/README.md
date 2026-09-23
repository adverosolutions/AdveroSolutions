# Upwork Workflow Generator

> **Before deleting anything here, read [MANIFEST.md](MANIFEST.md).** The vault
> and the harvested catalogs are not regenerable.

Paste an Upwork job description, get back an importable n8n workflow or Make.com
blueprint — on the clipboard, in under a second — to walk through in a proposal
Loom.

The workflows are visual props. They do not execute and carry no credentials.
What they must do is **import cleanly on the first try**, **look senior-built**,
and **carry sample data on the first and last node** so the recording can say
"this is what goes in, this is what comes out."

## Use it

Through Claude Code, which is the intended path:

```
/upwork <paste the job description>
```

Or directly:

```bash
python3 -m upwork_gen vault jd.txt --job-ref "https://upwork.com/jobs/…"
```

Output lands in `out/` and on the clipboard. n8n accepts workflow JSON pasted
straight onto the canvas with Cmd+V, so there is no save-then-import step.

## How it works

Two engines, one compiler. Both are live so they can be split tested.

```
job description
      │
   classify.py ────────► platform · archetype · apps        ~2 ms, no model
      │
      ├── VAULT ───────► hand-verified archetype + app swaps    ~6 ms
      │
      └── COMPILER ────► Claude authors a WorkflowSpec          ~6 s
                │
                ▼
        validate → layout → compile
                │
        ┌───────┬────────┬────────────┐
     n8n JSON  Make bp  Mermaid  Excalidraw DSL
```

**Four targets, one spec.** The workflow and every diagram of it are compiled
from the same graph, so they cannot describe different things — which matters
when both appear in the same recording. Adding a fifth visual tool is a new
`compile_*.py`, not a new system.

The engines converge on one `WorkflowSpec`, so the comparison is fair and every
improvement to layout or the catalog benefits both.

**The LLM never writes platform JSON.** It writes a ~60-line spec drawn from a
closed vocabulary, and the compiler resolves that through a curated catalog. The
model cannot emit an invalid node type because it never names one.

**Nothing places nodes but the layout engine.** Columns come from longest-path
depth, sections get exclusive column bands, sticky notes are squared off into
uniform swimlanes, and AI sub-nodes dock beneath their agent. The canvas is tidy
on every generation rather than most of them.

**Unknown apps never fail.** An app with no catalog entry becomes an HTTP Request
node labelled with the app name, which reads as a deliberate custom-API call.

## Layout

| Path | What it is |
|---|---|
| `upwork_gen/spec.py` | `WorkflowSpec` — the contract both engines write to |
| `upwork_gen/classify.py` | Job post → platform, archetype, apps. No model. |
| `upwork_gen/layout.py` | Deterministic placement. Owns "looks well put together". |
| `upwork_gen/compile_n8n.py` | Spec → n8n JSON, incl. `pinData` and AI ports |
| `upwork_gen/compile_make.py` | Spec → Make blueprint, incl. router nesting |
| `upwork_gen/catalog/` | `(kind, app)` → real node types / module ids |
| `vault/archetypes/` | 24 specs — 20 hand-authored, 4 learned from real posts |
| `vault/sources/` | The job posts each learned archetype came from |
| `vault/corpus.jsonl` | Every run: the post, what matched, at what confidence |
| `upwork_gen/compile_flow.py` | Spec → Mermaid (pastes into GitHub, Notion, Artifacts) |
| `upwork_gen/compile_excalidraw.py` | Spec → Excalidraw DSL → `.excalidraw` via CLI |
| `runs.csv` | Split-test log |

## Commands

```bash
python3 -m upwork_gen classify jd.txt        # what the classifier sees
python3 -m upwork_gen next-engine jd.txt     # which split-test arm this job belongs to
python3 -m upwork_gen vault jd.txt           # engine A
python3 -m upwork_gen vault jd.txt --excalidraw   # also render the .excalidraw
python3 -m upwork_gen spec spec.json         # engine B
python3 -m upwork_gen check                  # compile every archetype, both platforms
python3 -m upwork_gen archetypes             # what the vault holds and has learned
python3 -m unittest discover -s tests        # invariants
```

## Getting it on screen

Both canvases accept a paste — n8n takes workflow JSON dropped on the canvas,
excalidraw.com takes a scene the same way. So every run opens both tabs and
leaves the workflow on the clipboard; the diagram is one command away.

```bash
python3 -m upwork_gen config --n8n-url https://your-instance/workflow/new --browser Arc
python3 -m upwork_gen vault jd.txt --excalidraw                # opens both tabs
#   Cmd+V into n8n
python3 -m upwork_gen clip flow                                # swap the clipboard
#   Cmd+V into excalidraw.com
```

Point `n8n_url` at a **blank canvas** (`/workflow/new`), not the workflow list —
there is nothing to paste onto on the list page. If the instance is on a
sleeping tier (Render free), a run pings it in the background as it starts, so
it is awake by the time the tab opens instead of cold-starting for 30-50s while
you watch.

`clip` takes `flow`, `n8n`, `make`, or `mermaid` and always acts on the most
recent run. `--no-open` suppresses the tabs for a single run;
`config --open-on-run off` turns it off for good.

Tabs are reused, not reopened — a run focuses the existing n8n and Excalidraw
tabs rather than adding another copy to a browser that already has 28 of them.

**The diagram and the workflow are identical, node for node.** Same labels,
nothing extra, nothing missing — they get narrated back to back in one
recording, so a step present in one and absent from the other is a
contradiction the viewer can see. A test asserts set equality across every
archetype.

Two consequences fall out of that. AI sub-nodes are drawn (they are on the n8n
canvas, so they are in the diagram). There is no synthetic "Done" terminal — a
node that exists only in the diagram is one the client can ask about and the
workflow cannot answer. And node labels are normalised at parse time, because
the DSL uses `( ) [ ] { }` as shape delimiters: fixing that in either compiler
alone would hide the divergence rather than remove it.

Diagrams render left-to-right. Note the CLI lays nodes out in a single chain
and does not spread branches, so a 15-node workflow is a long strip (~28:1)
rather than a 2-D graph. Acceptable for panning through on a recording; if the
decision structure needs to be visible, emit Excalidraw JSON directly from
`layout.py`, which already solves 2-D placement for the n8n canvas.

`upwork_gen/arc.py` can also paste the diagram into Excalidraw for you
(`paste_into_excalidraw`, clears the canvas first). It is deliberately not in
the run path: pasting is manual by choice. Wire it in if that changes — the
guard is already there, and it will not send keystrokes unless Arc confirms
Excalidraw is the focused tab.

Nothing else here drives the UI. Keyboard automation would save one keystroke and
introduce a failure mode that only shows up when a tab loads slowly — which is
mid-recording, the worst possible moment.

## The vault compounds

Every compiler run promotes its spec into the vault. A posting shape costs one
model turn the first time and 6 ms every time after — so coverage grows with
use rather than needing to be authored up front.

Promotion has two halves and both are mandatory:

1. The spec lands in `vault/archetypes/`.
2. Keywords mined from the job post land in `vault/keywords.json`, which
   `classify.py` merges at import.

Skipping the second half produces an archetype that exists but can never be
matched — coverage on paper, a gap in practice. A test enforces that every
learned entry has keywords.

Keywords come from the posting, not the spec, because the classifier reads
postings. The **application-instructions tail is stripped first** — mining
"To apply, please include examples… become a long-term partner" yields terms
that match half of Upwork. Terms already claimed by another archetype are
dropped too, so a new entry cannot quietly steal traffic from a hand-tuned one.
The 20 seed archetypes cannot be overwritten without `--force`.

```bash
python3 -m upwork_gen spec spec.json --jd jd.txt --archetype-id ai_ops_router
python3 -m upwork_gen archetypes                     # what it holds and has learned
python3 -m upwork_gen archetypes --forget ai_ops_router   # drop one that matches badly
```

## What happens automatically on every run

Nothing below is behind a flag. The value of a system that compounds is that it
does so whether or not anyone remembers to ask.

| | |
|---|---|
| **Corpus capture** | The job post is appended to `vault/corpus.jsonl` with what it matched and at what confidence. This is the only record of what the classifier actually sees, and the raw material for improving it. |
| **Source archiving** | The first post to produce an archetype is kept in `vault/sources/`, so its keywords can be re-derived if they go bad. Later posts that merely match it do not overwrite it. |
| **Self-check** | An integrity pass surfaces silent degradation — an archetype with no keywords is invisible to the classifier, and no normal run would reveal that. Problems print under `health:`. |
| **Auto-commit** | The vault and run log commit themselves. Scoped to `vault/` and `runs.csv` only: a generation never commits code, and never sweeps up unrelated repository edits. Disable per-run with `--no-commit`. |

A full read of the system's own state:

```bash
python3 -m upwork_gen doctor
```

Reports archetype counts, catalog verification status, corpus size, whether the
vault has uncommitted changes, and any integrity problems.

## Engine choice

**The compiler is the default.** A tailored spec written for the posting in hand
beats a retrieved archetype on any posting that names specifics, and most do.
The vault is for postings that are genuinely generic and match strongly
(confidence ≥ 12) — it is a cache, not the first choice.

A run prints WEAK MATCH under 8.0, but the threshold for *preferring* the vault
is higher than the threshold for it being allowed at all. When in doubt, tailor:
the cost is one model turn, and the cost of being wrong is a recording that
shows a client a workflow built for somebody else.

## Split test

`runs.csv` records every generation. Two columns carry the real signal and are
filled in by hand:

- **`loom_takes`** — does vault familiarity actually reduce re-records? This is
  the hypothesis worth testing, because take count moves minutes while
  generation latency moves seconds.
- **`replied`** — does compiler tailoring win more jobs?

`gen_ms` is logged for completeness, but at 6 ms versus 6 s inside a five-minute
budget it is noise, and it is expected to stay noise.

## Catalogs

Both catalogs are **verified**, not guessed.

- **n8n** — 42 node types with `typeVersion` read programmatically from each
  package's build artifacts (n8n 2.32.7), not transcribed from docs.
- **Make** — 94 module ids mined from real exported blueprints, every entry
  carrying the source URL it came from.

Sources live in `tools/harvest/`. To re-import after a fresh harvest:

```bash
python3 tools/import_catalogs.py tools/harvest/n8n-node-catalog.json tools/harvest/make_module_catalog.json
```

The harvest uses its own key scheme (`kind:vendor:operation`); `import_catalogs.py`
translates it into this project's `kind:app:op`. Each app is also registered
under `kind:app:` with no operation, so an op the harvest missed still resolves
to the right node type rather than degrading to a generic HTTP request.

Apps with no Make module in the corpus — Postgres, HubSpot, Stripe, Twilio,
Shopify — fall back to a labelled HTTP call. That is accurate: Make genuinely
has no first-party module for several of them.

## Confirmed against a live canvas (2026-07-31)

- **`pinData` survives a clipboard paste.** Pasted workflows show pinned data on
  the first and last node with the pin badge intact, so the clipboard path holds
  and there is no need to import from file.
- **Sticky colours:** `3`=red, `4`=green, `5`=blue, `6`=purple, `7`=grey. Red is
  deliberately out of the rotation — it reads as an error state on a section that
  is only doing work. `1` and `2` remain unidentified.
- **n8n renders two node widths**, not one: ordinary nodes are ~100px, agent and
  chain nodes ~200px. `layout.py` sizes per kind; assuming one width made wide
  nodes overflow their section band and crowd the next column.

Still untested: nodes carry no credentials, so n8n shows a small warning triangle
on each. Whether that reads badly at recording zoom is unknown.
