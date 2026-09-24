# Upwork offers: proof and pricing for Upwork follow-up drafts

This file is the only source of figures and proof for Upwork drafts
(`services/upwork_followup/`). A draft may state a dollar figure or a
percentage only when that exact figure is written in this file. Nothing else
is a source: not the private assessment notes, not the client intel, and not
the cold-email offer sheet (`config/offers.md`), which stays separate so the
cold-email gates that read it are unchanged.

`services/upwork_followup/draft.py` puts this file in every draft prompt and
hands it to the copy gate (`copy_gate.py`). Any figure added here becomes
quotable in an Upwork draft, so only Lorenzo adds figures.

## Proof

Copied verbatim from `Coding/upwork-pipeline/templates/ps-case-studies.md`.
Every proposal already carries these, so follow-up touches never quote them
(Lorenzo, 2026-09-23). T3 only hints at a past client like theirs, with no
name and no figures, when one line matches the client's vertical or problem;
if none fits, it shares a relevant insight instead, never a stretched match.
A reply may quote one line when the client asks for examples, proof or past
work.

- Vertical: trades, bids and estimates (commercial roofing contractor).
  $750M+ in annual bid volume runs through a routing and follow-up system I built for a commercial roofing contractor, every estimate request tracked and followed up on, none lost to manual chasing.
- Vertical: paid ads and ROI (lender).
  Generated $5M in loan applications in 30 days on $1,500 of ad spend for a lender, a 3,300x return on the media budget.
- Vertical: outbound and B2B lead generation (software consultancy).
  Increased a software consultancy's qualified lead volume 35% with an outbound system that personalizes each message instead of blasting a template.
- Vertical: AI systems (Lorenzo's own AI agency).
  Scaled my own AI agency to $10,000 a month on the same kind of system.

## Pricing

None, by design (Lorenzo, 2026-09-23): he sets the price for each job
himself, so no draft ever states a price. When a client asks about price, the
reply leaves it for Lorenzo in NEEDS_YOU.
