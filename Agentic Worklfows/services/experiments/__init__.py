"""services.experiments - Blueprint M3 and M4 (brief A7).

Three things live here and nothing else:

``analytics``        read-only pulls of Instantly campaign analytics (overview,
                     per-step, per-variant) plus positives counted off the
                     replied-lead list.
``verdicts``         the campaign verdict rules (1,000 / 3,000 send lines, the
                     500-sends-per-variant rule, recruiting retirement) and the
                     projection math for the next decision date.
``copy_validator``   ``validate_copy()``: the change-sets' copy gate, extended
                     with the A7 rules (merge variable anywhere inside a spin,
                     one proof family per campaign, 30-word readability flag).
``experiment_log``   ``config/experiments.json`` read / seed / update.
``report``           markdown rendering for the job and the runbook.

Nothing in this package writes to a live system. Every Instantly call it makes
is a GET (or one of the two POST-shaped reads), which is safe under the
controlled-environment rule; the job that drives it (``jobs/campaign_verdicts.py``)
is the only thing that writes, and it writes one local JSON file.
"""
