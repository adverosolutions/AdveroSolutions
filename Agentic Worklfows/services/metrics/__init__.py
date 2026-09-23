"""Daily metrics (Blueprint O4) and the Section 6 KPI dashboard.

    sources  - read-only collectors (Instantly, GHL, Upwork handoff, engine logs)
    render   - the DAILY UPDATE block, in the Daily Metrics tracker's own format
    kpi      - the Section 6 KPI dashboard as one text/markdown block
    sheet    - Daily Log row read + guarded row write on the existing tracker
    skool    - the Maker School post payload + guarded post

Nothing in this package writes to a live system except through
``shared.settings.guard_write``. In MODE=shadow every write is a would_do
record and the rendered text lands in .tmp/ for Lorenzo.
"""
