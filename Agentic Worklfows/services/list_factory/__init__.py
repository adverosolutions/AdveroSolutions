"""List factory (Blueprint M5, job O8).

3,300 verified, scored, personalized leads a week at no more than 2 cents per
verified contact, as a resumable state machine so a run that dies in stage 5
continues from stage 5 instead of paying for stages 1-4 again.

    source -> icp -> owner -> patterns -> verify -> finder -> suppress
           -> personalize -> stage

Every paid client (Apify, Perplexity, MillionVerifier, a paid email finder,
and the factory's own Anthropic calls) is behind ``ALLOW_PAID_CALLS=1`` alone
(live mode is not required, owner decision R7) and injectable, so the whole pipeline runs
offline on a recorded fixture and in tests without spending a cent. Nothing is
uploaded: the last stage writes a CSV and one ``guard_write`` record for
``POST /leads``.
"""

__all__ = [
    "models",
    "state",
    "sources",
    "icp",
    "contacts",
    "suppression",
    "personalize",
    "ledger",
    "stage_out",
    "pipeline",
    "targets",
]
