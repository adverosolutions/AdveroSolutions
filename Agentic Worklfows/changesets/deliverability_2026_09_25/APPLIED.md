# Applied 2026-09-25, 20:46-20:48 CT (2026-09-26 01:46-01:48 UTC)

Applied by Claude from worktree `.worktrees/deliv` at commit a37c3e7, with Lorenzo's explicit chat permission ("giving you access and permissions to changing the instantly ... make sure that you have clear documentation and storage of every lead that you remove"). Reviewed by reviewer-max (APPROVE, round 3). Exit 0.

## Why

- Placement test A (01a0dac3-e227-7eb6-8334-f0a75795b689, current copy): Gmail seeds put proadvero.com 24/24 in spam, the other three domains 1/65. Microsoft seeds 42/45 in spam across all four domains.
- Placement test B (01a0db13-63d9-7ab8-b06a-50da867e505b, same email with the gift card removed): Microsoft 23/25 in spam. The copy is not the Microsoft lever, so no copy was changed.
- Live replies: 11 human replies from Microsoft-hosted leads Sep 15-18, none Sep 19-25, while Google and other providers kept replying.

## What changed

| Change | Result |
|---|---|
| A. proadvero.com out of all six campaigns | email_list 12 -> 9 on every campaign (lorenzo@, lorenzov@, lorenzovillarreal@proadvero.com removed). Accounts not paused, warm-up untouched. |
| B. allow_risky_contacts | True -> False on all six |
| Quarantine | the 3 proadvero inboxes added to `capacity.quarantine` in the main checkout's `Agentic Worklfows/.tmp/store.json` |
| C. Microsoft-hosted leads parked | 1,154 leads moved to Instantly lead list **Parked - Microsoft recipients 2026-09-25** (id `6e5482b6-470f-4acc-8edc-bdb492240fcc`), 16 move jobs, 0 failed, 0 skipped, every lead verified in the list and out of its campaign |

Campaigns stay paused (status 2). Sequences and copy are unchanged (body lengths re-read after apply).

Leads parked per campaign:

| Campaign | Not started | Mid-sequence (email 1 sent) | Total |
|---|---|---|---|
| 2026 Cleaning - Trigger Outbound | 58 | 48 | 106 |
| 2026 Bookkeeping - Client Reactivation | 205 | 62 | 267 |
| 2026 Recruiting - Outbound (specialty roles) | 155 | 50 | 205 |
| 2026 Bookkeeping - Trigger Outbound | 190 | 64 | 254 |
| 2026 Cleaning - Client Reactivation | 45 | 47 | 92 |
| 2026 Recruiting - Client Reactivation | 174 | 56 | 230 |
| Total | 827 | 327 | 1,154 |

Left in place on purpose: 3 Microsoft leads that had sent an out-of-office reply (interest status set), and 424 Microsoft leads that were never in any campaign.

## Where the records are

- **Per-lead manifest** (one row per lead: id, email, name, company, website, original campaign, stage, last step, move job, verification, restore columns). Lead PII, never committed:
  - `.worktrees/deliv/Agentic Worklfows/changesets/deliverability_2026_09_25/manifests/parked_leads_2026-09-25.csv` and `.json`
  - copy: `AdveroSolutions/.tmp/deliverability_2026_09_25/parked_leads_2026-09-25.csv` and `.json`
- **Campaign rollback points** (full campaign JSON taken before the PATCH), `deliverability_2026_09_25_<campaign_id>_20260926T014659Z.json`, in:
  - `.worktrees/deliv/Agentic Worklfows/changesets/backups/`
  - `Agentic Worklfows/changesets/backups/` (main checkout)
  - `AdveroSolutions/.tmp/deliverability_2026_09_25/campaign_backups/`
- **Run log**: Job_Log rows written by the script.

## How to undo

See README.md "Undo". `--restore-leads` reads `manifests/parked_leads_2026-09-25.csv` from the checkout it runs in. If running from a checkout other than `.worktrees/deliv`, first copy the manifest from `AdveroSolutions/.tmp/deliverability_2026_09_25/` into that checkout's `changesets/deliverability_2026_09_25/manifests/`. Restore one mid-sequence lead first (`--limit 1`) and check its step in the Instantly UI before restoring the rest.
