---
name: cold-read-research-2026
description: Sept 2026 cold-reading study on 18 recruiting/cleaning/bookkeeping companies — which traits are safe to assert blind per niche, plus list data-quality findings (dead sites, contact-vs-company state mismatch, off-niche leaks)
metadata:
  type: project
---

Method (2026-09-02): seeded random draw of 5 clean leads/niche (+3 extra cleaners after
off-niche leaks), each researched by a Sonnet subagent (site pages + 2 searches, every
field source-backed or blank). Files: `Coding/lead-scrape-2026/research/` —
findings_by_company.csv, trait_prevalence.csv, distinctive_facts.csv, aggregate.py.
Verdict rule: >=80% of sample = SAFE to assert blind; 50-79% COIN FLIP; else needs research.

**SAFE cold reads found**
- Recruiting: "industry/role specialist" (5/5) — every firm names a niche. Nothing else is safe.
- Bookkeeping: small-business focus (4/5), "personal relationship" positioning (4/5), client
  portal (4/5), does individual tax too (5/5). CPA credential only 3/5 — don't assume CPA.
- Cleaning: serves offices (6/6), serves medical/healthcare (5/6). Eco/green, free quote,
  years-in-business, custom plans are coin flips (4/6).

**List data-quality facts that constrain personalization**
- Website reachability (60 random clean/niche): bookkeeping ~81%, recruiting ~76%,
  cleaning ~65% live. "Saw your site/work" is provably false for 1 in 4-3 leads.
- `state`/`city` on the lead = CONTACT's LinkedIn location, not the company's:
  differs from company_state for recruiting 25%, cleaning 34%, bookkeeping 16%.
  Use company_city/company_state (now added to MASTER + sheet) for any location line.
- Off-niche leakage in a random clean sample: cleaning 2/5 (furniture installer, sign
  company); recruiting had an Egypt-based firm listed as Virginia. Recruiting sites were
  rough: dead domain, Lorem-Ipsum About page, 2016 Joomla template.
- company_size from the actor is unreliable (18 listed vs 250+ on site).

**Why:** Lorenzo's approach is cold reading (assert industry-typical things so it sounds
researched). Only SAFE traits qualify; distinctive facts need per-lead research.
**How to apply:** anchor lines to the business type, not the website; never name city
from `state`; treat CPA/eco/guarantee as research-gated. Related: [[lead-scrape-2026-niches]]
