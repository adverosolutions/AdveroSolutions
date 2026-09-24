# Section 3: Upwork follow-ups

## Goal
Every open Upwork proposal chat gets a timely, bespoke follow-up draft. Lorenzo reads and sends each one himself. The engine never writes to Upwork.

## Where it stands (2026-09-23)
- **Built and committed** (`services/upwork_followup/`, `jobs/upwork_followup.py`, design in `services/upwork_followup/DESIGN.md`, runbook `runbooks/upwork_followup.md`):
  - `collect.py` reads proposals and chats through the official Upwork MCP from a Claude scheduled task (read only; `collect_calls.md`, `scheduled_task_prompt.md`);
  - `classify.py` reads where each chat stands;
  - `sequence.py` sets the touch schedule (`prompts/touch_t1.md` to `touch_t7.md`, plus `reply.md` and `checkin.md`);
  - `draft.py` writes the drafts;
  - `ghl_sync.py` mirrors each chat to a GHL card. A card move in GHL always wins over `--stage`, and the morning file says when that happens.
- **The copy gate** (`copy_gate.py`) refuses a draft that:
  - offers an off-Upwork payment method (wire, check, cash, Zelle, PayPal and so on) outside payments jobs;
  - uses any figure from Lorenzo's private pricing notes (the model never sees those notes);
  - agrees to a price the client proposed, with the number ("Sure, 2,000 works") or without it ("Sure, that works" right after they name one).
- **Real test run on 2026-09-23:** reads only, drafts written to a file, about $0.20 of model spend, nothing sent. It caught the Sonnet "thinking" cut-off, since fixed for every model call. Its files are in `.tmp/upwork_followup/test_run_2026-09-23/` in the main folder. That folder holds real client data: subagents never read `.tmp/upwork_followup/`.
- **Open chats at the last run:** three. Two are blocked on Upwork's side. One has been quiet since Lorenzo's quote on 09-22; its first follow-up was due 09-24.
- **Known limits of the price guard** (a backstop, since Lorenzo sends every draft himself):
  - it misses agreement phrased as a question ("The price works, right?");
  - it misses agreement with words in between ("The price for the build works");
  - it misses agreement to a monthly rate ("2,000 a month works out fine", `_RATE_AGREED_RE`);
  - it doesn't read spelled-out prices or hours ("twenty-five hundred", "a six-hour build");
  - a few safe-side refusals cost one retry.
- **`jobs/upwork_rooms.py`** is a separate read-only check of Upwork message rooms (`runbooks/upwork_rooms.md`).

## Next steps, in order
1. **Ask Lorenzo whether to walk through the Upwork follow-up touches** (T1 to T7 and their timing) the way section 1 is doing email: show each touch prompt and a sample draft, and take his edits. He listed "the Upwork reply sequence" as its own section.
2. **His "say yes" items:**
   - the 08:30 CT Claude scheduled task for the daily run (`scheduled_task_prompt.md`);
   - the GHL Upwork pipeline, which he creates himself (its ids go in `config/ids.json` under `pipelines.upwork`);
   - the Upwork pricing lines in `config/upwork_offers.md`.
3. **Optional:** close the monthly-rate gap in `copy_gate.py`, only if Lorenzo wants it. The earlier price-guard rounds were long.
4. **Real runs** read live Upwork data, so they happen in the main folder (where `.env` and `.tmp/` live) after merging to main and running `git pull` there. They need Lorenzo's OK for the model spend.

## Hard rules for this section
- Never call Upwork write tools: `send_message`, `manage_proposals`, `respond_to_offer`, `manage_meetings`, `submit_milestones`, `boost_profile`, `manage_offers`, `update_profile`.
- The Upwork proposal and application flow (`Coding/upwork-pipeline/`, the `/upwork` skill) is not part of this section.
- No real client names in committed docs or tests.

## What this section owns (paths under `Agentic Worklfows/`)
- `services/upwork_followup/**` (including its tests), `jobs/upwork_followup.py`, `jobs/upwork_rooms.py`, `jobs/tests/test_upwork_rooms.py`
- `config/upwork_offers.md`, and the `pipelines.upwork` key in `config/ids.json` (only that key)
- `runbooks/upwork_followup.md`, `runbooks/upwork_rooms.md`
- `sections/3_upwork/**`

Uses but does not own: `shared/llm.py`, `shared/ghl.py` and the rest of `shared/` (section 4).
