---
name: microsoft-deliverability-recheck-2026-10-09
description: Two-week re-check of Microsoft inbox placement before un-parking 1,154 Microsoft-hosted leads
---

You are helping Lorenzo Villarreal (AdveroSolutions) decide whether Microsoft-hosted leads can go back into his Instantly cold campaigns. Read-only unless noted. Work from /Users/lorenzovillarreal/Desktop/AdveroSolutions. Use the Instantly MCP tools (or the API key INSTANTLY_API_KEY in "Agentic Worklfows/.env").

Background (2026-09-25): Instantly placement tests showed Microsoft seeds putting 42/45 (current copy) and 23/25 (gift card removed) in spam from all four sending domains (theadvero.com, adveromedia.com, myadvero.com, proadvero.com, all Google Workspace). Real replies from Microsoft-hosted leads stopped after Sep 18. proadvero.com was 24/24 spam at Gmail and was removed from all six campaigns (inboxes quarantined, warm-up left on). 1,154 active Microsoft-hosted leads (esp_code 2) were moved out of the six "2026 ..." campaigns into the Instantly lead list "Parked - Microsoft recipients 2026-09-25" (id 6e5482b6-470f-4acc-8edc-bdb492240fcc). Full record: "Agentic Worklfows/changesets/deliverability_2026_09_25/APPLIED.md" and README.md (on origin/main; also in the worktree .worktrees/deliv). Manifest copy: .tmp/deliverability_2026_09_25/parked_leads_2026-09-25.csv.

Do this:
1. Pull the last 14 days of per-inbox analytics (analytics_daily_account for the sending inboxes in the six campaigns' email_list) and received emails; report sends, bounces and real human replies per sending domain and per recipient provider (lead esp_code: 1 Google, 2 Microsoft, 999 other). Real replies = unique_replies, not auto-replies.
2. List any inbox placement tests run since 2026-09-25 and summarize Gmail vs Microsoft spam per sending domain. Do NOT create a new placement test (free tests are used up; tests cost money) unless Lorenzo has said so in a newer note.
3. Check whether the Zapmail CAPTCHA "Security check" page is still on the sending domains (curl -sL https://theadvero.com | grep -i "<title>") and whether the 11 domains registered 2026-09-20 (adverocreative, adverogrowth, adverohq, adveropartners, adverosolution, adverostudio, adveroteam, getadvero, joinadvero, meetadvero, tryadvero .com) now have a plain 301 redirect instead.
4. Recommend one of: keep Microsoft leads parked; run a small paid Microsoft placement test first; or restore a small batch (the change-set's --restore-leads supports --limit). Never restore or change anything live yourself; restoring is Lorenzo's call.
Write the summary in plain English for Lorenzo: short, numbers first, no restating lines, no em dashes.