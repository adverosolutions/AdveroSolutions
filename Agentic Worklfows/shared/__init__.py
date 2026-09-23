"""AdveroSolutions shared library (revenue automation).

    from shared import settings, instantly, ghl, store, job_log, notify, llm, slots
    from shared.settings import guard_write, is_live, IDS, OFFERS_MD, TZ

Shadow contract: MODE=shadow (default) means no write reaches Instantly, GHL
or any other live system; every write path calls settings.guard_write() first
and returns a {'shadow': True, ...} record instead. See shared/README.md.
"""
from shared import settings, job_log, store, notify, llm, slots, instantly, ghl  # noqa: F401
from shared.settings import (  # noqa: F401
    CADENCE_HOUR,
    IDS,
    MAX_BUSINESS_DAYS,
    MIN_LEAD_HOURS,
    MODE,
    OFFERS_MD,
    SEND_WINDOW,
    SLOT_WINDOW,
    TZ,
    LiveWriteBlocked,
    guard_write,
    is_live,
    load_env,
    require_live,
    require_offers,
)
from shared.instantly import Instantly  # noqa: F401
from shared.ghl import GHL  # noqa: F401
from shared.store import ABSENT, JsonFileStore, ModalDictStore, Store, StoreError, get_store  # noqa: F401
from shared.job_log import log_run, shadow  # noqa: F401
from shared.notify import notify as send_notification  # noqa: F401
from shared.llm import MODEL_POLICY, complete, register_fake  # noqa: F401

__all__ = [
    "settings", "job_log", "store", "notify", "llm", "slots", "instantly", "ghl",
    "CADENCE_HOUR", "IDS", "MAX_BUSINESS_DAYS", "MIN_LEAD_HOURS", "MODE", "OFFERS_MD",
    "SEND_WINDOW", "SLOT_WINDOW", "TZ", "LiveWriteBlocked", "guard_write", "is_live",
    "load_env", "require_live", "require_offers", "Instantly", "GHL", "JsonFileStore",
    "ABSENT", "ModalDictStore", "Store", "StoreError", "get_store", "log_run", "shadow", "send_notification", "MODEL_POLICY",
    "complete", "register_fake",
]
