# Go-live checklist

> **Rewritten 2026-09-22 after the re-review.** Do not start Stage 3 or later until the live-write guard (Stage 0.4) is in and Lorenzo has signed off the fix plan in `REREVIEW_2026-09-22.md`.

The ordered, top-level path to a system that runs on its own. This page says **what** and **in which
order**. The **how** lives in the runbooks it points to, and they win if this page ever disagrees:

- `runbooks/deployment.md`: the Modal secret, the shadow deploy, the laptop runner, the 48-hour watch,
  the cutover, the live flip and the rollback.
- `runbooks/phase0.md`: the Instantly campaign copy, labels and subsequence.
- `runbooks/capacity.md`: the Oct 11 capacity change.
- `changesets/PHASE0_MANUAL_CHECKLIST.md`: the clicks in GHL, Instantly and ntfy.

**Working directory.** Every command on this page and in those runbooks runs from:

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
```

The only exceptions are `launchctl` and `crontab`, which work from any folder.

**Who does what.**

- **[L]** Lorenzo does it, from his own terminal or the vendor's UI. Claude prepares the exact command
  and reads back the output Lorenzo pastes. Every step that touches Modal, sets `MODE=live` or
  `ALLOW_LIVE_WRITES=1`, runs an apply, restore or rollback without `--dry-run`, or pushes to git is [L].
  So is any dry-run that reads a live API, until the read-only keys exist (Stage 0.3).
- **[C]** Claude may do it: local, offline work only. Tests, `build_schedules.py --check`, offline
  replays (`--fixtures`, and a change-set's `--dry-run --from-snapshot`; the live-write guard refuses a
  change-set run that does not say `--dry-run`), and edits to local files that Lorenzo then reviews.

**What gates going live.** Not one short list of decisions. Each stage below names what it depends on.
The hard gates are: the credentials rotated (0.1), the live-write guard installed (0.4), the GHL token
(2.1), the prices (1.2), a clean 48-hour shadow watch (Stage 3) and Lorenzo's written go.

---

## Stage 0: before live, Lorenzo's side

### 0.1 Rotate the committed credentials [L]

- `execution/modal_reply_handler_v2.py` hard-codes four live credentials in its `modal.Secret.from_dict`
  block: an Instantly API key, a GitHub token, a Slack webhook URL and a Google service-account private
  key. The file is deleted in the working tree but still tracked at HEAD and in older commits.
- The Modal secret `instantly-email-responder`, read by the April test-mode app, needs rotating too.
- Two April Modal apps are still deployed: `instantly-email-responder-v2` and
  `instantly-email-responder-test-mode`. Decide whether to stop them
  (`python3 -m modal app stop <name>`), after checking nothing still calls them.
- Rotating the Google key means replacing `credentials.json` and the `GOOGLE_CREDENTIALS_JSON` value
  too. Until the new key is in place, every Sheets read and the Job_Log mirror fail.
- Do not add a git remote before this is done. Any remote must stay private: tracked test fixtures
  hold real email addresses.
- Full facts: `REREVIEW_2026-09-22.md`, "What went wrong that you did not know", items 4 and 5, and
  `DECISIONS_FOR_LORENZO.md` 0.1.
- **Undo**: none wanted. A rotated key is never put back.

### 0.2 Fix the `GOOGLE_CREDENTIALS_JSON` placeholder in `.env` [L]

`.env` still carries a placeholder value for it. `changesets/deploy/modal_secret.py` refuses to build
the Modal secret while it is there. Put the real service-account JSON there (the rotated one from 0.1),
or delete the line.

### 0.3 Create read-only keys [L]

Follow `runbooks/read_only_keys.md` (being written). Until these exist, Claude runs nothing that reads
a live API.

### 0.4 Install the live-write guard [L]

Follow `runbooks/live_write_guard.md` (being written). Until it is in, do not count on any hook: the
only protection is the code-level `shared.settings.guard_write`.

### 0.5 A2P 10DLC registration, if SMS will be used [L]

- Takes days. The clicks are in `changesets/PHASE0_MANUAL_CHECKLIST.md` section 2.
- Keep `A2P_10DLC_REGISTERED` unset (or `0`) in `.env` until GHL shows the campaign approved. Until
  then every SMS leg is skipped as `a2p_not_registered`.

---

## Stage 1: decisions with a date on them [L]

### 1.1 The Oct 11 capacity shape and the domain order

Option A or Option B: `DECISIONS_FOR_LORENZO.md` Q-L1, which uses the same definitions as
`changesets/capacity/domain_order.md`. The order itself is Q-L3. The decision also sets each
campaign's new `daily_limit` for Stage 7. A domain order cannot be undone.

### 1.2 Prices and the deposit rule in `config/offers.md`

`DECISIONS_FOR_LORENZO.md` M1 (the missing prices) and M2 (the deposit contradiction). The Phase 0 copy
and the reply drafts quote this file.

`config/` is copied into the Modal image at deploy time. An edit made after a deploy reaches the
deployed engine only with another deploy (see 3.2).

### 1.3 Deliverability decisions

The five inboxes under the 1% line (`DECISIONS_FOR_LORENZO.md` Q-K1; counted by unique replying lead,
as `jobs/deliverability_monitor.py` `aggregate_window` has done since MKT-4), the level-2 placement
test (started by hand in the Instantly UI, then `python3 jobs/inbox_placement.py --now --seed <address> ...`), and whether
the level-4 canary mails real prospects (J10, J11). None of these blocks the sales tier.

---

## Stage 2: credentials and settings [L]

**Where each key goes** (decision R2(a): agent sessions only ever see read-only keys;
`runbooks/read_only_keys.md` step 3, variable names from `shared/keys.py`):

- The two write-capable keys, `INSTANTLY_API_KEY` and `GHL_PRIVATE_INTEGRATION_TOKEN`, go in
  `~/.advero/live.env`, outside the repo, `chmod 600`. Not in `.env`: delete them from
  `Agentic Worklfows/.env` and from `AdveroSolutions/.env`.
- Their read-only copies, `INSTANTLY_API_KEY_READ` and `GHL_PRIVATE_INTEGRATION_TOKEN_READ`, go in
  `.env`.
- Every other value in this stage goes in `.env`.

`changesets/deploy/modal_secret.py` builds the Modal secret later. It takes the two write keys from
`~/.advero/live.env` first (then the shell, then `.env`, with a note to move them) and everything else
from `.env` (`modal_secret.py:13-20`; deployment.md step 2a lists every key and what the script
requires).

**Every [L] live command on this page needs the write keys in that one terminal first.** That means 4.1,
4.2, the Stage 6 and Stage 7 applies, the Stage 6b webhook apply, the Stage 8 inbox-action apply, and
every restore and rollback in "Backups and restore". Before the command, in the same terminal:

```bash
set -a; source ~/.advero/live.env; set +a
```

Never start Claude from a terminal where you ran that. Close it when you are done. Dry-runs and the
Modal secret script do not need it.

### 2.1 GHL Private Integration token

- Create it: `changesets/PHASE0_MANUAL_CHECKLIST.md` section 3 (scopes listed there).
- Put it in `~/.advero/live.env` as `GHL_PRIVATE_INTEGRATION_TOKEN`, never in `.env`. The secret script
  refuses to run without it.
- Create the read-only integration too (`runbooks/read_only_keys.md` step 2) and put that token in
  `.env` as `GHL_PRIVATE_INTEGRATION_TOKEN_READ`. Do its smoke read (step 5) before anything else.
- **Undo**: delete the integration in GHL (both, if you made the read-only one). What the code then does depends on
  which token is still set (`shared/ghl.py`, `shared/keys.py`):
  - Reads send `GHL_PRIVATE_INTEGRATION_TOKEN_READ` when it is set and fall back to `GHL_PRIVATE_INTEGRATION_TOKEN`
    only when it is not. With the read token set, deleting only the write integration leaves reads working; only writes stop.
  - A deleted token that is still set is not "missing": GHL refuses it, so reads raise `GHLError` with the HTTP
    status (a 403 on the read-only token raises `GHLScopeError`, which names a scope although the real cause is
    the deleted token), and live writes fail the same way.
  - Reads return nothing with a `ghl_token_missing` warning only once neither variable is set (remove them from
    `.env` and `~/.advero/live.env`; a deployed container keeps whatever the Modal secret holds, a deleted token
    included, so on Modal expect the auth errors above). In live, a write with no
    `GHL_PRIVATE_INTEGRATION_TOKEN` writes a `skipped_no_token` Job_Log row and raises.

### 2.2 Read the GHL calendar timezone

Every slot rule assumes Central. It has never been read. `PHASE0_MANUAL_CHECKLIST.md` section 1.

### 2.3 ntfy

Set `NTFY_TOPIC` (already set in `.env`; confirm it is yours), and set `NTFY_ALLOW_SENSITIVE` to `0` or
`1` (required by the secret script). For Approve buttons on the phone, set `NTFY_TOKEN` on a protected
topic, or `NTFY_ALLOW_SENSITIVE=1`, or all three of `GMAIL_SENDER_EMAIL`, `GMAIL_APP_PASSWORD` and `NOTIFY_EMAIL`. deployment.md step 2a.

### 2.4 `REPLY_ENGINE_SECRET`

Add it once, never regenerate it: every approval link and webhook carries it. deployment.md step 2a has
the one-line generator.

### 2.5 The rest

`PAYMENT_LINK_URL` (without it every SOP-009 draft is unsendable), `FIREFLIES_API_KEY`, the Skool
values, and anything else in the deployment.md step 2a table you want on. Unset optional keys are left
out of the secret, never sent empty.

### 2.6 Zoom

1. **[L]** Connect Zoom in GHL and set it as the Discovery Call meeting location
   (`PHASE0_MANUAL_CHECKLIST.md` section 1 has the clicks).
2. **[C]** Then change `config/ids.json` at `ghl.calendars.discovery_call.conferencing`. The engine
   treats Zoom as connected only when that value contains `zoom` and does not contain `not connected`
   (`services/reply_engine/booking.py`, `zoom_connected_default`). Today it reads
   `google_conference (Zoom NOT connected as of 2026-09-21; isZoomAdded=false)`. Something like
   `zoom (connected <date>)` works. Until it changes, every booking confirmation draft carries a
   `zoom_not_connected` note (not a blocking problem) and uses the no-Zoom wording, whose template
   (`booking.confirmation.no_zoom_link`) is approved separately from the Zoom one.
3. `config/` is baked into the Modal image, so this needs a deploy (the next one in Stage 3, or a
   redeploy as in 3.2).

How booking works once Zoom is on: when a lead picks a time, the engine creates the GHL appointment
with `toNotify: false`, so GHL emails the lead nothing. The engine treats it as held, not confirmed,
and sends you the card. On Approve, once the reply is out, it updates the appointment to `confirmed`
with `toNotify: true`, and GHL sends the invite. Check this in the rehearsal (4.2).

---

## Stage 3: shadow deploy and the 48-hour watch [L]

Follow `runbooks/deployment.md` steps 1 to 3 in order. The short version:

**Before step 1: templates (CT3).** Rule (2026-09-22): an engine email (first reply, counter-proposal,
booking confirmation, cadence touch, show-rate or no-show message) is sent automatically only when its
text is exactly a template you approved with `jobs/approve_templates.py` and unchanged since, the
template kill switch is off, and every send check passes (copy gate, opt-out marker, lead reply hold,
07:00-19:00 CT send window, recipient check, slot rules). Anything else goes to you as an approval card
(replies) or is held (cadence, show-rate, no-show). That is a code rule, not a mode: shadow runs the same
gate. Do these in order before the first preflight (step 1 below), and again before every
`--deploy shadow`, which runs the preflight itself; `--deploy live` runs none and accepts only a
preflight stamp from the last 60 minutes on the same code:

a. **Approve the ladder ids first** [L], from your own terminal: `runbooks/template_approvals.md`,
   "Approve the ladder templates before deploying CT3" (export, read, `--approve-all-shown`). These are
   the `cadence.*`, `show_rate.*` and `no_show.*` ids, including the lines spliced into days 2, 4 and 5.
   First reply and booking ids can follow later, a few at a time; leave `first_reply.*.other.full` and
   `first_reply.*.referral.full` unapproved at first.
b. **Read the preflight's template checks** [L]. Step 7 rebuilds `config/template_catalogue_hashes.json`
   (`template_parity.py --write`, then `--check`) and refuses the deploy on a mismatch. Step 8 prints the
   ladder ids that are still unapproved or could not be rendered, warns when the kill switch is on, and
   while either count is not 0 asks you to type `HOLD`. `HOLD` deploys with those messages held; a
   show-rate or no-show message whose send time passes while held is dropped, not sent late. Commit the
   reference file with the code it was built from.
c. **Choose the kill switch state** [L] before the secret (step 3 below). Off (`AUTO_SEND_TEMPLATES`
   unset or `1`, and no `"auto_send"` other than `true` in `config/approved_templates.json`) lets approved
   templates send. On (for example `AUTO_SEND_TEMPLATES=0` in the secret, deployment.md step 2a) turns
   every reply into a card and holds every cadence, show-rate and no-show message, including the
   reminders before a booked call. Step 8 reads only this laptop's value, not the Modal secret's.

After each deploy, `/health` must report `templates.parity` as `ok`; `verify_health.py` fails the deploy
otherwise (it polls again while it is `not_ready`).

1. **Local checks** (deployment.md step 1). [C] may run `python3 -m pytest -q` and
   `python3 changesets/schedules/build_schedules.py --check`. The preflight
   (`bash changesets/schedules/install_schedules.sh --preflight`) is [L]: it writes the stamp the live
   flip accepts.
2. **The received-email count** before the first shadow deploy (deployment.md step 2b). It must print
   `more than 20 pages: False`.
3. **The secret** (step 2a): `modal_secret.py --mode shadow`, then `--create`. The plan must show the
   two write keys coming from `~/.advero/live.env`; everything else comes from `.env`.
4. **Deploy in two passes** (step 2b): `--deploy shadow --first-pass`, then the secret again with the
   web URL, then `--deploy shadow`. The second pass must end with all `/health` checks passed.
5. **The laptop runner** (step 2c): 8 laptop jobs through launchd, plus the `self_test` agent. The three
   turned-off jobs are not installed; remove them if an earlier install loaded them.
6. **Start the report clock** (step 2d): `watch_clock.py start-report`. It refuses until the second-pass
   health check, the launchd self-test and a complete poller cursor all hold.
7. **Watch 48 hours** (step 3). The gate is `changesets/deploy/watch_report.py`, which reads the
   records the Modal containers wrote to the evidence Dict (`advero-reply-engine-obs-shadow`) plus the
   laptop runner's `.tmp/laptop_runs/runs.jsonl`. **Do not** judge the watch from the laptop's
   `.tmp/job_log.csv` or `.tmp/shadow_log.jsonl`: they only describe laptop runs. The automated criteria
   include zero `live_write_*` rows; the manual ones (a push each morning, one approval card tapped end to
   end, every `would_do` record read) are yours.

**Rollback**: `python3 -m modal app stop advero-reply-engine` stops every schedule and the web endpoint.
For the laptop agents, `launchctl bootout` (deployment.md Rollback step 3).

### 3.1 LLM spend during the watch [L]

- Check it in the deployed store: `python3 changesets/deploy/budget.py status`. A laptop
  `llm.budget_status()` reads the laptop's own counter, not Modal's.
- If the cap is hit: `python3 changesets/deploy/budget.py reset --store-mode shadow` (type `RESET`)
  zeroes the Modal counter. `llm.reset_spend()` on the laptop does not.
- Raising `budget_usd` in `config/llm_budget.json` does nothing on Modal until a redeploy
  (`DEPLOY_TIERS=sales bash changesets/schedules/install_schedules.sh --deploy shadow`).
- After either, restart the report clock: deployment.md step 3, "When the budget cap is hit".

### 3.2 Any later redeploy

`config/`, `shared/`, `services/` and `jobs/` are a snapshot taken at deploy time. After any change to
them (prices, Zoom, the inbox list, the budget), redeploy in the current mode.

- **In shadow:** `DEPLOY_TIERS=sales bash changesets/schedules/install_schedules.sh --deploy shadow`. It
  runs the preflight itself.
- **Once live:** a fresh preflight, then the live deploy, with no code change in between:

  ```bash
  DEPLOY_TIERS=sales bash changesets/schedules/install_schedules.sh --preflight     # the stamp lasts 60 minutes, on this exact code
  DEPLOY_TIERS=sales bash changesets/schedules/install_schedules.sh --deploy live   # type DEPLOY, then CREATE; /health must say live
  ```

  `--deploy live` checks the stamp before it asks anything, then re-creates the live secret itself
  (`modal_secret.py --mode live --create`) and deploys straight after (`install_schedules.sh:218`, `:275`;
  deployment.md step 5). Do not create the live secret by hand. Do not re-run the step 5 block either:
  `cutover.py --apply` refuses a store that was already cut over.

---

## Stage 4: rehearsals before the sales tier goes live [L]

### 4.1 One-send reply rehearsal

The reply endpoint has two recipient guards, and nobody knows yet which one does the work
(root `CLAUDE.md`, "Instantly API contract"; `config/instantly_api_contract.md`, `POST /emails/reply`):
`shared/instantly.py` refuses to send without `to=<lead email>`, and in live
`services/reply_engine/cadence.py` `thread_recipient_ok` re-reads the email and refuses unless its
sender is the lead. One test settles it.

**The limits.** The system sends at most **one** email in this rehearsal, and only between mailboxes you
own. No prospect is ever on the thread. Run the send once, whatever happens: if it errors, do not run
it again; bring the output to Claude.

Three mailboxes take part, all yours:

- **Mailbox A**: your own first mailbox, not an Instantly inbox. It starts the thread.
- **Inbox I**: one of the Instantly sending inboxes. It receives A's email and sends the reply.
- **Mailbox B**: a second address you own, not A and not an Instantly inbox. It is the deliberately
  wrong `to`.

1. From mailbox A, email inbox I. Nobody else on To or Cc.
2. Claude prepares a read-only command that finds that email's id in inbox I
   (`shared.instantly` `list_emails(email_type="received", eaccount=<inbox I>)`). Once the read-only keys
   exist (0.3), Claude may run it.
3. **Check the id right before the send (read-only).** `reply_to_email` run by hand does not go through
   `cadence.thread_recipient_ok` (`services/reply_engine/cadence.py`), so nothing else checks whose email
   this is. With a wrong id, and an Instantly that ignores `to`, the reply would go to whoever sent that
   email, possibly a prospect. So, in the same terminal, just before step 4:

   ```bash
   python3 -c "from shared.instantly import Instantly; e = Instantly().get_email('<id>'); print(e.get('from_address_email'), e.get('eaccount'))"
   ```

   It must print exactly mailbox A, then inbox I. **If either is anything else, stop.** Do not send.
4. Send one reply into that thread, with `reply_to_uuid=<id>`, `eaccount=<inbox I>` and a **deliberately
   wrong** `to`: mailbox B. Claude prepares the command. It calls `shared.instantly` `reply_to_email(...)`
   with `MODE=live ALLOW_LIVE_WRITES=1` on the command line for this one run only, after
   `set -a; source ~/.advero/live.env; set +a` in that terminal (Stage 2).
5. **Read the result.** Look at three places: the command's output, **mailbox A** and **mailbox B**
   (inbox and spam, give it 15 minutes). The reply can land in only one of three ways:

   | What you see | What it means | Which guard does the work |
   |---|---|---|
   | Instantly refuses the send with a message that names the recipient, `to` or the thread, and nothing arrives in A or B | Instantly checks `to` against the thread. | The `to` guard in `shared/instantly.py` is the one that works: Instantly itself blocks a reply whose `to` is not the thread's sender. `thread_recipient_ok` is then a second check of the same thing. |
   | The reply arrives in **mailbox A** (the thread's original sender), nothing in B | Instantly ignores `to` and always replies to the thread's sender. | `thread_recipient_ok` is the only guard that protects prospects. The `to` field does nothing. |
   | The reply arrives in **mailbox B** (with or without A) | Instantly sends to whatever `to` says, without checking it against the thread. | Both. `to` decides who gets the email, so it must be exactly the lead; `thread_recipient_ok` still checks the thread is that lead's. Neither can go. The `shared/instantly.py` docstring ("Instantly validates it against the thread") is then wrong. |

   Any other error (an `InstantlyScopeError`, a 401, a 5xx, a timeout) settles nothing: the result is
   unknown. So is a run where the command did not error and nothing arrives anywhere. In either case do
   not run the send again, bring the output to Claude, and write nothing into
   `config/instantly_api_contract.md`.
6. Record the answer in `config/instantly_api_contract.md`. Keep both halves until then. Delete a half only
   if the table says it does nothing (the second row), and only after this is recorded.

The same session is the place to confirm `DELETE /webhooks/{id}`, which is still unverified
(`changesets/instantly_webhooks.py` docstring), if you plan Stage 6b: create one webhook, delete it by id
with a hand-run call, then read `GET /webhooks`. Until that is confirmed, recorded in the API contract and
`DELETE_WEBHOOK_VERIFIED` in `changesets/instantly_webhooks.py` is set to `True`, the webhook rollback
sends no DELETE (see "Backups and restore").

### 4.2 Booking invite check

Once Zoom and any Google Calendar sync are on, rehearse the engine's two GHL calls by hand on a test
contact whose email is yours. Claude prepares the commands (`shared.ghl` `create_appointment(...,
appointment_status="new", to_notify=False)`, which is what `booking.book()` sends, then
`update_appointment_status(<id>, "confirmed", to_notify=True)`, then
`update_appointment_status(<id>, "cancelled", to_notify=False)` to clean up), each run with
`MODE=live ALLOW_LIVE_WRITES=1` on the command line, in a terminal where you first ran
`set -a; source ~/.advero/live.env; set +a` (Stage 2). The create must pass `"new"`:
`create_appointment` defaults to `"confirmed"`, which would skip the hold step entirely.

- After the create (the hold), the appointment shows in GHL as **Unconfirmed** (status `new`), and
  **no** invite, GHL email or calendar notification may reach that address. This check always
  applies.
- After the confirm (what Approve does), the status is **Confirmed** and the invite arrives with the
  Zoom link.
- The GHL workflows, only if they are already published. Today neither is (`MASTER_BUILD_REPORT.md`
  lists S4/S5 and S7 under "Not built").
  - For each workflow that is published at this point, check that nothing fires at the create and
    that it reacts only at the confirm. The show-rate workflow
    (`changesets/ghl_workflows/show_rate_workflow.md`) must enter at the confirm. For the proposal
    follow-up (`changesets/ghl_workflows/proposal_follow_up.md`), first move the test contact's
    opportunity to Proposal Sent so the contact is in the workflow, then check that the contact is
    removed at the confirm and not at the create.
  - For a workflow that is not published, skip it here. Its hold check lives in its own pre-publish
    test plan: test step 5 ("The hold path") in `show_rate_workflow.md`, and the "They book another
    call" row of the exit conditions in `proposal_follow_up.md`.
  - Do not publish the show-rate workflow just for this check. While `SHOW_RATE_SENDER=engine` (the
    default), the engine already sends those touches, so a published workflow would send every touch
    twice.
- If an invite, notification or workflow goes out at hold time, stop: a lead would hear from you about
  a call you have not approved.

The full rehearsal list, including the free-slot block and the calendar auto-confirm check, is
`runbooks/cadence_and_booking.md` step 7b. Run it in the same session.

---

## Stage 5: the sales tier goes live [L]

Follow `runbooks/deployment.md` steps 4 and 5.

1. Record the approval (step 4).
2. The watch report passes again, then a fresh preflight (the stamp lasts 60 minutes).
3. `python3 changesets/deploy/cutover.py --watch-start "$H"` (`$H` is the hand-off start, as deployment.md step 5 sets it), then the same with `--apply` (type `CUTOVER`). Handle every reply
   on the hand-off list by hand; the live engine never sees them.
4. Within 120 minutes of the cutover: `DEPLOY_TIERS=sales bash changesets/schedules/install_schedules.sh --deploy live`
   (type `DEPLOY`, then `CREATE`). `/health` must say live.
5. First hour: follow one positive reply end to end. Check spend with
   `python3 changesets/deploy/budget.py status --store-mode live`.

If the cutover refuses, or the live deploy fails: STOP and follow deployment.md step 5 exactly.

**Rollback**: deployment.md "Rollback" step 1 (stop the app) and step 2 (back to shadow: seed the shadow
cursor, re-create the secret, redeploy). Going live again afterwards is `cutover.py --resume-live`,
never `--redo`.

**Templates.** The CT3 template steps before Stage 3 step 1 ("Before step 1: templates (CT3)") apply to
the fresh preflight in step 2 above too: approve any ladder id that changed since, and read step 8's report.

---

## Stage 6: Phase 0 on Instantly, one campaign at a time [L]

- **Depends on**: 1.2 (the copy quotes prices), `DECISIONS_FOR_LORENZO.md` I1 (the long sentences),
  and the read-only keys (0.3) for Claude to run the live dry-runs. It does not depend on the deploy.
- **Follow** `runbooks/phase0.md`, "How to go live". [C] may run the offline dry-run
  (`python3 changesets/instantly_phase0/apply_instantly_phase0.py --dry-run --from-snapshot`) and the
  tests.
- Each apply is `MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/instantly_phase0/apply_instantly_phase0.py --apply --campaign <key>`,
  run in a terminal where you first ran `set -a; source ~/.advero/live.env; set +a` (Stage 2).
- The apply normally sends `sequences`, `pl_value` and `campaign_schedule`, including the B variants that
  experiments EXP-001a and EXP-001b need (`config/experiments.json`).

The safety gates, all in phase0.md:

- **One campaign at a time**, never all six. Order: `cleaning_reactivation`, `cleaning_trigger`,
  bookkeeping, then recruiting. Watch a full cycle before the next.
- **A fresh live dry-run right before each apply** (phase0.md checklist item 2):
  `python3 changesets/instantly_phase0/apply_instantly_phase0.py --dry-run --campaign <key>`. Read the
  full diff, not the summary. Then open the dry-run copy it wrote in `.tmp/changeset_dryruns/phase0/` and
  check its `timestamp_updated` matches what the Instantly UI shows. If they differ, somebody edited the
  campaign in the UI since: stop and dry-run again.
- **No copy edits in the UI during the 1,000-send window** (phase0.md checklist item 4). Both variants
  stay on for at least 1,000 sends per campaign, so the verdict at 500 per variant is fair.
- **The step-3 burst.** Live campaigns have 2 steps, the staged ones 3. The moment a PATCH lands, that
  campaign's completed leads (100 to 107 each, about 620 across the six) become due for step 3 at once,
  as a new thread. If you do not want that: pause, PATCH, trim the completed leads, re-activate.
- **UI preview** right after each apply: preview five leads. Spintax renders, personalization is line
  one, step 3 has its own subject, the timeline reads day 0 / 3 / 7. Step 1 on any day but day 0 means
  restore at once.
- **AI Smart Pause**: a UI-only toggle, on, per campaign (`PHASE0_MANUAL_CHECKLIST.md` section 6).
- **The Saturday drop and the new window.** The patch sets `campaign_schedule` to 07:00-19:00
  America/Chicago, Mon-Fri, on all six (`changesets/instantly_phase0/campaign_settings.json`). Live today
  (`config/snapshots/instantly_campaigns_2026-09-21.json`), all six send on Saturday, so Saturday sending
  stops on every one. Five of them run 07:00-19:00 America/Detroit: their day starts at 07:00 CT instead
  of 06:00 CT. `recruiting_outbound` runs 08:00-17:00 America/Chicago: the patch **widens** its window by
  3 hours (an hour earlier, two hours later). Read that line of the settings delta before confirming.
- **`cleaning_trigger` variables.** Its copy uses `{{buildingType}}` and `{{metro}}`, which its leads do
  not have today. The apply refuses it without `--allow-new-variables`; wait for the list factory to
  upload leads with those fields.
- **Labels** after the first campaign is live, created with AI off (`use_with_ai: false`).
- **The subsequence enrolled-count check.** Create the Interested-quiet subsequence for one campaign
  only, after 12:00 CT, and only after the cadence go-live decision. Straight after the first create,
  read its enrolled-lead count. **If it is not 0, delete the subsequence in the Instantly UI at once.**
  Its first email tells every enrolled lead "the times I floated have filled up", and a campaign has
  466 to 676 leads, including people who already hold a call. Move leads in by hand only when slots
  were offered and went unanswered, never a lead who holds a call.
- **Two checks**: within 24 hours (the burst goes out at `daily_limit`, bounces under 2%) and 48 hours
  later (step 3 lands on day 7 for leads whose step 1 came after the apply).

**Rollback**: the Phase 0 restore (see "Backups and restore" below). Labels and the subsequence are
removed by hand in the Instantly UI.

---

## Stage 6b: the Instantly webhooks (optional) [L]

Only after the sales tier has run live. The poller already reads replies. deployment.md step 6. The
apply needs `set -a; source ~/.advero/live.env; set +a` in that terminal first (Stage 2).

**Rollback**: by hand in Instantly (Settings, Webhooks) until `DELETE /webhooks/{id}` is confirmed (4.1).
See the Webhooks row in "Backups and restore".

---

## Stage 7: Oct 11 capacity [L]

After Stage 3, because it ends in a redeploy. Mechanics: `runbooks/capacity.md`, "Oct 11 capacity
change-set".

1. **[C]** Write the plan file `changesets/capacity/oct11_capacity.json` from the Stage 1.1 decision,
   in the shape of `oct11_capacity.example.json` (the example itself is refused). Lorenzo reviews it.
2. Dry-run: `python3 changesets/capacity/apply_capacity.py --dry-run --input changesets/capacity/oct11_capacity.json`.
3. Apply one campaign at a time:
   `MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/capacity/apply_capacity.py --input changesets/capacity/oct11_capacity.json --campaign <key> --apply`.
   Run it in a terminal where you first ran `set -a; source ~/.advero/live.env; set +a` (Stage 2).
   It adds the warmed inboxes to `email_list` and sets `daily_limit` in one PATCH.
   **Warm-age:** the 33 new inboxes started warming 2026-09-20 23:39 UTC. The script needs 21 days, so
   on Oct 11 it refuses them until about 18:40 CT. Plan the apply for that evening.
4. **[C]** Update the inbox list in `config/ids.json` (`instantly.active_inboxes`, 12 today) to the
   inboxes now sending. The reports and the poller read it.
5. Redeploy (3.2), because `config/` is baked into the Modal image.

**Rollback**: the capacity restore, one campaign at a time (see "Backups and restore"), then put
`instantly.active_inboxes` back and redeploy.

---

## Stage 8: the laptop tiers, one at a time [L]

deployment.md step 7. Add one tier at a time to `LAPTOP_LIVE_TIERS` in `.env` (marketing, then ops,
then fulfillment), 24 hours apart. The runner reads it from `.env` only, never from the shell.

- Marketing live means you can apply proposals you have read, one proposal id at a time. That is a
  live Instantly write:
  `MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/inbox_actions/apply_inbox_actions.py --apply --id <proposal id>`,
  run in a terminal where you first ran `set -a; source ~/.advero/live.env; set +a` (Stage 2). Dry-run it
  first with `--dry-run`. The jobs themselves only propose.
- Ops: read deployment.md "Open" first. The laptop's engine keys are stale once the engine runs on
  Modal, so `daily_metrics` and `retro_packet` show old engine numbers.
- The list factory needs two things: `LAPTOP_PAID_JOBS=list_factory` in `.env`, **and** the cost-cap
  decision in `DECISIONS_FOR_LORENZO.md` R14 (was Q-M3). At today's Apify rate a run prices at $0.02267
  per contact against the $0.02 cap (`shared/thresholds.py`, `LIST_FACTORY_MAX_COST_PER_CONTACT_USD`),
  so every run halts before the source fetch and stages nothing. `LAPTOP_PAID_JOBS=list_factory` alone
  therefore stages nothing either. That switch opens its paid calls, live mode or not; it does not gate
  Anthropic spend anywhere else.

**Rollback**: remove the tier from `LAPTOP_LIVE_TIERS` (and `list_factory` from `LAPTOP_PAID_JOBS`).

---

## Backups and restore

Every script that PATCHes a campaign writes its rollback point through `changesets/rollback.py` into
`changesets/backups/`. The unsuffixed file is the rollback point. `.dryrun`, `.prerestore`,
`.not_applied` and `.evidence` files are not restorable; a `.preapply` file means a run died mid-PATCH
(compare it with live first; restore accepts it only with `--accept-interrupted`). Every restore reads
live first, refuses if a field changed after the apply (unless `--override-later-changes`, never with
`--yes`), asks for a typed confirmation and PATCHes only the fields the apply changed. All are [L] and
need `MODE=live ALLOW_LIVE_WRITES=1` on the command line, in a terminal where you first ran
`set -a; source ~/.advero/live.env; set +a` (Stage 2).

| Change | Rollback point | Restore |
|---|---|---|
| Phase 0 copy and settings | `phase0_<campaign_id>_<ts>.json` | `changesets/instantly_phase0/apply_instantly_phase0.py --apply --restore <file> --campaign <key>` |
| Oct 11 capacity (`email_list`, `daily_limit`) | `capacity_<campaign_id>_<ts>.json` | `changesets/capacity/apply_capacity.py --restore <file> --campaign <key>` (no `--apply`) |
| Insurance promotion (`email_list`) | `promotion_<campaign_id>_<ts>.json` | `changesets/capacity/apply_promotion.py --restore <file> --campaign <key>` |
| Inbox action (`email_list`) | `inbox_actions_campaign_<campaign_id>_before_<ts>.json` | `changesets/inbox_actions/apply_inbox_actions.py --restore <file> --campaign <key>` |
| Lead labels | `phase0_lead_labels_<ts>.evidence.json` (a record only) | delete the label by hand in Settings > Lead Labels |
| Subsequence create | `subsequences_before_<ts>.json` (a record only) | delete it by hand in the Instantly UI |
| Webhooks | The ledger `changesets/backups/webhooks_created_ids.json`: the ids `--apply` created (`webhooks_<ts>.json` is only the list before the apply) | **By hand** in Instantly (Settings, Webhooks). While `DELETE_WEBHOOK_VERIFIED = False` in `changesets/instantly_webhooks.py`, `changesets/instantly_webhooks.py --rollback --yes` sends no DELETE: it reads the ledger, lists each id that is still live as NOT deleted, and exits 3. It deletes only once DELETE is confirmed (4.1) and the flag is set to `True`. |

---

## What can and cannot be undone

The fast kill switch is **`python3 -m modal app stop advero-reply-engine`** [L]: every schedule and the
web endpoint stop at once, and both engine stores survive. Details: deployment.md "Rollback".

| What | Can it be undone? |
|---|---|
| The sales tier being live | Yes, but not by a flag. `ALLOW_LIVE_WRITES=0` means seeding the shadow cursor, re-creating the secret and redeploying (deployment.md Rollback step 2). |
| A laptop tier being live | Yes: remove it from `LAPTOP_LIVE_TIERS` in `.env`. The next run is shadow. |
| Sent email and SMS | No. |
| `pipeline_sync` writes: Instantly interest status, and in GHL new opportunities, a value on opportunities that had none, and notes. It never moves a GHL stage. | No restore. The sync's summary lists each interest change as `from -> to`, each opportunity it created and each value it set. Put an interest status back, or delete an opportunity, value or note, by hand. |
| Blocklist entries | No script. Remove them by hand in Instantly. |
| Lead labels | By hand in the Instantly UI. |
| Subsequences and the leads moved into them | Delete the subsequence, or take the lead out, by hand in Instantly. Emails already sent stay sent. |
| `email_list` and `daily_limit` | Yes: the restore commands above. |
| Phase 0 copy and settings | Yes: the Phase 0 restore above. |
| The Modal store | No. The live store is the record of the live period. `cutover.py --reset` refuses once the evidence holds an Instantly or GHL live write. Entries expire after 7 days with no read or write. |
| A2P registration | The registration stays. To stop SMS, set `A2P_10DLC_REGISTERED=0` in `.env`, then get it into the secret. In shadow: `python3 changesets/deploy/modal_secret.py --mode shadow --base-url "$(cat .tmp/deploy/web_url.txt)" --create` (type `CREATE`), then `DEPLOY_TIERS=sales bash changesets/schedules/install_schedules.sh --deploy shadow` (deployment.md Rollback step 2). Once live: the live redeploy in 3.2 (a fresh `--preflight`, then `DEPLOY_TIERS=sales bash changesets/schedules/install_schedules.sh --deploy live`, type `DEPLOY`, then `CREATE`), which re-creates the live secret itself. Never create the live secret by hand (deployment.md step 5). |
| Paid calls | Take `list_factory` out of `LAPTOP_PAID_JOBS`. Money spent is spent. |
| A domain order | No. |
| Stopping the two April Modal apps (`instantly-email-responder-v2`, `instantly-email-responder-test-mode`, 0.1) | Only by redeploying them from git history, which brings the old, committed credentials back into use. Treat the stop as final. |

---

## Housekeeping

- The laptop plists and `crontab.txt` embed the repo's absolute path. If the repo folder moves,
  regenerate them with `python3 changesets/schedules/build_schedules.py` from the new location, then
  unload the old agents and install the new ones (deployment.md step 2c).
- Keep the Mac awake, on power and on Central Time during the watch: launchd fires on local time, and a
  Mac asleep at a due time fails the laptop half of the watch.
