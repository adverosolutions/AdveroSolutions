"""Offer Intel: mine Maker School wins posts for offers that are closing now.

Plan: MAKER_SCHOOL_WINS_PLAN.md. Runbook: runbooks/offer_intel.md.

    skool_read  read-only Skool collection (logged-in Chrome profile on the Mac)
    gate        Haiku: is this a business win, which channel
    extract     Sonnet: offer fields, each with the sentence it came from
    taxonomy    free-text industry / mechanism -> fixed lists
    rollup      patterns ranked by distinct winners
    render      CSVs, weekly digest, hand-check sheet

Other members' numbers are market research. Nothing here feeds an email, a
reply-engine draft or a proof line; config/offers.md stays the only proof.
"""
