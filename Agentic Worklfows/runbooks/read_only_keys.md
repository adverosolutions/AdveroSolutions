# Read-only keys for agent sessions (decision R2(a))

Goal: a Claude session on this laptop only ever holds keys that can read. The keys that can send, book, pause or move anything live in two places only: the Modal secret, and `~/.advero/live.env` on this laptop.

`shared.settings.guard_write` is still the real protection. This change only limits what a leaked or misused key can do.

How the code picks a key (`shared/keys.py`):

| System | Read calls use | Write calls use |
|---|---|---|
| Instantly | `INSTANTLY_API_KEY_READ`, or `INSTANTLY_API_KEY` if that is unset | `INSTANTLY_API_KEY` only |
| GHL | `GHL_PRIVATE_INTEGRATION_TOKEN_READ`, or `GHL_PRIVATE_INTEGRATION_TOKEN` if that is unset | `GHL_PRIVATE_INTEGRATION_TOKEN` only |

The code decides read or write per method, not by HTTP verb, so `POST /leads/list` and `POST /contacts/search` count as reads. Nothing breaks before you do the steps below. Until the `_READ` keys exist, each shadow process logs one warning per system: "reads are using the write-capable ...".

## 1. Create the Instantly read key

Instantly > Settings > Integrations > API Keys > Create. Give it the scope **`all:read`**.

Use `all:read` rather than a list of narrow scopes. Only three scopes are verified: `GET /emails` needs `emails:read`, `POST /leads/list` needs `leads:read`, and a reply needs `emails:create`. The reference names no scope for the other reads, including `GET /campaigns/analytics`, and some endpoints accept only `all:*` scopes. The full table is in `config/instantly_api_contract.md` under "API-key scopes per endpoint".

## 2. Create the GHL read-only Private Integration

GHL > Settings > Private Integrations > Create. Tick only these read scopes:

- `contacts.readonly`: get a contact, and contact search (a POST that only reads)
- `opportunities.readonly`: opportunity search, and get one opportunity
- `calendars.readonly`: free slots
- `calendars/events.readonly`: calendar events, and get one appointment
- `conversations.readonly`: conversation search. **Unverified**: this scope was not part of the 2026-09-22 check. If GHL's list names it differently, tick the conversations read scope it does offer.

**Check this first:** GHL's docs imply that a token with only readonly scopes is allowed, but they never say so outright. Create the token, then do the smoke read in step 5 before you change anything else. If GHL refuses to create a readonly-only token, stop there. The fallback (R2) is one GHL token kept only in `~/.advero/live.env`, with no GHL token in the repo `.env`. Agent sessions then get no GHL reads (every read logs `ghl_token_missing` and returns None).

The write-capable token you already have (or will create) keeps the matching `.write` scopes. It is the one that goes in `live.env`.

## 3. Put each key in its place, with NEW write keys

**Rotate. Don't just move.** The current Instantly key has sat in the repo `.env` since 2026-09-21, so every process an agent started since then has loaded it. Moving it out of `.env` doesn't take back those copies. It also sits in `Coding/lead-scrape-2026/.env`, according to `config/ids.json`. And `execution/modal_reply_handler_v2.py`, a tracked file, has credentials hard-coded at HEAD; whether any of them is a live Instantly key is unverified, and step 6 covers it either way. So the write keys that go into `live.env` must be **new** ones. Everything in this section is your action, in your own terminal and your own vendor dashboards.

1. Instantly > Settings > Integrations > API Keys: create a **new** write-capable key. Keep the old one for now.
2. GHL > Settings > Private Integrations: create a **new** write-capable token, with the same `.write` scopes as the current one. If no GHL token was ever minted, this is simply the first one.

Repo `Agentic Worklfows/.env` (agents can read this file) gets only the two read keys:

```
INSTANTLY_API_KEY_READ=<the Instantly all:read key you created in section 1>
GHL_PRIVATE_INTEGRATION_TOKEN_READ=<the GHL readonly token you created in section 2>
```

**Confirm each `_READ` key's scope in the vendor dashboard before you go on.** A write key saved under a `_READ` name would quietly defeat all of this, and step 5 would not notice, because a write key reads fine.
- Instantly > API Keys: the key you pasted as `INSTANTLY_API_KEY_READ` shows `all:read` and nothing else.
- GHL > Private Integrations: the token you pasted as `GHL_PRIVATE_INTEGRATION_TOKEN_READ` shows only `.readonly` scopes.

Then **delete** `INSTANTLY_API_KEY=` and `GHL_PRIVATE_INTEGRATION_TOKEN=` from **all four** of these files:
- `Agentic Worklfows/.env`
- `AdveroSolutions/.env`
- `Agentic Worklfows/execution/.env`
- `Coding/lead-scrape-2026/.env`

`load_env` reads the first two. The `execution/` scripts load the third. `Coding/lead-scrape-2026/instantly_push.py` reads the fourth (see "What breaks").

Put the **new** write keys in a file outside the repo:

```
mkdir -p ~/.advero && chmod 700 ~/.advero
nano ~/.advero/live.env        # INSTANTLY_API_KEY=<new>  and  GHL_PRIVATE_INTEGRATION_TOKEN=<new>
chmod 600 ~/.advero/live.env
```

`load_env` never reads this file. It reads only the two repo `.env` files (`shared/paths.py` `ENV_PATHS`). The Modal secret script reads it directly.

When you need a laptop write, such as a change-set `--apply`, load the keys into that one terminal:

```
set -a; source ~/.advero/live.env; set +a
```

Never start Claude from a shell where you have done that. Close the terminal when you're finished.

## 4. Rebuild the Modal secret and redeploy

The deployed engine needs the write keys, so the secret carries them. Run the D1 script from `Agentic Worklfows/`, in your own terminal:

```
python3 changesets/deploy/modal_secret.py --mode shadow                    # plan: names and lengths only
python3 changesets/deploy/modal_secret.py --mode shadow --create           # type CREATE when asked
```

For the live flip, use `--mode live`, as in the go-live checklist. The script looks for each write key in this order:

1. `~/.advero/live.env`
2. the process environment
3. `.env`

Check the plan output:
- The `INSTANTLY_API_KEY` and `GHL_PRIVATE_INTEGRATION_TOKEN` lines should say `~/.advero/live.env (required)`.
- A note saying a key "is still in the repo .env" means a copy was left behind. The note prints whichever source won, so delete that line and re-run the plan.
- A note that a key "in the repo .env differs from ~/.advero/live.env" means an old value was left behind.
- The script ignores any other name in `live.env` and lists it.
- It adds a note if the file is not chmod 600.

Then redeploy, so every container reads the new secret. The script prints the command.

**Every other Modal secret.** In the Modal dashboard, open the secrets list and check **each** secret, by key name only, for `INSTANTLY_API_KEY` or a GHL token. You don't need to reveal any value. Two are known from the code:
- `advero-lead-sync`, used by `execution/modal_lead_sync.py`, the daily lead sync.
- `instantly-email-responder`, used by `execution/modal_reply_webhook.py`, which is tracked at HEAD and deleted in the working tree.

Any secret that holds the key almost certainly holds the old one. Before step 6, either put the new key in it and redeploy its app, or confirm the app is stopped and delete the secret. Otherwise revoking the old key breaks that app, or leaves the old key where you forgot about it.

## 5. Verify with a shadow, read-only run

From `Agentic Worklfows/`, in a fresh terminal where you have **not** sourced `live.env`:

```
python3 -c "from shared import keys; print(keys.read_key_and_name('instantly')[1], keys.read_key_and_name('ghl')[1], keys.write_key('instantly') is None, keys.write_key('ghl') is None)"
```

Expect `INSTANTLY_API_KEY_READ GHL_PRIVATE_INTEGRATION_TOKEN_READ True True`. That result means the agent-side environment holds no write key under the write names. It can't tell you what a `_READ` key can do; the dashboard check in step 3 covers that.

Smoke reads, each of which only reads:

```
python3 -c "
from shared.instantly import Instantly; from shared.ghl import GHL
i = Instantly(); g = GHL()
def get_one_email():
    items = i.list_emails(limit=1).get('items') or []
    if not items:
        print('SKIP get_email: no received email to fetch'); return
    i.get_email(items[0]['id'])          # the recipient re-check before a send uses this read
for name, call in [('instantly campaigns', lambda: i.list_campaigns(limit=1)),
                   ('instantly emails', lambda: i.list_emails(limit=1)),
                   ('instantly get_email', get_one_email),
                   ('instantly leads/list', lambda: i.list_leads(limit=1)),
                   ('instantly campaigns/analytics', lambda: i.campaign_analytics()),
                   ('ghl opportunities', lambda: g.search_opportunities(limit=1)),
                   ('ghl contact search', lambda: g.search_contacts('nobody@example.invalid')),
                   ('ghl calendar events', lambda: g.get_calendar_events(None, 0, 1))]:
    try:
        call(); print('OK  ', name)
    except Exception as exc:
        print('FAIL', name, '->', exc)
"
python3 services/reply_engine/poller.py --dry-run --lookup-leads --limit 5
python3 jobs/pipeline_sweep.py --dry-run
```

All lines should say OK. The warning "reads are using the write-capable ..." must not appear. Also check the deployed engine with the health check in the go-live checklist (`changesets/deploy/verify_health.py`), which confirms the redeployed containers came up on the new secret.

## 6. Revoke the old write keys

Do this only after steps 4 and 5 pass and every Modal secret from step 4 is dealt with.

- Instantly > API Keys: **account for every key on the list.** You should recognise only three:
  - the new write key in `live.env` and the Modal secret,
  - the `_READ` key,
  - any key you just put in another Modal secret.

  Delete every other key, including any you can't account for. Don't rely on knowing which file held which old copy.
- GHL > Private Integrations: do the same. Keep the new write token and the readonly token, and delete the rest.

Then run step 5 once more. Anything that still used an old key now fails loudly instead of working quietly.

**If you defer the rotation (new write keys in step 3, revocation in step 6):** the old Instantly key stays valid, and it can send, pause, move and delete. Copies of it remain in several places:
- in `Coding/lead-scrape-2026/.env` and every other `.env` above, readable by any agent session, until you delete it from them;
- in the logs and environments of every agent-run process since 2026-09-21;
- in any Modal secret still holding it;
- possibly in git history.

Moving the key out of the two repo `.env` files stops new agent sessions from loading it through `load_env`, and that is all it does. Until you delete the old key from every file and revoke it, R2(a) only covers the future.

## Rollback

To undo the code change (a revert of `shared/keys.py` and the client split) after the migration: the old code reads only `INSTANTLY_API_KEY` and `GHL_PRIVATE_INTEGRATION_TOKEN`. Pick one of these for the laptop:

- **Keep agents read-only:** put `INSTANTLY_API_KEY=<the read key>` (and `GHL_PRIVATE_INTEGRATION_TOKEN=<the readonly token>`) in the repo `.env`. Reads work. Laptop writes get a 403 from the vendor, and shadow writes send nothing anyway.
- **Full restore:** put the write keys back in the repo `.env`. This undoes R2(a).

**The Modal secret: leave it alone during a rollback.** The secret already carries the write keys under their main names, and the reverted code reads those names, so it keeps working. **Do not re-create it with the reverted `modal_secret.py`.** That version reads write keys from `.env` only. Under "keep agents read-only", `.env` holds the read key under the main name, so the new secret would carry the read key, and every live write from Modal would get a 403. If the secret must be re-created during a rollback, pick one of these:
- run the reverted script with `--env-file` pointing at a temporary file that holds the write keys (`chmod 600`, outside the repo, deleted afterwards);
- keep this version of `changesets/deploy/modal_secret.py`, which reads `~/.advero/live.env`, when you revert the rest.

## What breaks

- **A missing scope.** A read made with a `_READ` key that lacks a scope fails right away. You get `InstantlyScopeError` or `GHLScopeError`, and the message names the scope to add, or says the scope is unverified and that `all:read` is expected to cover it. Nothing is retried. Add the scope, or recreate the key with it. The key's value never appears in the message.
- **A live write in a process with no write key** is refused before any request is sent. The two clients leave different traces:
  - **Instantly:** raises `InstantlyError` ("INSTANTLY_API_KEY is not set") and writes a `live_write_intent` row, then a `live_write_failed` row.
  - **GHL:** raises `GHLError` ("ghl_token_missing") and writes a `live_write_intent` row, then a `skipped_no_token` row (not `live_write_failed`, same as before this change).
  - Shadow writes are unaffected, because they never send anything.
- **Scheduled laptop jobs** get no Instantly or GHL write key, by design, and none of them needs one. None of the 8 laptop jobs writes to Instantly or GHL:
  - `autoresponder_canary`, `client_scorecard`, `daily_metrics`, `deliverability_monitor`, `inbox_inventory`, `inbox_placement`, `list_factory`, `retro_packet`.
  - `list_factory`'s stage-out only calls `guard_write`, and never sends.
  - If one ever tries a live write, it fails the way the item above describes.
- **Laptop change-set `--apply` runs** need `live.env` sourced in that terminal (step 3). Their dry-runs are reads, so they work with the read key.
- **`Coding/lead-scrape-2026/instantly_push.py`** (your separate lead-scrape tool) creates campaigns, pushes leads and activates campaigns. It reads `INSTANTLY_API_KEY` only from `Coding/lead-scrape-2026/.env` or `Agentic Worklfows/.env`, never from the process environment. So once the key is gone from both files, the script stops working. **Do not put a key back into either `.env` to fix it.** That re-creates the exposure this runbook removes. There are two ways out, and both are your call:
  - **Change the script** so it reads `INSTANTLY_API_KEY` from the process environment. Then run it only in a terminal where you have sourced `~/.advero/live.env` (step 3). That is a change to your tool, and nothing here makes it.
  - **Retire the script** and push leads through the list factory (`create_lead`, guarded), or by hand in the Instantly UI.
- **Legacy `execution/` scripts** read `INSTANTLY_API_KEY` directly, not through `shared/`. They will not find it in agent sessions or in any shell that has not sourced `live.env`. Checked with grep on 2026-09-22, by file name and code only, with no `.env` opened.
  - In the working tree today:
    - read the key themselves: `execution/instantly_api.py`, `execution/instantly_campaign_builder.py`
    - import those two, and break with them: `execution/instantly_lead_sync.py`, plus the untracked `execution/export_and_separate_leads.py` and `execution/separate_contacted_leads.py`
    - `execution/modal_lead_sync.py` imports the lead sync, but runs on Modal from the `advero-lead-sync` secret (step 4), not from `.env`.
  - Tracked at HEAD but deleted in the working tree by the 2026-09-21 cleanup. They break the same way if restored:
    - read the key directly: `modal_reply_webhook.py` (Modal secret `instantly-email-responder`), `modal_reply_handler_test_mode.py`, `modal_reply_handler_v2.py`, `system_status.py`, and `test_instantly_auth.py`, `test_instantly_decode.py`, `test_instantly_endpoints.py`, `test_instantly_final.py`
    - import the legacy modules: `campaign_monitor.py`, `campaign_orchestrator.py`, `no_show_recovery.py`, `non_booker_follow_up.py`, `reply_monitor.py`, `sequence_tracker.py`, `test_full_system.py`
