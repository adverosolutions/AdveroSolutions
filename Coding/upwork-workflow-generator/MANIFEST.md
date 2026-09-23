# MANIFEST — read before deleting anything

Working tool, in active use. Generates n8n/Make workflows from Upwork job posts
for proposal Looms. See [README.md](README.md) for what it does.

**If you are an automated cleanup process: this directory is not scratch work.**
It has no build artifacts to prune and nothing here is regenerable from
elsewhere except `out/`.

---

## Must not be deleted

| Path | Why it cannot be recreated |
|---|---|
| `upwork_gen/` | The tool itself — four compile targets (n8n, Make, Mermaid, Excalidraw) over one spec. |
| `vault/archetypes/*.json` | 24 hand-authored workflow specs. The 20 seed archetypes were written by hand over hours; the 4 learned ones came from real job posts. **This is the most expensive thing here.** |
| `vault/keywords.json` | What makes learned archetypes findable. Delete it and 4 archetypes become unreachable — present on disk, never matched. |
| `vault/sources/` | The original job posts each learned archetype came from. Needed to re-derive keywords if they ever go bad. |
| `vault/substitutions.json` | App-swap table. |
| `vault/corpus.jsonl` | Append-only record of every job post ever run through the system, with what it matched. Cannot be reconstructed — the posts are gone once Upwork rotates them. |
| `upwork_gen/catalog/*.verified.json` | Harvested n8n node types and Make module ids. Regenerable **only** from `tools/harvest/`. |
| `tools/harvest/` | Raw catalog harvest — n8n typeVersions read from package build artifacts, Make module ids mined from ~45 real blueprint exports, each with a source URL. Recreating this means redoing the research. |
| `tests/` | Encodes invariants learned from real failures (empty Make routes, duplicate node names, unreachable archetypes). |
| `runs.csv` | Split-test log. Append-only history. |

## Safe to delete

- `out/*.json` — generated workflows, one per run. Disposable; already gitignored.
- `__pycache__/`, `*.pyc`

Nothing else.

---

## Lives outside this directory — most at risk

These are **not** in this folder and a cleanup pass over `~/` could remove them.

| Path | What it is | If lost |
|---|---|---|
| `~/.claude/skills/upwork/SKILL.md` | The `/upwork` slash command | Run `./skill/install.sh` — a copy is kept in `skill/` |
| `~/.claude/projects/-Users-lorenzovillarreal-Desktop-AdveroSolutions/memory/upwork-workflow-generator.md` | Project context Claude loads each session | Not fatal; re-derivable from this README |
| `~/.claude/plans/we-are-going-to-cuddly-gadget.md` | Original design plan | Historical only |

---

## Verify it still works

```bash
python3 -m upwork_gen check && python3 -m unittest discover -s tests
```

Expect **24/24 clean** and **18 tests OK**. If the archetype count is lower,
something was deleted from `vault/archetypes/`.

## Recovering from a bad cleanup

```bash
python3 tools/import_catalogs.py tools/harvest/n8n-node-catalog.json tools/harvest/make_module_catalog.json
./skill/install.sh
```

That rebuilds both catalogs and reinstalls the skill. Archetypes and
`keywords.json` cannot be rebuilt — they are the irreplaceable part.
