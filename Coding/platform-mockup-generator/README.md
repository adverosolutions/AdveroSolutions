# Platform Mockup Generator

Renders an automation as a page that looks like the **GoHighLevel workflow
builder** or the **Zapier editor**, for use as a visual prop in a proposal Loom.

## Why this exists

Neither platform has a public import format. There is no file to hand a client
and no canvas to paste into, so the artifact that works for n8n and Make.com —
an importable JSON workflow — has no equivalent here. A page that reads as the
builder gets the same beat in the recording.

This is **separate from the n8n/Make generator** by design. Different output,
different model of an automation (a card stack, not a graph), no shared code.

## Use

```bash
python3 -m mockup build specs/example_speed_to_lead.json --both
python3 -m pytest tests/ -q
```

`build` writes `out/<slug>.<platform>.html` and opens it. Flags: `--platform
ghl|zapier`, `--both`, `--no-open`, `--browser Arc`, `--out DIR`.

## Design constraints

- **Self-contained output.** No external stylesheet, font, script or image — a
  request that fails would repaint the page mid-recording. Enforced by a test.
- **No logos.** App tiles are initials on a colour derived from the app name,
  which avoids trademark use and keeps the file offline. Colour assignment is
  deterministic across processes, so an app looks the same in every recording.
- **Honest framing.** The page is a mockup of a build, not a running account.
  The skill says so, and the pitch is stronger for it.

## Layout

| File | Role |
|---|---|
| `mockup/spec.py` | The contract — a nested step list with a closed `type` vocabulary |
| `mockup/theme.py` | Per-platform palette and chrome; app tile colours |
| `mockup/render.py` | Spec → one self-contained HTML page |
| `mockup/cli.py` | `build` subcommand |
| `specs/` | Hand-authored specs |

The `/mockup` skill at `~/.claude/skills/mockup/SKILL.md` is the entry point.
