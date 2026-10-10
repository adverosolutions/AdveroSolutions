---
name: deliverability-2026-09-25
description: "First Instantly placement test (2026-09-25) and diagnosis: proadvero.com burned at Gmail, Microsoft replies stopped after Sep 18, gift-card offer not outperforming; all 6 campaigns paused"
metadata:
  node_type: memory
  type: project
  originSessionId: cfd34993-cbd3-41b3-8ce2-9c48abf169d1
  modified: 2026-09-26T01:50:48.250Z
---

First seed test (id 01a0dac3-e227-7eb6-8334-f0a75795b689, Cleaning Trigger copy, 36 sends = 3 per inbox):
Gmail 8/26 spam, 7 of them from proadvero.com (7/7); the other three domains 1/19. Microsoft 9/10 spam on all four domains.
Lorenzo paused all six campaigns right after (status 2, 2026-09-25 23:21Z).

Live data behind the diagnosis (human replies, 2026 leads, esp_code from Instantly leads):
- Microsoft-hosted leads: 11 human replies Sep 15-18, 0 from Sep 19-25, while Google (2) and other (3) kept replying. Microsoft flipped to junk mid-week, after 7+ angry Microsoft replies and when step 2 (offer repeated in bullets) began Sep 18.
- Gift-card campaigns: 2 positive replies / 920 contacted; non-gift-card campaigns: 4 / 918. No sign the guarantee lifts replies.
- Uncontacted leads: 1,581 Microsoft, 1,226 Google, 901 other. proadvero had the most bounces (13 vs 5-8 per domain); allow_risky_contacts is true on all six.
- All four July domains' homepages are a Zapmail-style hCaptcha "Security check / This link is protected" page on shared host 18.226.18.161 (certs issued 2026-09-15). Not blocklisted; phishing-like pattern. The 11 Sep-20 domains have no A record yet.

Later same night (tests kept sending): test A current copy 134 results: Gmail proadvero 24/24 spam, other three domains 1/65; Microsoft 42/45 spam. Test B (01a0db13-63d9-7ab8-b06a-50da867e505b, guarantee kept, gift card removed): Microsoft 23/25 spam, Gmail non-proadvero 0/5. Removing the gift card did not move Microsoft, so copy is not the deliverability lever; copy left as Lorenzo wrote it. Free placement tests are used up (402 on the third).
esp_code on leads IS the recipient provider (API enum 1 Google, 2 Microsoft, 999 other; MX-verified 24/25). `execution/instantly_lead_sync.py` reads it as delivery status, which is wrong. 1,324 status-1 leads sit in no campaign (424 of them Microsoft).
Lorenzo gave explicit permission (2026-09-25 evening) for Claude to make the Instantly changes, provided every moved lead is documented. Change-set: `Agentic Worklfows/changesets/deliverability_2026_09_25/` on branch ops/deliverability-2026-09-25 (1,154 Microsoft leads to list "Parked - Microsoft recipients 2026-09-25", manifest git-ignored plus copy in `.tmp/deliverability_2026_09_25/`).

APPLIED 2026-09-25 20:46-20:48 CT (commit a37c3e7, record APPLIED.md in the change-set, pushed 1a488fa): all six campaigns now 9 inboxes (no proadvero), allow_risky_contacts false, still paused; 1,154 leads in list id 6e5482b6-470f-4acc-8edc-bdb492240fcc, all verified; proadvero inboxes in main store quarantine. Manifest + campaign backups also in AdveroSolutions/.tmp/deliverability_2026_09_25/. Main checkout was 45 ahead / 25 behind origin (never pull there without asking). One-time scheduled re-check: task microsoft-deliverability-recheck-2026-10-09.

**Why:** Lorenzo thought the copy (guarantee, $ figures, $200 steakhouse gift card) caused it; evidence says reputation (complaints) first, content indirectly.
**Decision 2026-09-27 (Lorenzo):** the $200 steakhouse gift card stays and goes on any new offer it makes stronger. His read after more sending time: deliverability is fine as long as Microsoft recipients stay parked (done). Do not propose dropping the gift card again on deliverability or reply-rate grounds.

**How to apply:** original proposed plan (gift-card part overruled 2026-09-27): pull proadvero from campaigns, park Microsoft leads, drop the gift card, 3-version same-day seed test (current / guarantee without gift card / neutral), captcha off -> plain 301, risky contacts off. Research reports were in the session scratchpad only. See [[instantly-2026-campaigns]], [[no-live-changes-until-tested]].
