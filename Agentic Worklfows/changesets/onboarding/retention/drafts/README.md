# Generated retention drafts

Every file under here was produced by the job, not typed:

```bash
cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
MODE=shadow LLM_FAKE=1 NOTIFY=off python3 jobs/client_scorecard.py \
  --dry-run --client man-transformed --lookahead 30 --offline \
  --as-of 2026-09-22T00:45:00-05:00 \
  --out-dir changesets/onboarding/retention/drafts
```

They are committed because Mike's day-25 renewal is due by **2026-10-12** and the draft has to exist before then, with its gaps named. Regenerate rather than edit: a hand-edit here is lost on the next run, and the gap list is the point of the file.

`--lookahead 30` is what reaches the day-30 touch, which now falls on 2026-10-19. The default lookahead is 7, which is what a weekly run should use. `--offline` and `--as-of` are what make the run reproducible: `test_the_committed_man_transformed_artifacts_match_a_fresh_render` re-renders these files and fails the suite if they have drifted.

`scorecard_2026-09-21.md` is the document Mike could read. `operator_2026-09-21.md` beside it is Lorenzo's: the retention schedule, the blockers and the run notes, none of which belong on a client's page.

## Mike, Man Transformed

Signed 2026-09-17, 30-day content and lead system. Day 0 is taken as the signing date (`clients.seed.json` records that the kickoff call date is not written down anywhere, which is an open question for Lorenzo). On that basis:

| Day | Due | State |
| --- | --- | --- |
| 7 | 2026-09-24 | ready |
| 21 | 2026-10-08 | blocked, needs the week's numbers |
| 25 | 2026-10-12 | blocked, needs the numbers and a price |
| 30 | 2026-10-19 | blocked, needs a headline result and a review link |

Day 30 is 2026-10-17 on the calendar, which is a Saturday, so it rolls to the Monday. The rest of the cadence holds Mon-Fri and this schedule now does too.

**The day-25 renewal cannot go out as it stands**, and the file says so at the top. Three things have to happen first:

1. Real numbers from his scorecard. His roster row has no campaign ids, so the job has no source for sent, replies, positives, booked, held or closed. Whatever runs his content and lead capture has to be connected before any of those figures exist. The day-21 and day-25 notes need **term-to-date** numbers, not one week's, and the job will not fill them from a week.
2. `renewal_terms` and `expansion_line` written. They are the two offers in the note and there is nothing to generate them from.
3. A price Lorenzo has confirmed. 2,000 dollars is not in `config/offers.md`, and the offer sheet is the only source for a number that goes in front of anyone.

Nothing here has been sent, and nothing in this repo can send it.
