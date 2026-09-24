# Template approvals (CT1)

Goal: you approve each cold-email template once, instead of approving every single email built from it.

Code: `services/reply_engine/template_approvals.py` (the catalogue, hashes, status and kill switch) and `jobs/approve_templates.py` (the command line). The record of what you approved is `config/approved_templates.json`.

## What approving means

Approving a template means every email of that type sends on its own, with no per-email Approve (CT3), with two exceptions that come first (Lorenzo, 2026-09-23, `approval.py` `draft_only`): a first reply is never sent on its own, it is a draft you send yourself from the thread, whatever is approved; and any other reply to a lead no reply of ours has reached yet is a draft too, except a booking confirmation (`booking.confirmation.*`). The safety checks all stay on for every send: the 07:00 to 19:00 CT send window, the slot rules, the offers.md copy gate, the recipient check on the thread, the live-write guard and the kill switch below.

The decision is made by `services/reply_engine/template_gate.py`. An email goes out without a card only when all of these hold, checked in this order: the kill switch is off, the parity check passes, the email was rendered from a template (not polished or edited), every template id it uses is approved at its current text, the text it was rendered from is still the current text, (first replies and booking emails) the reply was classified as interested, a question or a referral, with confidence of at least 0.8, and not by the fallback classifier, the lead did not ask for a time the slot rules refuse, the copy gate passes on the body and on the subject line, and the body is exactly the template with only its placeholders filled. The first check that fails is the reason shown. A reply that fails becomes a normal approval card. A cadence, show-rate or no-show message that fails is held.

"Only its placeholders filled" is strict. Each placeholder must hold the kind of value it is for, or the email is refused as `nonconforming`:

- names (first name, referral name): letters, spaces, hyphens and apostrophes, a period only after an initial, at most 3 words and 40 characters, all in one alphabet. "Mary-Jane", "O'Neil", "J. R.", "José", "Müller", "Zoë" and "Nuñez" pass (letters with accents are still Latin); "The Manager" or a sentence does not, and neither does a Latin name with a letter from any other alphabet in it (a Cyrillic, Greek, Armenian or Cherokee look-alike). The referral first name must be the first word of the referral name.
- specialty, the original subject and other short text: at most 80 characters and 10 words, with no link, email address, phone number, dollar figure or percentage, no "!" or "?", no invisible, control or line-separator characters, and no period followed by a capitalised word unless the period ends an initial or an abbreviation ("J.", "St.", "Co.").
- company names are stricter: at most 8 words, no run of 5 or more digits, nothing after "Inc.", "LLC.", "Ltd.", "Corp.", "LLP.", "PLLC." or "PC." except another of those, and no period followed by any word, capitalised or not, unless the period ends an initial or an abbreviation ("Co.", "St.", "Mr.", "Ms.", "Mrs.", "Ft.", "Pt.", "Assoc.", "Svcs.", "Mfg.", "Ctr." and a few more), and the same one-alphabet rule as names. "Smith & Co. Ltd", "Joe's Janitorial, LLC", "Mr. Rooter Plumbing", "Ft. Worth Roofing" and "Acme Mfg. Co." pass; "Acme Inc. Reply with your password" and "Acme. reply now" do not. The check looks for a second sentence after a period, so a short clause with no sentence-ending period still passes as a company name: "Acme, reply with your card" (6 words, no period) is accepted, and so is a sentence that follows an abbreviation ("Acme Co. Reply with your password"). The limits that do apply are the 8 words, the 80 characters and the no-link, no-number, no-"!" and no-"?" rules.
- times and slots: exactly what the engine's own time formatter writes for a real date and time, such as "Tue, Jan 8 at 12:05pm CT (10:05am PT)" or "4:30pm CT". A made-up time ("Wed, Feb 30 at 1:00pm CT") or free text is refused. Which zones the lead's own time can be in depends on where it comes from. The time the lead proposed, written back in a counter-proposal, is limited to the four `slots.TZ_ALIASES` zones (Eastern, Central, Mountain and Pacific, written ET, CT, MT or PT): any other label, or none, is refused. "Your time" in a booking confirmation is in the zone the lead named in their reply, so it is one of those four too (`slots.detect_tz` answers no other). Only the time in brackets after the Central time in a show-rate or no-show message comes from elsewhere, the GHL contact's own time zone, and there the gate accepts any pytz common time zone or any `US/` or `Canada/` zone name, written exactly as the formatter writes it for that zone ("2:00pm ET", "2:00pm EST", "3:30pm NST"). A wrong time, a made-up zone label or extra words are refused. In a booking confirmation the lead's time must also be the time of the slot beside it, in winter or in summer time. For a zone that changes its clocks on different dates from the US, that check fails in the weeks between the two changes and the email goes to a card. The zones where that happens are Lisbon, the Canary Islands, Madeira and the Faroe Islands (WET), Jerusalem, Morocco, south-east Australia, New Zealand, Macquarie Island and McMurdo. Most of Europe is not affected: the check accepts the time as any zone on the list writes it, and some zone writes CET or EET all year, so the in-between week's time still matches. If one zone name fails to load on the server, it is skipped and logged once. A time that only that zone writes is then refused (a card, or a hold for show-rate and no-show), and every other lead is checked as usual.
- links: https only, with the host written out (no user name, no port): the configured booking link or a GHL booking-widget link (`https://api.leadconnectorhq.com/widget/booking/` and one calendar id, nothing after it) whose calendar id is one of yours: an id under `ghl.calendars` in `config/ids.json` (today only the discovery call), or the id in the configured booking link. A booking link to anyone else's GHL calendar is refused. The gate only reads `config/ids.json`; if it cannot read it, only the configured booking link passes. The call link passes on the Zoom host rule: a Zoom link on zoom.us or a subdomain of it. A `meet.google.com` link (that exact host, no subdomain) passes only when it equals the appointment's own call link, which the show-rate and no-show send paths pass in (`template_gate.appointment_bindings`); a Meet link anywhere else is refused. A configured Loom link also passes. An `http:`, `javascript:` or `data:` link, or a link on any other host, is refused.
- every value must be unchanged by Unicode normalisation (NFKC), so full-width letters and other compatibility characters are refused. Names and company names have the one-alphabet rule above. Look-alike characters, a letter that looks like a dot included, are not refused in the specialty or the original subject line.

Where the send path knows the exact value (the lead's first name, the offered slots, the reschedule link), it passes it in (from the CT3 integration phase), and the value in the email must match it exactly and still pass the check for its kind above: passing a value in only narrows the check. A reschedule link on another host is refused whether it was passed in or not. The one exception is the appointment time: the show-rate and no-show send paths can pass in the time the engine's own formatter wrote for that appointment (`template_gate.appointment_bindings`), and then exactly that value passes, even for a lead zone outside the list above. The fixed fallback wordings an entry already contains ("there", "your business") are accepted in their placeholder when no value is passed in for it. No wording is accepted in place of the call link: with no link on file the show-rate and no-show messages use their own `no_call_link` variant. There are 17 of them, listed in `services/reply_engine/tests/test_template_gate_values.py` (`EXPECTED_FALLBACKS`); a test fails if one is added or removed.

The approve command prints that note every time, and when you approve from your terminal it warns that, once CT3 phase 2 is deployed, the templates auto-send with no card while the kill switch is off. The gate is built, and CT3 phase 2 wires the send paths to it. The cadence ladder asks it on every touch (see "Cadence holds, stalls and resume" below). Until phase 2 is deployed, the app running on Modal still follows the old rules.

Each template is recorded with a sha256 of its exact text. The text you approve is the whole block the review document shows for that id, not just the main template. That block also includes every variant the same email can go out as:

- missing lead data ("Hey there,", "your business", no referral name)
- no call link on file (`no_call_link`: the message says the link is on the calendar invite), no Loom URL (`no_loom_url`), or neither (`no_call_link_or_loom`)
- no free slot, or only one
- a lead in another timezone
- the dated form of a counter-proposal
- the fallback subject line
- how times and slots are written (the `value_formats` block, on every template with a time or slot in it): the engine's own formatters at fixed example times, such as `Tue 12:05pm or Thu 4:30pm CT`. The block is the same on every such template.

A change to any of that wording, in code or in a prompt file, changes the hash. That includes the way times are written: a change to a time or slot formatter (the "or" between two times, "CT", the date format) sends every template with a time or slot in it back for approval.

What is not covered: a first reply after the LLM polishes it and any body you edit by hand on a card always go through a card. An E2 follow-up (`cadence.e2`) with a per-lead LLM research line is always held; by default E2 uses the fixed fallback line (`cadence.e2.research_fallback.<offer>`), which you can approve. `booking.slot_already_taken` is always a card. A first reply that accepts the time the lead asked for with no booking behind it (the `confirmed_time` variant: "... CT works on my end, I will send the invite over") is always a card too, even when its id is approved, because the gate cannot know an invite was actually booked. Booking confirmations (`booking.confirmation.*`: "Locked in ..., invite on the way") are different: once approved they send on their own, after the classification check. The E2 research line (`cadence.e2.research_line`) cannot be rendered for review by design, so it is never approvable; the Google Doc shows it only as a read-only note on Follow-up email 2. The review document's last section lists the other exclusions.

## Approving, step by step

Approvals come from your own terminal, with one exception. This is a permanent rule: a Claude session must never run `--approve`, `--approve-all-shown` or `--revoke`, and must never write `config/approved_templates.json` in any other way, except this one (Lorenzo's rule of 2026-09-23): after Lorenzo types "done" in chat about the one Google Doc, the section 4 chat may run `tools/template_doc/record_doc_approvals.py --write` on that doc's export, with `--doc-id` of that doc and his exact words as `--done-quote`, as described in "From the Google Doc" below. That tool only adds or refreshes approvals for templates the doc showed unchanged; it never revokes and never touches the kill switch. Nothing else a Claude session does may write the registry. The terminal command refuses without an interactive terminal, but that check is not bulletproof (a pseudo-terminal wrapper gets past it).

The real protection is the registry file itself. It is committed to git, and you review it with `git diff -- config/approved_templates.json` (run from the `Agentic Worklfows` folder) before every commit. `git diff` only shows changes to a file git already tracks, so the empty registry has to be committed first. Treat any approval record you did not make yourself as an incident. The live-write guard (`.claude/hooks/guard_live_writes.py`, rule d) also blocks the approve and revoke commands and commands that name `config/approved_templates.json`, but it is only a tripwire. It does not block `tools/template_doc/record_doc_approvals.py --write`: it denies only when the command text names the registry file or the approve and revoke modes, and the recorder writes the registry from inside Python. You still have to apply it from your own terminal (`changesets/claude_guard/README.md`); until then it does not run in sessions started from `Coding/` or any other folder. Even applied, it reads command text, so it cannot catch an arbitrary script, code decoded at run time, or a git command with no path (`git stash`, `git reset`).

1. Export the review document:

   ```bash
   cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
   python3 jobs/approve_templates.py --export .tmp/templates_for_approval.md
   ```

2. Read it. Paste it into a Google Doc if that is easier to review or comment on. Every template has an id, its status, its variables, where it is sent from, and a text block with every variant.
3. If you want wording changed, that is a code or prompt change, not an approval. Make the change, export again and read the new file.
4. Approve exactly what you read, from your own terminal:

   ```bash
   python3 jobs/approve_templates.py --approve-all-shown .tmp/templates_for_approval.md
   ```

   Type `APPROVE` when asked. The whole file is refused in any of these cases:
   - a text block was edited in the file after export;
   - a marker has no text block;
   - any template changed in the code since the export.

   Nothing is written in that case. Re-export and review again.
5. To approve a few ids instead of the whole file: `python3 jobs/approve_templates.py --approve cadence.e1 cadence.e3`. First read each one with `--show <id>`.

`--list` prints every id with its kind and status. Every approve and revoke run writes a Job_Log row (job `approve_templates`) with the ids and hashes, never the text.

## From the Google Doc ("done")

Lorenzo's rule of 2026-09-23: when he types "done" in chat about the one Google Doc, everything in the doc counts as approved. That word replaces the terminal approve step for the doc. It is the one case where a Claude session writes `config/approved_templates.json` (see "Approving, step by step"): only with `tools/template_doc/record_doc_approvals.py`, only after his "done" in chat, only for the doc he said it about, and only with his exact words passed as `--done-quote` (they must contain "done"). "Go live" is a separate yes and is not part of this.

The principle: a template is approved only if Lorenzo could see every part of its hashed text in the doc he said "done" on, he changed and commented on none of it (anywhere in the doc, not only in the email bodies), and the code still renders exactly that.

### Builds, uploads and the fingerprint

`tools/template_doc/build.py` builds the doc from `jobs/approve_templates.py --export` output. Every build has a fingerprint (a hash of every block's tag, text and template hash, plus every line outside the block bodies). It is printed in the doc as the line `Doc build: <fingerprint> (tag: X-BUILD)` at the end of the top section, and it names the build folder `tools/template_doc/builds/<fingerprint>/` (html and manifest). `tools/template_doc/uploads.json` records which Google Doc holds which build. The top-level `manifest.json` and `advero_all_emails.html` are the build of the doc currently in Drive. Today that is the doc `1jTg1ccYJT8CugDdCf3BQHqzgHUKC4oFG9rgolUILO4U`, uploaded 2026-09-23T17:59Z, which predates fingerprints: it can be diffed and dry-run, but never approved from. To approve from a doc, upload a fingerprinted build first (`tools/template_doc/README.txt`, "Upload and promote").

The build shows every part of every template's hashed text: the main text; the subject line and its fallback subjects (a note); the full time formats block (`formats.1`, one tagged block per distinct text) that every template with a time depends on; and every variant as the changes it makes to the main text. Each change is a grey note that quotes, word for word, the main-text lines it replaces or leaves out (`Instead of "A" and "B":`, `Leaves out "A".`) or the line it adds after or before, followed by the lines it puts in; the forms are in `tools/template_doc/doc_rules.py`. The dated and other-timezone variants that write out example times are shown in full instead (Lorenzo's choice, 2026-09-23), so every example hour, date and zone label is in the doc. A variant that is exactly two others together is one note, one the change notes cannot say exactly is shown in full too, and a missing-data variant is left out only when it is exactly the fallbacks the top section states. Before writing anything, the build reads every template back out of the doc's own text (`doc_areas.DocReader`) and stops, writing nothing, unless every part comes back exactly. So a code change to any part changes the doc, and the doc Lorenzo said "done" on determines every text it approves.

The layout comes from the catalogue, not from lists in the tool: every approvable id in the catalogue's order, by section, each follow-up email (`cadence.e1` to `cadence.e10` today) with the lines spliced into it right below. So ids a section adds or drops need no change in the tool; the build stops unless the doc holds every approvable id exactly once. A catalogue entry that is not approvable is never a tagged block: `cadence.e2.research_line` (written by AI for each lead) is a read-only note on Follow-up email 2, and "done" never approves it. The doc says how approved emails go out, as the engine's locks do: first replies are drafts Lorenzo sends himself from the thread; other replies go out on their own only after a reply of his reached the lead, except the Locked in booking confirmation.

### When and how

The section 4 chat, right after Lorenzo says "done" about the doc. The chat runs in its worktree, so point the Job_Log at the main folder's log (the job log uses `JOB_LOG_PATH`) or the row stays in the worktree's `.tmp/`:

1. Read the doc's open comments and suggestions: Drive `read_file_content` with `includeComments: true`, and open the doc itself to look for suggestions. Suggestions are in neither export (not in text/plain, and a real Drive text/html export showed none), so this step is the real control for them; the tool's HTML check for suggestion markup is best-effort only. If any comment or suggestion is open, stop and ask Lorenzo; do not run `--write`.
2. Export the doc twice, as plain text and as HTML (Drive `download_file_content` with `exportMimeType=text/plain`, then with `exportMimeType=text/html`; see `tools/template_doc/README.txt`), and save them as `tools/template_doc/exports/<UTC time>.txt` and `.html`. The HTML keeps what the text drops: strikethrough, highlights and text colours (grey counts only where the build itself made text grey: tags, notes, labels, section markers). It does not show suggestions (step 1 covers those). The doc's top section asks Lorenzo to type changes straight in, without any of these.
3. Dry run (writes nothing, prints the plan; exits 1 when `--write` would refuse the whole doc):

   ```bash
   cd "<worktree>/Agentic Worklfows"
   export JOB_LOG_PATH="/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows/.tmp/job_log.csv"
   python3 tools/template_doc/record_doc_approvals.py tools/template_doc/exports/<UTC time>.txt --html tools/template_doc/exports/<UTC time>.html
   ```

4. Record the approvals, with the doc's id and his exact words. `--checked-comments` says step 1 found no open comment or suggestion, and `--html` is the HTML export of step 2; without either, `--write` refuses and writes nothing:

   ```bash
   python3 tools/template_doc/record_doc_approvals.py tools/template_doc/exports/<UTC time>.txt --write --doc-id <doc id> --done-quote "<his exact words>" --checked-comments --html tools/template_doc/exports/<UTC time>.html
   ```

5. After a write the tool says what an approval does (first replies stay drafts Lorenzo sends himself; other replies auto-send only once a reply of ours reached the lead, booking confirmations excepted) and ends by printing the command `git diff -- config/approved_templates.json`. Run it, show Lorenzo the output, and commit, quoting his words in the commit message. `approved_by` on every new record carries his quote and the short build fingerprint, so the diff shows which "done" it came from.

### How a template qualifies

The export's `X-BUILD` line names its build; `builds/<fingerprint>/manifest.json` must exist and hash to that fingerprint, and the build's HTML next to it must be that manifest's doc. With `--write`, `uploads.json` must map `--doc-id` to that fingerprint, and no other doc to the same fingerprint. The export is compared with that build, and the build with a fresh build of the current code (made in a temp folder by `tools/template_doc/fresh_manifest.py`). A template is approved only when all of these hold:

- every block of it (main text, subject, every variant) and its time formats block are in the doc unchanged; differences Google makes on its own (curly quotes, non-breaking spaces, a doubled blank line, runs of spaces) do not count, but a paragraph break added or removed does;
- every block of it is where the build put it: a version or Subject line moved under another email refuses both emails;
- its heading, variant labels and notes (fallback subjects, the change notes with the lines they quote) are unchanged and each note is still where it was in its block, and no line changed or was typed outside the emails in its section;
- no new block tagged for it was added (a tag that starts with its id and `/` or `.`);
- none of the words it shows was edited elsewhere in the doc: the doc says "changing it once is enough; it changes everywhere", so a line or sentence an edit removed from a block, or a quoted line, written-out spliced line or fallback subject an edit removed from a note, refuses every template that shows it, in a block or in a note. There are no exemptions: a greeting, the sign-off, a sentence that is only a placeholder and a sentence most emails share count too (editing "Hey {first_name}," once refuses almost every email). A deleted version or Subject line counts only for the words the email's main text no longer has. The templates `tools/template_doc/route_doc.py` lists under "also appears in" are refused as well;
- its text, read back out of the doc's build and out of a fresh build of the current code (`fresh_manifest.readback_mismatches`), hashes to its template hash;
- for a follow-up email with spliced lines (`cadence.e2`, `e4`, `e5`, `e6` and `e9` today; the pairs are read from the catalogue's ids), the email and all its lines are unrefused;
- it is not a first reply: every `first_reply.*` id, main text and every variant, is refused as held (`R_HELD`, `doc_rules.is_held` in `tools/template_doc/doc_rules.py`). Lorenzo decided on 2026-09-24 that first replies stay drafts he writes himself until they are rebuilt from his own replies, and the doc marks each one "Not approved yet";
- it is approvable in the catalogue: an entry that is not (`cadence.e2.research_line`, the first-reply reference pieces) is never recorded;
- its hash in the doc's build equals its hash now, and the doc's build shows it exactly as a build of the current code would; the catalogue hash is checked again just before writing.

The hash recorded is the current catalogue hash, the same value `--approve-all-shown` would record.

### What gets refused, and why

- An edited or deleted block, heading, label or note (a change note's quoted lines included), or a note moved within its block: Lorenzo wants words the code does not send yet. The owning section changes the code first (`tools/template_doc/route_doc.py` says which section and file), a new doc is built and uploaded, and the template is approved on the next "done".
- Other templates with the same block text or a sentence the edit changed or removed (the repeat rule), and follow-up emails with their spliced lines: refused together with the edited one. An edit to the read-only research-line note refuses Follow-up email 2 and its lines.
- Every first reply (`first_reply.*`, every id and variant): refused as held, never approved from the doc (Lorenzo, 2026-09-24: first replies stay drafts he writes himself until they are rebuilt from his own replies).
- Code changed since the doc was built, or during the run: build and upload a new doc.
- The whole doc, with nothing written: a doc without a build fingerprint (`this doc predates build fingerprints; rebuild and re-upload`), a `--doc-id` that `uploads.json` does not map to the export's build, a build `uploads.json` maps to more than one doc, anything the HTML export shows (struck-through, highlighted or coloured text the build did not set, suggestion or comment markup, or an HTML file that is not the same doc as the text export), duplicate tags, copies of one sentence changed differently, a change in the top section or outside the engine sections (Instantly headings and notes, the closing section, the build line), a tag that matches no email, a doc with no tags, or a fresh build that fails.

A refused template keeps whatever approval it had: the plan says it "keeps its earlier approval, which still matches the code" when it does. The tool only adds or refreshes approvals, never revokes, and never touches the kill switch (`auto_send`). It writes through the registry's own `plan_approve` (with the fresh hashes as `expected`) and `apply_approve`, so the records have the same format as the terminal path's. One Job_Log row per `--write` run (job `approve_templates`, action `approve_from_doc`): the doc id, the build fingerprint, the sha256 of the build's manifest and of the export, the HEAD commit, the approvals file path, the quote, `checked_comments`, the ids and hashes approved and the ids refused with their reasons. Instantly blocks are not approvals: the tool counts the unchanged and changed ones, and changed ones go through `changesets/instantly_copy/`.

The terminal path above (`--export`, `--approve-all-shown`, `--approve`, `--revoke`, typed `APPROVE`) is unchanged and still the only way to revoke.

## Statuses

- `approved`: the current text, every variant included, hashes to what you approved.
- `changed_since_approval`: you approved it, but the wording has changed since. It is treated as not approved and goes back to a card until you approve the new text.
- `unapproved`: never approved, or revoked.
- `unknown_id`: no such template.

## Revoking

```bash
python3 jobs/approve_templates.py --revoke cadence.e1
```

From your own terminal, type `APPROVE`. That template goes back to per-email cards.

## Kill switch

Either of these stops every template auto-send at once, whatever is approved:

- Environment: `AUTO_SEND_TEMPLATES` set to anything other than `1`, `on`, `true` or `yes` (for example `0` or `off`). An empty value (`AUTO_SEND_TEMPLATES=`) is off too, on the laptop and on Modal: the secret builder sends it as `off`. On Modal it is an optional key of the secret (`runbooks/deployment.md` step 2a), so re-create the secret to change it there.
- File: `"auto_send": false` in `config/approved_templates.json`. Any value other than the JSON literal `true` counts as off. A file that cannot be read also counts as off.

Neither switch is instant on Modal:

- The environment switch reaches only new Modal containers. A container that is already running keeps the value it started with until Modal replaces it.
- `config/` is mounted into the Modal image at deploy time, so a change to the approvals file reaches Modal only on the next deploy.

For an immediate stop, run `python3 -m modal app stop advero-reply-engine` from your own terminal (`runbooks/deployment.md`). That stops every schedule and the web endpoint, not just templates. A Claude session does not run it for you. Then set the kill switch and redeploy before starting the app again.

## Approve the ladder templates before deploying CT3

Once the CT3 integration phase is deployed, a cadence, show-rate or no-show message whose template is not approved is held, not sent. Deploying before you approve them would hold every reminder and every cadence touch. So approve the ladder ids first:

1. Export and read the review document (steps 1 to 3 above). The ladder ids are the `cadence.*`, `show_rate.*` and `no_show.*` sections, including the lines spliced into E2, E4, E5, E6 and E9.
2. Approve them from your own terminal with `--approve-all-shown` (or `--approve <ids>`).
3. List what is still unapproved:

   ```bash
   python3 changesets/deploy/template_parity.py --report-unapproved
   ```

   It prints ids only. The first three lines are:

   - `UNAPPROVED LADDER IDS: <count>`: ladder ids not approved at their current text (listed next);
   - `UNEXTRACTABLE LADDER IDS: <count>`: ladder ids the catalogue could not render (a code bug to fix; listed separately);
   - `KILL SWITCH: on` or `off`.

   It exits 0 when it could build the report and 2 when it could not (for example an unreadable approvals file). The deploy preflight (`install_schedules.sh --preflight`, step 8) runs it, prints the report, warns when the kill switch is on (every cadence, show-rate and no-show message would be held), and asks you to type `HOLD` to deploy while either count is not 0. Those messages are held until approved; a show-rate or no-show message whose send time passes while it is held is dropped. Any malformed line or a failed run stops the preflight.

Booking emails can be approved later, a few at a time. Until one is approved, that email stays a card.

First replies are not approved from the doc at all: when you say "done", the recorder refuses every `first_reply.*` id and variant as held (`R_HELD`). Reason: Lorenzo's decision of 2026-09-24 that first replies stay drafts he writes himself until they are rebuilt from his own replies. Each one stays a card you send yourself from the thread.

Approving the counter-proposal ids (`booking.counter.*`) rarely changes anything: a counter usually answers a lead who asked for a time the slot rules refuse, and the gate keeps those as a card (`requested_override`) whatever is approved.

## The kill switch now also holds cadence, show-rate and no-show

The kill switch (above) stops every template auto-send, not only replies. With it on, replies become cards, and cadence, show-rate and no-show messages are held. That includes the show-rate reminders before a booked call, so a kill switch left on costs show rate. A held show-rate message that passes its latest send time is dropped, not sent late.

A cadence touch held by the kill switch is not lost and its ladder is never stopped for it: the day is retried every tick and goes out late, on the first tick after you turn the kill switch off, under the usual send window and D1 Veto rules. The same goes for the other holds that cover every ladder at once: a parity failure and a catalogue or approvals file the gate cannot read.

## Cadence holds, stalls and resume

A cadence day whose email the gate refuses is held: nothing is sent, the day is not advanced, and the digest says why once a day (again the same day only if the reason changes). What to do depends on the reason, and the digest line and the stop push say which:

- `kill_switch`, `parity_failed`, `registry_error`: a hold on every ladder at once. Nothing to approve. Turn the kill switch off, fix parity (`template_parity.py --check`, then redeploy) or fix what the gate could not read (see `/health`). These holds never count toward a stall, never reset its count and never stop a ladder.
- `unapproved`, `changed_since_approval`: approve the ids with `jobs/approve_templates.py`.
- `nonconforming`, `copy_gate`: approving changes nothing. A value of the lead's (the first name, the company or the thread subject) does not fit the placeholder rules above, or the copy check refused it. Fix the lead's record, or answer the lead by hand.
- anything else (`unknown_id`, `not_approvable`, `stale_render`, ...): the id cannot be auto-sent as it stands; the code or the catalogue needs a fix.

D1 has one more rule. In live, before the 30-minute Veto window opens, the engine runs the full check on the exact subject and body D1 would send, with the lead's values filled in. If it fails, you get no "sends at" ping; the day is held and reported like any other. After a refused check the window opens again only once something the check looks at has changed (an approval, the lead's name, company or subject, the template, the catalogue, or the gate's own rules: a deploy that changes a rule bumps `template_gate.GATE_RULES_VERSION`), or once you press Resume on the stopped ladder, and then as a fresh, full 30 minutes before anything is sent. Resume drops the old refusal, so the next tick runs the full check afresh: a pass opens one fresh window, and a refusal (before the window or at send time) is recorded again, so the window does not re-open on every tick. A rule relaxed by a deploy that did not bump the version leaves a held D1 held until one of those happens. A D1 whose copy check fails opens no window either; it is reported as blocked copy when it falls due.

The stall counts business days. Each business day on which the day was held for a reason other than the gate-wide ones counts once, whatever the reason, and the reasons can come in any order. A gate-wide hold in between neither counts nor resets the count, so an approval hold after a kill-switch pause continues the count it had before the pause. The count belongs to the held day: it starts again only when that day is sent, or the ladder is re-armed or resumed. Once the day has been held on 3 business days that count, the next tick that holds it for a reason that counts stops the ladder as `template_unapproved` (with holds on consecutive days, that is the fourth day). A tick held for a gate-wide reason never stops it, however long ago the first hold was. You get one push, worded for the reason that stopped it. The day, the reason, the ids and what to do are always on ntfy. The lead and a signed Resume link, valid 48 hours, go only where they may:

- on a protected ntfy topic (NTFY_TOKEN set, or NTFY_ALLOW_SENSITIVE=1): in the push itself, as text and as a Resume button (the email leg, when it is set too, gets the same text);
- on a public topic with the email leg set (NOTIFY_EMAIL, GMAIL_SENDER_EMAIL, GMAIL_APP_PASSWORD): on the email leg only, with no names, emails, companies or links on ntfy;
- on a public topic with no email leg: nowhere. The push says no channel can carry the link and what to set (NTFY_TOKEN, or those three email keys, in `.env`, then redeploy: `runbooks/deployment.md`, step 2a). No link is recorded or reported as sent, and the first tick after a channel exists sends one.

While the ladder stays stopped, a fresh Resume link is sent the same way on the first tick of every day, so there is always a live one. For an `unapproved` or `changed_since_approval` stop, a link also comes as soon as the held ids pass the gate, with "ready to resume" in the title. Neither comes once the lead opted out, was blocklisted, booked, or answered hostile, lost, wrong person or not now: a Resume would stop the ladder again at once. Without BASE_URL or REPLY_ENGINE_SECRET no link can be signed; the push says so, and the link comes on the next tick after you set them.

To resume: fix the cause, open the newest Resume link, check the page (for an approval stop it says whether the held ids pass the gate now) and press Resume. Nothing is sent from the page. The next tick runs the template gate and every send check again (opt-out, lead reply, open card, send window, recipient check, slot rules) and sends the held day only if all of them pass; a D1 first opens a fresh 30-minute Veto window. If the cause is not fixed, the day is held again and, 3 business days later, stopped again.

## FYI push

Emails that go out without a card are not silent. `template_gate.py` keeps the queue for it: one line per auto-sent email (the kind, the template id, the card id, the status and the send time; never the text), and a count of held messages per template id. The CT3 integration phase wires the send paths to fill it and adds the push that drains it every 30 minutes:

- the ntfy push carries counts per template id only, with no names, emails, subjects, bodies or links, because the ntfy topic is public;
- the email leg can carry one line per lead with a Veto link for anything still queued;
- if the push fails, the batch is put back and goes out with the next one.

The queue keeps at most 500 lines; beyond that the oldest are dropped (and logged).

## Parity check

The deployed app on Modal runs Python 3.11 and your laptop runs 3.9. If the catalogue renders differently there (a time formatter, a library version), the hashes would differ and nothing would match what you approved. The parity check catches that as one clear failure instead of many silent ones.

- `python3 changesets/deploy/template_parity.py --write` writes `config/template_catalogue_hashes.json`: the digest of every approvable template's hash, the id-to-hash map, and the python, pytz and pydantic versions it was built with. Ids and hashes only.
- `--check` rebuilds the catalogue and exits 1 with the ids that differ.
- Both run in the deploy preflight (`install_schedules.sh --preflight`, step 7). Run them from your own terminal; the script never writes `config/approved_templates.json`.
- `config/template_catalogue_hashes.json` is not in git until you commit it the first time: the first `--write` creates it as a new, untracked file. After that first commit, every preflight rewrites it and leaves it changed in git (at least its timestamp). Commit it with the code it was built from.
- If the app is still loading its modules when the catalogue is asked for, the parity check reports `not_ready`: auto-send is off for that moment, every email becomes a card or a hold, and no alert is sent.

`config/` is mounted into the Modal image, so the reference reaches the app with the code. The app compares its own catalogue with it. On a mismatch, a missing reference or an error, template auto-send is off everywhere (every email becomes a card or a hold) and you get one urgent push a day with the status and the ids, never text. `/health` reports it under `templates.parity` once the CT3 integration phase wires the templates block in, and `changesets/deploy/verify_health.py` fails the deploy when it is not `ok`. The one exception is `not_ready` (the app is still loading its modules): `verify_health.py` polls again, 5 seconds apart, within the same attempt budget it uses for a slow cold start (`--attempts`, 4 by default), and fails only if parity is still `not_ready` after the last attempt. A missing `templates` block, `mismatch`, `reference_missing` or `error` fails at once.

To fix a mismatch: run the preflight again on the code you are deploying, and redeploy.

If the mismatch comes back after a fresh preflight and redeploy, the laptop and Modal render some template differently, so redeploying again will not help. The laptop already runs the same pydantic (2.12.5) and pytz (2023.3) as the Modal image, which installs `services/reply_engine/requirements.txt`; the pydantic 2.5.3 pin in the top-level `requirements.txt` is not what either one runs. So the real difference today is Python: 3.9.6 on the laptop against 3.11 in the image. That difference has been checked: on 2026-09-23 a local Python 3.11 rendered every approvable template of the catalogue of that time (111) exactly as the laptop's 3.9.6 does (fastapi was stubbed out). The check was repeated later that day on today's 108 templates, with the laptop's own fastapi, starlette and anyio on the 3.11 path: the same 108 ids and the same digest (392b01cd05449198). The Modal image itself was not tested; the parity check in the preflight catches any difference.

If the differing ids are the three `booking.already_booked.*` ones, the likely cause is that `services/reply_engine/app.py` could not be imported where the reference or the app's own catalogue was built, for example because a dependency such as fastapi is missing there, which leaves those three templates with no text. Check that environment's imports first. On Modal, a failed import makes `/health` answer `"app": "missing"` with the error in `detail`. On the laptop, with the `python3` that wrote the reference, `python3 jobs/approve_templates.py --show booking.already_booked.awaiting_approval` prints "app.py could not be imported here" and the error when the import fails there.

For any mismatch that a Python or library version difference causes (after an upgrade on one side, for example), either run the whole preflight and the deploy (`install_schedules.sh --preflight`, then `--deploy ...`) from one shell whose `python3` is Python 3.11 with the image's requirements (`services/reply_engine/requirements.txt`) plus `modal` and `pytest`, which the preflight and the deploy also use. Step 7 rewrites the reference with whichever `python3` runs it, so a reference written any other way is overwritten by the next preflight. Export, review and approve the templates from that same environment too. An approval stores each template's hash as the approving environment renders it, and Modal compares that with its own. An approval made under 3.9 reads as `changed_since_approval` on Modal for every template that renders differently there, and `--approve-all-shown` refuses a review file exported in a different environment when any template in it renders differently between the two. Or report the differing ids from the alert so the formatter can be fixed in code. Until the mismatch is fixed, auto-send stays off: every reply is a card and every cadence, show-rate and no-show message is held.

## Rollback

Revoke the ids, or restore the previous `config/approved_templates.json` from git (`git checkout -- "Agentic Worklfows/config/approved_templates.json"`). The empty registry is `{"version": 1, "approvals": {}}`. For an immediate stop, set the kill switch first and roll back after.
