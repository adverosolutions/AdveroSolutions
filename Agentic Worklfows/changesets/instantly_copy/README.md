# Instantly copy change-set (edits made in the one Google Doc)

Turns Lorenzo's edits to the 6 live Instantly cold campaigns, made in the one Google Doc
(`1jTg1ccYJT8CugDdCf3BQHqzgHUKC4oFG9rgolUILO4U`), into a staged, dry-runnable
`PATCH /campaigns/{id}`. Nothing here touches live Instantly unless `MODE=live` and
`ALLOW_LIVE_WRITES=1` are both set and one campaign is named.

**The rule:** the live apply happens only after Lorenzo says **"done"** on the doc (the edits are
final) and then, separately, **"go live"** for the push. "done" is not "go live". Never set the live
flags on his behalf.

## Files

| File | What it does |
|---|---|
| `build_from_doc.py` | Offline. Diffs a Drive text export against `tools/template_doc/manifest.json` (with `parse_doc.py` + `diff_doc.py`), keeps only `instantly.*` changes, checks them, and writes the staged folder. |
| `apply_instantly_copy.py` | Verifies the staged folder, then dry-run (default), guarded one-campaign apply, or `--restore`. |
| `copy_lib.py` | Doc text to Instantly HTML, the copy rules, the doc-structure check, the manifest baseline, the drift check, the variant swap. Reuses `phase0_lib` (`text_to_html`, tag parser, offers.md figures, `sequence_diff`), `copy_validator.variables_inside_spins` and `changesets/rollback.py`. |
| `staged/<export stem>/` | Output of a build: `staged.json` (tool marker, export / manifest / snapshot paths and sha256, doc id, built_at, every change with old and new text) and one `<campaign_key>.json` per edited campaign. |

## Commands

```
cd "Agentic Worklfows"

# 1. stage (offline). Exit 0 = staged or nothing to stage, 1 = refused (nothing written)
python3 changesets/instantly_copy/build_from_doc.py tools/template_doc/exports/<export>.txt

# 2. dry-run: verify the staged folder, GET each staged campaign, drift check, text diff, exact PATCH body
python3 changesets/instantly_copy/apply_instantly_copy.py --staged changesets/instantly_copy/staged/<export stem>
python3 changesets/instantly_copy/apply_instantly_copy.py --staged DIR --from-snapshot   # offline

# 3. apply, one campaign, only after "done" AND "go live"
MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/instantly_copy/apply_instantly_copy.py \
    --staged DIR --apply --campaign cleaning_reactivation
```

`--out` must be inside `changesets/instantly_copy/staged/` (or the system temp dir, for tests).
`--overwrite` replaces only a folder whose `staged.json` carries `"tool": "instantly_copy/build_from_doc"`,
and deletes only that `staged.json` and the campaign files it lists; any other folder is refused.

## What the build refuses (nothing is written; nothing is "fixed")

- an `instantly.*` tag missing from the doc (deleting a step from the doc is not supported),
  an unknown tag starting with `instantly.`, or any duplicate tag. Unknown tags that do not start
  with `instantly.` (for example a build fingerprint line) are ignored;
- a note for Claude inside an email (a line with `(note)` or starting with `NOTE`, the doc router's
  rule), any `(tag:`, `(section)` or `(note)` fragment, or a line that is one of the doc's own
  layout lines (headings, section titles, notes, taken from the manifest and from
  `tools/template_doc/drive_export.txt`): that is what happens when a grey marker is deleted and
  the structure line runs into the copy. Lines already in the live copy are exempt;
- a dash other than a plain hyphen (em, en, figure, minus, horizontal bar, small em dash and others)
  or `--`; `!` in any form (full-width, emoji, `‼`); a mention of AI/automation;
- an engine-style single-brace placeholder such as `{first_name}` (Instantly only fills
  `{{firstName}}`), unbalanced `{{` / `}}`, a merge variable inside a spin
  (`{{RANDOM | Hey {{firstName}} | Hi {{firstName}}}}` ships the literal tag), a spin with fewer than
  two options, an empty option or a repeated option, a `{{variable}}` the campaign does not have;
- a subject added to step 2 (it would break the thread) or removed from step 1, an empty body;
- a newly added dollar figure, promised time window or (reactivation) guarantee that is not in
  `config/offers.md`. Only promise shapes count as windows ("in 30 days", "within 14 days",
  "90-day"); "3 days ago" or "next 2 weeks" do not. The check fails closed: no readable offers.md,
  or a campaign without an `offer` in `config/ids.json`, refuses the build;
- copies of one shared sentence edited to different texts; a manifest that disagrees with its
  snapshot; a campaign id that disagrees with `config/ids.json`.

Warnings (staged anyway, printed): curly quotes, non-breaking spaces, `…`; `{{ firstName }}` with
spaces inside the braces; `[first_name]`-style brackets; a `{{variable}}` the old text had and the
new one drops. Whitespace/quote-only edits are listed and not staged (Instantly keeps the old text).
phase0's validators (`validate_sequence`, `copy_validator.validate_copy`) are not used whole: they
judge a 3-step A/B sequence with 3 to 5 spin points, which the live 2-step, 1-variant campaigns are not.

## Shared sentences

The doc tells Lorenzo that a sentence repeated across emails changes everywhere when he edits one
copy. The six step-1 subjects are one such sentence (one `text_group`): editing one stages the same
subject for all six campaigns, and the build output and `staged.json` (`propagated_from`) say which
edit each copy came from. Two copies edited to different texts are refused. Blank texts (the step-2
subjects) are not treated as a shared sentence.

## How the text becomes HTML

Drive's export writes every paragraph gap as two blank lines; the build collapses blank runs to
one (this gives exactly the manifest text for all 12 bodies) and then uses `phase0_lib.text_to_html`.
Only an edited variant is regenerated. `text_to_html(manifest text)` reproduces the live
`raw_html` for 8 of the 12 bodies but not for 4: cleaning_trigger, bookkeeping_trigger and
recruiting_reactivation step 1 carry trailing `&nbsp;`, and bookkeeping_reactivation step 1 has a
`<br />` inside a line. So every unedited step and variant is copied from the baseline byte for byte,
and an edit to one of those 4 bodies also changes its formatting. The build and the dry-run label
it: "formatting-only change: trailing non-breaking spaces removed" or "a line break inside a line
becomes a blank line of its own (renders the same)". Links, bold and other formatting typed in the
doc are not carried over: the export is plain text.

## Verification of a staged folder (dry-run and apply, before any GET)

The recorded export, manifest and snapshot must exist and match their sha256 in `staged.json`, and
re-running the build's `plan()` on them must reproduce every staged file byte for byte. A folder
edited by hand, even consistently, a moved or changed export, or a change with an out-of-range step,
a negative index or a field other than body/subject is refused with exit 1 and no request. Keep the
export file for as long as the staged folder may be applied.

## Drift check (dry-run and again on the fresh GET before an apply)

The baseline is the manifest (`raw_html` / `raw_subject`, delay and delay_unit) plus the snapshot's
step types, rebuilt from the verified sources, never read from the staged files. Live must match:
the same step count, each step's `type`, `delay` and `delay_unit`, the same variant count, and every
variant's subject and body (an edited field may also already hold the staged value; any third value
is drift). Otherwise that campaign is refused and the difference printed, because applying would
silently overwrite an edit made in Instantly after the doc was made. If the Phase 0 change-set
(`changesets/instantly_phase0/`, 3-step A/B sequences) is applied first, every campaign it touched
drifts; make a fresh doc from the new live copy. Applying Phase 0 AFTER this change-set overwrites
these edits with Phase 0's staged copy.

## Apply

One campaign at a time. Refused (exit 2) unless `settings.is_live()`, and refused together with
`--dry-run` or `--from-snapshot`. Order: read live, drift check, print the diff and the PATCH, ask
for the campaign key typed back (unless `--yes`), read live again and refuse if the sequences moved
while the prompt was open, write the before-image
`changesets/backups/instantly_copy_<campaign_id>_<ts>.preapply.json`, then send one PATCH holding
only `{"sequences": [...]}`, built from the LIVE sequences with only the edited variants'
subject/body swapped (so `v_disabled`, `pre_delay_unit` and any other live-only key survive),
through `rollback.patch_and_settle` (`Instantly.update_campaign`, so `guard_write` runs inside). The
before-image then becomes the rollback point `instantly_copy_<campaign_id>_<ts>.json`, also after a
PATCH error. When live already equals the target nothing is sent and no backup is written. An edited
variant that is switched off in live (`v_disabled`) is warned about. Editing a step-1 subject while
leads are mid-sequence can split threads: step 2 replies in the thread of the subject each lead got.

## Rollback

```
MODE=live ALLOW_LIVE_WRITES=1 python3 changesets/instantly_copy/apply_instantly_copy.py \
    --apply --restore changesets/backups/instantly_copy_<campaign_id>_<ts>.json --campaign <key>
```

Same rules as every change-set on `changesets/rollback.py`: only an unsuffixed `instantly_copy`
rollback point for that campaign is accepted (a phase0 point or another campaign's point is
refused), live is read and the change printed first, a later change to `sequences` is refused
unless `--override-later-changes`, and only `sequences` is PATCHed.

## Exit codes

`apply_instantly_copy.py`: 0 ok; 1 staged folder not verifiable, or live drifted from the doc
baseline; 2 live write refused (not live, `--dry-run` with `--apply`, no `--campaign`,
`--from-snapshot` with `--apply`, confirmation mismatch, live moved during the prompt, backup not
writable, shadow record); 3 API error (a multi-campaign dry-run reports it and goes on with the
others) or a PATCH that was not verified. `build_from_doc.py`: 0 staged or nothing to stage;
1 refused.
