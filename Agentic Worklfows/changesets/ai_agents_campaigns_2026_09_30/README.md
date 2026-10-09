# AI Agents campaigns (2026-09-30)

Creates six Instantly campaigns, left in draft (status 0). The script never starts, stops or changes the state of any campaign.

| Campaign | Key |
|---|---|
| 2026 Bookkeeping & tax - AI Agents | bookkeeping_ai |
| 2026 Insurance brokers - AI Agents | insurance_broker_ai |
| 2026 Landscaping - AI Agents | landscaping_ai |
| 2026 Marketing agencies - AI Agents | marketing_agency_ai |
| 2026 MSP - AI Agents | msp_ai |
| 2026 Pest control - AI Agents | pest_control_ai |

- Copy: `copy_source.json`, byte for byte from the Claude Doc "Cold Email Rebuild: AI Agents" (rev 85). Step 1 has variants A and B (subject `{{firstName}}, question`), step 2 is one variant with an empty subject (same thread), 3 days apart. Each line becomes `<div>line</div>`, each blank line `<div><br /></div>`.
- Settings: read live from "2026 Service - AI Agents" (`d81f1d53-...`) at run time: schedule, the same 12 inboxes, daily_limit, email_gap, text_only, stop_on_reply, link/open tracking, pl_value. Also sends `insert_unsubscribe_header: true`, `allow_risky_contacts: false`.
- New ids go to `Coding/lead-scrape-2026/instantly_campaigns_ai_agents.json`. `instantly_campaigns.json` is not touched (its `--activate` flag would start every id in it).

## Commands (from this folder)

```
python3 apply_ai_agents_campaigns.py --dry-run      # dry-run (also the default), GETs only; payloads -> .tmp/ai_agents_2026_09_30/dryrun_payloads.json
MODE=live ALLOW_LIVE_WRITES=1 python3 apply_ai_agents_campaigns.py --apply --yes  # live create (Lorenzo only, from his own terminal)
python3 -m pytest -q -p no:cacheprovider test_apply_ai_agents_campaigns.py
```

`--apply` refuses (exit 2, no request at all) unless `--yes` is given and the environment has `MODE=live` and `ALLOW_LIVE_WRITES=1` (same rule as `shared/settings.py` `is_live()`). `--dry-run` with `--apply` also refuses.

Exit codes: 0 ok, 1 invalid copy (a structure check fails before any POST), 2 refused (live gate not set, `--yes` missing, or a name already exists live), 3 a POST failed or raised (timeout, network, bad JSON; the output names the campaign that may exist without a recorded id), a read-back GET or verify failed, the final re-list failed, or a pre-existing campaign's status changed. A re-run after apply refuses, so it cannot create duplicates.

Live apply snapshots every campaign's id/name/status to `.tmp/ai_agents_2026_09_30/before_<ts>.json`, writes each new id to the ids file as soon as its POST returns, then verifies each new campaign against what was sent (draft status, bodies byte for byte, subjects, per-step delay and delay_unit, inboxes, daily_limit, email_gap, text_only, stop_on_reply, link/open tracking, pl_value, schedule) and that no existing campaign's status moved. A failed read-back or re-list is recorded and the remaining checks still run. Results go to `APPLIED.md`, which is written in every case once the POSTs are done.

## Rollback

Delete the six campaign ids listed in `Coding/lead-scrape-2026/instantly_campaigns_ai_agents.json` (Instantly UI, or `DELETE campaigns/<id>`), then remove that file. They are drafts with no leads, so nothing else depends on them.
