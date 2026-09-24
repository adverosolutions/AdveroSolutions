# Section 3 status

**2026-09-23 (split day):** Lorenzo's new voice rule (no Claudeisms, normal capitalization) is in `sections/README.md`, his global CLAUDE.md and a `claudeisms` skill.

**Earlier on 2026-09-23:** the follow-up pipeline and price guard are committed and tested. One real read-only run is done (drafts only). Not scheduled yet. The GHL Upwork pipeline doesn't exist yet (Lorenzo creates it).

## Next
1. **Touch walkthrough: done** (2026-09-23). All 9 prompts agreed; every decision and sample is in `walkthrough.md`.
2. **Then apply the agreed edits to all 9 prompts in one piece** (worker, then reviewer), per `walkthrough.md`:
   - normal capitalization (drop "Lowercase-casual is fine");
   - the no-Claudeisms rule with its examples;
   - T3 rework: a vague line about a similar past client, no name and no figures, only when a proof line truly matches; no touch repeats a result the proposal already states.
   Update the tests that pin prompt text, then run the full suite and push to main.
   **In progress:** worker done (full suite green, all 9 agreed samples pass the gate), reviewer running. If this chat ends before it lands, the unreviewed edits are on GitHub as branch `wip/section-3-prompt-edits`: review them, commit to `section/3-upwork`, push to main, delete the wip branch.

## Waiting on Lorenzo
The 08:30 scheduled task (yes/no), the GHL Upwork pipeline, the pricing lines in `config/upwork_offers.md`.
