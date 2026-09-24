# Section 3 status

**2026-09-23 (split day):** Lorenzo's new voice rule (no Claudeisms, normal capitalization) is in `sections/README.md`, his global CLAUDE.md and a `claudeisms` skill.

**Earlier on 2026-09-23:** the follow-up pipeline and price guard are committed and tested. One real read-only run is done (drafts only). Not scheduled yet. The GHL Upwork pipeline doesn't exist yet (Lorenzo creates it).

## Next
1. **Touch walkthrough** (Lorenzo said yes, 2026-09-23): T1 to T7 and the check-in are agreed; the reply prompt is the last item. Every decision and sample is in `walkthrough.md`. Samples are written by hand on a made-up client, no model spend.
2. **Then apply the agreed edits to all 9 prompts in one piece** (worker, then reviewer), per `walkthrough.md`:
   - normal capitalization (drop "Lowercase-casual is fine");
   - the no-Claudeisms rule with its examples;
   - T3 rework: a vague line about a similar past client, no name and no figures, only when a proof line truly matches; no touch repeats a result the proposal already states.
   Update the tests that pin prompt text, then run the full suite and push to main.

## Waiting on Lorenzo
The 08:30 scheduled task (yes/no), the GHL Upwork pipeline, the pricing lines in `config/upwork_offers.md`.
