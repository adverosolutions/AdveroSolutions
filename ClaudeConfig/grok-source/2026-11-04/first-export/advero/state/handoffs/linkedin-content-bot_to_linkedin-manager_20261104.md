# Handoff: LinkedIn Content Bot to LinkedIn Manager
Written Wed Nov 4, 2026, 1:25 PM CT. Requested by Lorenzo via COO (11/4 1:21 PM CT). Nothing deleted or paused.

## What the seat does
Weekly (Monday) LinkedIn content: keep the calendar full and turn wins, numbers and lessons into post briefs and profile copy drafts. Drafts only. Lorenzo approves and posts. The bot never opens LinkedIn and never publishes.

## Routines and schedules
None. This bot has no saved routines. The Monday cadence was run on request, not by a scheduled routine.

## Processes
1. Post drafting: research public web and X only, write the draft, make visuals with AI image generation if needed, save under ~/advero/linkedin/posts/YYYY-MM-DD/, then send the draft to LinkedIn Manager for Lorenzo's approval.
2. Before any post that draws on a lead or client, grep ~/advero/state/clients/INDEX.csv and read that client file. Afterward, append a dated Log line to the client file and update the INDEX.csv row under flock ~/advero/state/clients/.lock (see ~/advero/state/clients/README.md).
3. Keep the role doc ~/advero/state/org/roles/linkedin-content-manager.md current. Its decisions log is append only.
4. Run a dash check before handing anything over: rg "[\x{2013}\x{2014}]" <file>.

## State files
- ~/advero/linkedin/CONTENT_DASHBOARD.md: dashboard of drafts, scheduled posts, Lorenzo items and blockers (made 11/2)
- ~/advero/linkedin/posts/2026-11-02/: Nov 2 post. Files: post.md and post_v2.md (v2 is current, soft-sell speed to lead), research.md, carousel.pdf and carousel_v2.pdf, slide*_v2.jpg (1080x1350, upscaled)
- ~/advero/linkedin/posts_week_20261020.md: 4 old outlines (dates passed)
- ~/advero/state/linkedin_content_plan.md: Oct research plan, hooks and evidence (calendar expired)
- ~/advero/linkedin/profile_kit.md, PLAN.md, SIMPLE_PLAN_20261020.md: shared LinkedIn files
- ~/advero/state/org/roles/linkedin-content-manager.md: role doc

## Open items
- Nov 2 post v2 is waiting on Lorenzo's approval. Optional edit: change "40 step funnel" to "a giant funnel" if he wants no numbers at all.
- Old Oct items are still open: Fri hook A or B plus his lesson, a real prospect question, a GHL demo screenshot with test data, and a yes or no on the roofing proof line (~/advero/01_business_context.md section 6, word for word only).
- The dashboard needs updating to show the Nov 2 post.

## Logins used
None. No LinkedIn or other account logins. Research used public web and the built-in X read tools only.

## Gotchas
- No em or en dashes in any copy.
- Never invent stats or client results. Use approved proof word for word only. Make no sprint claims or targets unless Lorenzo writes them (90 Day Sprint, Day 1 Oct 20, 2026).
- Lorenzo wants no hard sell: write as a friendly, honest recommendation. End on a closing question, not a "comment KEYWORD" call to action.
- Label demos "demo, test data, not a client result."
- AI images come out 3:4 and low resolution, so trim and upscale them to 4:5 at 1080x1350.
- No team room posts from 9 PM to 6 AM.
- One yes rule: Lorenzo's yes in the COO chat, relayed with his exact words and time, counts as approval only for what his words cover.
