<!-- distill: batch_11_of_11 | videos: V5k2uY9T-Eg | model: opus | elapsed_s: 28 -->

# Playbook batch: Disposable-inbox deliverability ops (end-2025 SOP)

## 1. Frameworks / mental models
- **Hot-swap / disposable mindset:** treat sending domains as disposable. Never try to heal a burned domain; cancel it, rotate in a warmed backup, and reorder. [V5k2uY9T-Eg]
- **Over-provision capacity:** build infra for about 3–10x planned daily volume. Their default is infra for "5,000 emails a day" while clients test at "500 to 1500 emails a day". [V5k2uY9T-Eg]
- **Two pools:**
  - **Active pool:** the inboxes currently sending.
  - **Insurance pool:** inboxes that warm untouched for 4, 8, or 12+ weeks. [V5k2uY9T-Eg]
- **Assume spam complaints will happen.** Some recipients mark even good copy as spam, so plan spare inboxes for attrition. [V5k2uY9T-Eg]
- **Budget-neutral loop:** remove a failing inbox, swap in an insurance inbox, cancel the failed one, order a replacement. Spend stays flat and fresh inboxes keep warming. [V5k2uY9T-Eg]
- **ROI first, ESP tuning second.** Don't pre-optimize for Outlook or Proofpoint on day one. Only intervene if positive replies aren't producing ROI. [V5k2uY9T-Eg]
- **ICP fit:** they avoid clients whose TAM is only Fortune 500/5000. A large TAM makes the disposable model workable. [V5k2uY9T-Eg]

## 2. Copy formulas
- **Outlook targets:** keep copy short. This is attributed to Nick Abraham and is anecdotal. [V5k2uY9T-Eg]
- **Language may matter:** Enzo Caraso reports no Outlook problem in Europe, which suggests filters react to English copy. This is anecdotal. [V5k2uY9T-Eg]

## 4. List-building & enrichment tactics
- **Segment leads by ESP:** check whether each lead's domain is on Google or Outlook/other via MX records.
  - Tool: inboxcore.com from Lead Magic.
  - Alternative: ask ChatGPT to build an MX lookup, e.g. with Google's DNS endpoint. [V5k2uY9T-Eg]
- **Fallback when ROI is weak:** send to Gmail-hosted leads only for the first 2–3 weeks while the other inboxes keep aging. [V5k2uY9T-Eg]

## 5. Deliverability / inbox infra notes
**Sourcing** [V5k2uY9T-Eg]
- Domains: Porkbun and Dynadot, which have the most sales on `.com` and `.co`.
- Inboxes: mostly Hypertide. Google inboxes also from Zapmail and two vendors transcribed as "Pager" and "Alforic".

**Warm-up**
- Outlook and Proofpoint currently need longer warm-ups. [V5k2uY9T-Eg]
- Domain age is "really the thing" that gets through Outlook and Proofpoint. [V5k2uY9T-Eg]

**Outlook re-entry SOP** [V5k2uY9T-Eg]
1. Send to Gmail-only leads with the current active inboxes for 2–3 weeks.
2. Once the insurance inboxes pass 4–6 weeks of warm-up, remove the original active inboxes, even healthy ones.
3. Swap in the aged insurance inboxes and resume sending to Outlook.

**Other practices**
- Open tracking is off. When they tracked opens on Thursdays and Fridays, replies and positive replies dropped on those days. [V5k2uY9T-Eg]
- Spam placement tests are rarely used; they found them a weaker signal than reply, reputation and bounce monitoring. [V5k2uY9T-Eg]
- At high Hypertide volume, sending through Smartlead can slow down. Use batching and Hypertide's bulk-ops tools (`smartlead.hypertide.io` / `instantly.hypertide.io`). [V5k2uY9T-Eg]
- They built the monitoring and rotation system with Cursor, but the workflow wasn't shared. [V5k2uY9T-Eg]

## 6. Metrics & testing cadence
**Rotation triggers checklist** [V5k2uY9T-Eg]

| Signal | Cadence | Threshold (claimed) | Action |
|---|---|---|---|
| Campaign reply rate (excluding OOO) | Daily | "below 1%" (some leeway in hard markets) | Investigate and rotate |
| Inbox reputation | Automated / continuous | "below 98%" | Remove inbox from sending |
| Domain reply rate | Weekly (Fridays) | "<1%" (≈0.8% tolerated) **or** bottom 10% of domains | Mark failing, remove its inboxes |
| Domain: share of inboxes under 98% reputation | Weekly | "more than 10" (likely 10%) | Remove |
| Bounce rate | Ongoing | "over 2%" | Remove from campaigns |

- After every removal, swap in an insurance inbox warmed for well over 2 weeks and order a replacement. [V5k2uY9T-Eg]
- **Friday domain audit template:** export stats for every active domain → sort by reply rate → flag domains under 1% or in the bottom 10% → flag bounce over 2% → pull flagged inboxes → swap from insurance → cancel → reorder. [V5k2uY9T-Eg]

## 7. Tools mentioned
- **Porkbun, Dynadot:** domain purchasing. [V5k2uY9T-Eg]
- **Hypertide:** primary inbox provider, with bulk-ops tools for Smartlead and Instantly. [V5k2uY9T-Eg]
- **Zapmail, "Pager", "Alforic":** Google inbox providers. [V5k2uY9T-Eg]
- **Smartlead, Instantly:** sequencers. [V5k2uY9T-Eg]
- **Lead Magic / inboxcore.com:** detects a lead's ESP (Google vs Outlook). [V5k2uY9T-Eg]
- **ChatGPT + Google DNS endpoint:** do-it-yourself MX lookups. [V5k2uY9T-Eg]
- **Cursor:** builds the internal monitoring and rotation workflows. [V5k2uY9T-Eg]

## 8. Caveats / dated claims to re-validate
- All thresholds are late-2025. Re-check the 1% reply, 98% reputation and 2% bounce thresholds against current Instantly benchmarks. [V5k2uY9T-Eg]
- **Transcript ambiguities:**
  - "Maybe we'll go to 8%" is almost certainly 0.8%.
  - "More than 10 of the inboxes" is probably 10%.
  - "Portbun/Dinadot" are Porkbun/Dynadot.
  - "Pager" and "Alforic" are unverified vendor names; confirm before buying. [V5k2uY9T-Eg]
- The open-tracking harm is based on a few weeks of Thursday/Friday observation, not a controlled test. [V5k2uY9T-Eg]
- The claims about European Outlook, English-language filtering, and short copy for Outlook are anecdotal. [V5k2uY9T-Eg]
- Scale context: "5–6 million emails a month" and "200,000 inboxes". The thresholds may not transfer to Advero's lower volume. [V5k2uY9T-Eg]
- Confirm inboxcore.com is still live and still attributed to Lead Magic. [V5k2uY9T-Eg]

## Source videos
- V5k2uY9T-Eg — Outbound Email Deliverability Update for End of 2025
