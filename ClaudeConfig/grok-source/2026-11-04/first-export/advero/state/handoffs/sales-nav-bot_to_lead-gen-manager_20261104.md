# Sales Nav Bot -> Lead Gen Manager handoff (2026-11-04, written 1:2x PM CT)
Per Lorenzo 11/4 1:21 PM CT via COO: seat folds into Lead Gen Manager. Nothing deleted or paused by me for this handoff.

## Process
- Build Sales Navigator lead lists (saved searches, save leads to lists), vet fit, fill ~/advero/state/linkedin_connect_queue.csv for LinkedIn Setter.
- Fit: owners/founders/presidents/CEOs of pest or local-service cos, or true Google Ads/PPC agency owners. No SEO/creative/full-service agencies.
- Queue target 35/day Mon-Sat (Sat cap 34), queued by 9 PM night before. Local service <= half of a day, PPC first.
- Every row: checked /in/ URL at fill time (read Sales Nav overflow "View LinkedIn profile" href, don't click), "src ...; " note, dedupe vs queue, tracker, clients. Never pad. Backups = status `queued` + "BACKUP no rollover". No rollover of backups (li no-rollover rule 11/3).
- Columns: queue_date, person, company, profile_url, fit_reason, status.

## Gate / browser
- `~/advero/bin/linkedin_gate acquire|release|status sales-nav-bot` (~45 min hold). Release the moment a session ends.
- Stay off gate 7:00-9:35 AM CT Mon-Sat (Setter window).
- LinkedIn runs on box browser (Lorenzo 11/1 rule, state/org/LEAN_ORG.md ~line 60). Uses the existing box-browser LinkedIn/Sales Nav session; I never enter passwords, 2FA codes, or payment details, and never set up 2FA.
- Page budget 60/day. Throttle historically hit ~70 company pages.

## Never
- Connect requests, messages/InMails, comments, likes, follows, posts, open Messaging, bulk export/scrape.
- Click/type at any sign-in, verification, captcha, or restriction prompt.
- Load saved searches 2003647996 or 2003701060.
- Use held_lorenzo rows or linkedin_ppc_candidates_20261023.csv.
- Any LinkedIn write beyond saving leads without ask-first via manager + COO.
- Stop at any hang, grey screen, HTTP 400, page >20 s, or warning; write stop record in state/stops/ naming site, page, what it shows.

## Routines (all mine; none deleted)
- Daily LinkedIn connect queue fill: weekdays ~6:00 AM CT, ENABLED. Fills next days' queue rows. NOTE: conflicts with nothing in 7-9:35 window but check hold status before it runs tomorrow.
- 10/27, 10/28 one-offs (connect fill, Bing owner search, save remaining searches + Joshua C.): enabled but past dates, done.
- 11/2 resume / fit-targeted / local-trade runs, 11/3 local-trade+pest, 11/4 early Wed top-up, 11/4 Thu-Sat URL checks: paused, one-offs, done.
- 11/4 Fri/Thu/Sat checks + refills (after Setter catch-up), folder 11-4-fri-thu-sat-checks-refills-after-setter-cat: PAUSED by hold, never ran. Plan: Fri URL checks + PPC-first refill from search 2003879556 starting page 64, then Thu checks, Sat checks + rebalance, then Mon 11/9 fill to 35. 51 pages left today at pause.

## State files
- ~/advero/state/linkedin_connect_queue.csv (backups .bak-20261104-0615, .bak-20261104-0926)
- ~/advero/state/handoffs/leadgen/salesnav_saveonly_20261103.csv (31 saved local-trade leads; used: Chad Geaslen (hung), Dana Lawrence (in tracker), Ralph Henry, Sandra Solis, Sky Seals, Doug Winston, Stan Robinson, Joe G., Steve Roberts; next: Evan Hibbs, Martha Padilla, John B., Edgard Jimenez...)
- decisions.jsonl entries: queue_wed_topup_20261104, queue_wed_shortfall_20261104, salesnav_probe_stop_20261104(+_clear), queue_wed_topup2_20261104, salesnav_hold_20261104_1030; li-ce-separate-20261027 (line 750, cold-email opt-out separation rule)
- Stop records: state/stops/salesnav_stop_20261104_0616.md, state/stops/salesnav_probe_stop_20261104.md
- Role doc: ~/advero/state/org/roles/sales-nav-bot.md (contains "PEST WRITES HOLD" flag)

## Queue status (as of 11/4)
- Wed 11/4: 20 sent, 15 queued. Thu 35, Fri 35, Sat 33 NOT URL-checked; Fri has 11 /sales/lead/ links marked url_unverified and 0 PPC rows. Mon 11/9: 2 rows (Petrina, Foster).

## Open items
- HOLD since 10:30 AM 11/4 (Setter's 3rd page hang): off LinkedIn/Sales Nav/gate until Lorenzo's decision via COO.
- Thu-Sat URL checks, Fri PPC refill, Sat rebalance (to 34), Mon 11/9 fill to 35.
- Re-add unsent 11/3 backups (Billy Gregus, Andy Taylor, Justin Brewer) as new rows after Setter's final 11/3 report.
- Offered fit-check of Scott Hicks (Ballyhoo Digital), possibly lost in QuickEnrich dedupe.

## Gotchas
- Sales Nav pages can hang with HTTP 400 (6:16 AM 11/4); stop, don't retry.
- Backup status must be `queued`, not `backup`.
- Can't move Fri rows forward until their URLs are checked.
- Comms: one priority=false status per run to Lead Gen Manager; priority=true only for blockers/STOPs/decisions. Team room no posts 9 PM-6 AM.
