# Handoff: Community Content Bot to Community Manager (2026-11-04)

Requested by Lorenzo via COO, 11/4 1:21 PM CT. Nothing was deleted or paused for this handoff.

## Processes
- Community calendar post drafts: draft the next day's slot from ~/advero/state/communities/post_calendar_month1.md (and the .csv), save to ~/advero/state/communities/drafts/post_<yyyymmdd>_slot<NN>.md, and set that slot to drafted. ON HOLD since 10/21 (Lorenzo is holding community posts; slots 1 to 3 parked). Never mark anything ready to post.
- Maker School accountability draft: STOPPED. COO has owned it since Day 3 (2026-10-22).

## Routines
- "Evening community post draft", folder id `evening-community-accountability-drafts`. Cron CRON_TZ=America/Chicago 45 17 * * *, flexible (up to 15 min early, never late). Status: PAUSED since 10/21. When it's live, it skips parked slots, drafts tomorrow's slot, and messages Community Manager the path. Community Manager asked on 10/27 for it to be deleted. That is waiting on Lorenzo's own yes and has not been done.

## Files I made
- ~/advero/state/communities/drafts/post_20261022_slot02.md (Construction Contractors Hub, missed calls question).
- ~/advero/state/communities/drafts/post_20261023_slot03.md (Agency Service Scaling Kings, lead response question, post in General discussion). Group rules from https://www.skool.com/kings/-/rules: be positive, no self-promotion, stay on topic and in the right category.
- ~/advero/state/communities/drafts/accountability_day2_20261021.DROPPED_coo_drafted.md (dropped).
- ~/advero/state/community/drafts/2026-10-21_accountability_day2.md (stray early scaffold in the wrong folder, safe to ignore or remove).

## Open items
- Slots 1 to 3 parked until Lorenzo says go.
- Routine deletion is pending Lorenzo's yes.
- The role doc ~/advero/state/org/roles/community-content-bot.md was never created.

## Logins
- None. I only used the Google Sheets connector (read only, sprint sheet <REDACTED:long_token>, Daily Log tab) and public curl for Skool rules pages.

## Gotchas
- The Daily Log row is filled by the nightly writer at about 9 PM CT, so it's often empty at 6 PM. Leave blanks; unmeasured is n/a, never 0.
- Day 2 cold emails (750) and replies (5) matched Day 1 exactly, flagged as possibly carried over.
- Skool About pages don't include the rule text; use /-/rules.
- The CSV calendar may be mid-sync by Community Manager. Re-read it before editing, and change only the one status cell.
- Voice rules: automation consultancy only, never a trade business, never a 'first' close. No em dashes, en dashes, exclamation marks, or emojis (except the 💸 in the accountability title). No 'man', 'bro', or gendered address. No price, links, or pitch. Proof only word for word from approved_proof.md and only with Lorenzo's okay (none is approved for communities). Check clients/INDEX.csv before naming anyone.
