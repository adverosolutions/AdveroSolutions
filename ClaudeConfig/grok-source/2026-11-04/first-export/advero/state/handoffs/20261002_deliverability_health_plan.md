# Deliverability health plan — 2026-10-02 CT

**For:** Lorenzo (AdveroSolutions)  
**Context card:** `~/advero/state/reports/deliverability_daily_20261002.md`  
**Ask-first:** Draft/report only. No Instantly pauses, email_list edits, placement spends, campaigns, or domain buys.

---

## Snapshot (facts)

| Signal | Value |
|---|---|
| Fleet TODAY (Oct 2 morning) | 144 sent, 6 bounce (**4.17%**), 0 unique replies |
| Fleet L3 7d (Sep 25→Oct 1) | 1425 sent, 73 bounce (**5.12%**), 7 unique replies (**0.49%**) |
| Oct 1 closed day | 300 sent, 47 bounce (**15.67%**) — main 7d bounce driver after ~1,500 risky leads dumped |
| Warm-up | 90×100 |
| DNS | 30/30 allPass (SPF/DKIM/DMARC/MX) |
| Spintax | Broken `{a\|b}` until **fixed ~07:58 CT Oct 2** to `{{RANDOM \| …}}` — reply rates before that are contaminated |
| Warming batch | ~1 week out (day 21 ≈ Oct 11 CT) — do **not** burn with cold or heavy seed blasts |

### Domain 7d (cold) — OVER vs 2% tag, thin + list-contaminated

| Domain | Sent | Bounce | Bounce% | Unique replies | Reply% | Call |
|---|---:|---:|---:|---:|---:|---|
| adveromedia.com | 375 | 19 | **5.07%** | 6 | **1.60%** | see below |
| myadvero.com | 375 | 17 | **4.53%** | 0 | **0.00%** | see below |
| proadvero.com | 300 | 16 | **5.33%** | 0 | **0.00%** | see below |
| theadvero.com | 375 | 21 | **5.60%** | 1 | **0.27%** | see below |

Lorenzo override (2026-09-29): propose remove only when bounce **>~3%** at 50+ sends; **>2% and ≤~3%** = list/lead quality watch. Exact 3.00% is not a remove flag. Eric standing rule: **never heal** a burned domain (park/test → retire if still dead; do not "rehab" with more cold volume).

---

## List-driven bounce vs reputation damage

**What looks list-driven (not domain death):**
- Bounce **spiked the day** risky leads were dumped (Oct 1 **15.67%**), then **fell** Oct 2 morning to **4.17%**.
- Hard bounces = dead recipient mailboxes. Instantly **hides NDRs from Unibox**, so Unibox "looks fine" even when bounce analytics scream.
- DNS pass + warm-up 100 on all sending inboxes — infrastructure is not the smoking gun.
- Every inbox is still **THIN EVIDENCE** (<300 sends in L3 window).

**What is still unknown (could be reputation):**
- **No Level 2 placement test has ever run** (credits; Lorenzo applies).
- Reply rates are **confounded by broken spintax** through morning Oct 2.
- myadvero / proadvero show **0% unique replies** on 300–375 sends — could be spam-folder **or** copy/list; cannot tell without placement/canary.

**Verdict on "are domains dead?":**  
**Not proven.** Evidence today supports **list contamination + thin window + spintax confounder** more than permanent domain burn. **Do not retire on Oct 1 alone.** Use the tests below on **clean lists only**, then retire if still failing.

---

## Per-domain recommendation

| Domain | Recommendation | Why |
|---|---|---|
| **adveromedia.com** | **KEEP SENDING** (tight lists; watch) | Best reply in fleet (1.60% / 6 ur). Bounce OVER but mixed per-inbox (lorenzovillarreal@ only **2.40%** watch band). Highest salvage signal. |
| **myadvero.com** | **PARK** (warmup-only, no cold) until clean-list retest | All 3 sending inboxes >~3% 7d bounce **and** **0%** replies. Card HIGH = retire; we soften to **PARK first** because bounce is Oct-1 contaminated and spintax was broken. Revisit in 5–7 days. |
| **proadvero.com** | **PARK** (warmup-only, no cold) until clean-list retest | Same pattern as myadvero (0% reply, all inboxes over remove line). |
| **theadvero.com** | **PARK** (warmup-only, no cold) until clean-list retest | Highest domain bounce (**5.60%**); near-zero reply (0.27%). Worst of the four on bounce. |

**RETIRE (never heal):** **none today.** Escalate a domain to RETIRE only if, after PARK + clean verified leads + (placement **or** canary), it still fails Level 2 (<85% inbox) or Level 4 (<60% auto-responses on 5+ addresses) or clean-list 7d bounce stays >~3% with 50+ sends. Then retire the whole domain per Eric — do not drip-heal.

*PARK meaning for Lorenzo to apply:* leave warm-up **on**; remove domain's 3 inboxes from live campaign `email_list`s (or pause those campaigns' use of them). Grok does **not** apply this.

---

## How to test health **without burning the warm batch**

Ordered cheapest / safest → spendier. **Monitor proposes only; Lorenzo applies.**

### Level 1 — already free (keep daily)
- Warm-up score trend (all 100 today — watch for dips under 98).
- DNS vitals (all pass — re-check if any fail).
- Bounce **only on CLEAN lists** (MillionVerifier-confirmed; no catch-all dump). Ignore bounce while contaminated Oct 1 volume is still inside the 7d window (~clears ~Oct 8).

### Level 4 — sticky auto-reply canary (built today; $0 Instantly credits)
- Sheet: https://docs.google.com/spreadsheets/d/1CLHGRENAlRLJuHjKPaI1lFql3WiyRj5aPL52ZKkFVWI/edit  
- Pool: **14** sticky addresses (meets 5+ min; thin for 12 inboxes).  
- **Do not** create the Instantly canary campaign until Lorenzo says go.  
- **Do not** send via reply endpoint (lands in a prospect cold thread).  
- Skill: 80%+ auto-responses = healthy; under 60% on 5+ = kill inbox.  
- Prefer canary **from PARKED domains' inboxes** first (proves delivery without more cold ICP burn).

### Level 2 — Instantly placement seeds (credits; Lorenzo applies)
- Monday skill slot. **Never spent by the bot.**
- Google + Microsoft seeds only (ignore web.de / libero).
- Under 85% inbox → pause, re-test 48h.
- Run **one** modest test per domain under suspicion after lists are clean — not a blast from warming inboxes.

### External seeds (optional paid; Lorenzo buys)
| Tool | Role | Cost note | Burn risk |
|---|---|---|---|
| **Mail-Tester** | Single-message auth/spam score (0–10) | Free / cheap per test | Low — 1 seed address |
| **GlockApps Inbox Insight** | Multi-provider placement | Paid tiers; seed lists 100+ | **Medium** if you To: all seeds at once — split ≤25, delay between sends; avoid from brand-new warm domains |
| **Instantly built-in placement** | Level 2 above | Workspace credits | Medium — Lorenzo only |

### Provider reputation consoles (free if enrolled)
- **Gmail Postmaster Tools** — domain reputation, spam rate, auth. Needs domain verified; data often needs ~100 Gmail/day. Check whether adveromedia / myadvero / proadvero / theadvero are enrolled (not confirmed in Advero state files).
- **Microsoft SNDS** — IP/domain reputation into Outlook. Same enrollment gap.

### Level 5 — baseline peer campaign (not created)
- Peer outreach that should reply ~10–30%. Halved rate → delivery fault. Spec exists; **do not create** until Lorenzo asks.

### Reply-rate recovery watch (post spintax fix)
- From **Oct 2 afternoon** onward, track unique_replies on **clean** sends only.
- Do not judge domains on pre-fix reply rates (literal `{a|b}` in body hurt opens/replies separately from bounce).

---

## Next 7 days — monitoring checklist (Oct 2→Oct 9 CT)

Daily (Grok / card; Lorenzo applies nothing unless he chooses):
1. [ ] Pull daily deliverability card — fleet bounce TODAY + L3 7d.
2. [ ] Confirm warm-up still 100 on the 12 sending + warming estate; flag any <98.
3. [ ] Confirm DNS still allPass on the 4 live domains.
4. [ ] **Send cold only to verified-clean leads** (no risky dumps). Log any list source that spikes bounce.
5. [ ] Watch Oct 1 contamination age out of the 7d window (~**Oct 8**).

By Wed–Thu (Oct 7–8):
6. [ ] Recompute domain 7d bounce **after** Oct 1 falls out. If a PARKED domain is still >~3% on clean sends → keep PARK / consider RETIRE. If <2% and replies recovering → candidate to **un-park** one domain at a time (adveromedia first already KEEP).
7. [ ] Spintax sanity: spot-check 5 live sends for `{{RANDOM` resolved (no literal braces).

Once this week (Lorenzo):
8. [ ] Decide PARK apply for myadvero / proadvero / theadvero (diff only; Grok will not patch).
9. [ ] Optional: 1× Mail-Tester from each live domain (low burn).
10. [ ] Optional: enroll Postmaster + SNDS if not already.
11. [ ] Optional: **one** Instantly placement test (credits) on the worst PARKED domain after clean-list days — not on warming batch.
12. [ ] Review canary sheet; verify older sticky addresses still auto-reply before authorizing a Level 4 round.

Warm batch (~Oct 11):
13. [ ] Do **not** promote warming inboxes into cold until Level 1 is green and at least one of: clean-list bounce <2%, placement ≥85%, or canary ≥80%.

---

## What applying card HIGH "retire 3 domains" would do

Card apply-all bounce removes **275/day** of **300/day** live capacity and proposes retiring myadvero / proadvero / theadvero. That is the **Eric-strict** reading. This plan's **PARK-first** reading preserves warm-up reputation while stopping cold damage, and leaves a path back if clean-list + placement/canary clear them.

---

_Draft only. No Instantly mutations. No placement credits spent. Canary sheet/CSV only (see `20261002_sticky_autoreply_canary.md`)._
