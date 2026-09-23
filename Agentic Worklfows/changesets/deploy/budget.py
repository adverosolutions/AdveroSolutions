#!/usr/bin/env python3
"""The LLM spend counter in the DEPLOYED store: check it, reset it (GOL-14).

    cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
    python3 changesets/deploy/budget.py status                       # shadow Dict (the watch)
    python3 changesets/deploy/budget.py status --store-mode live
    python3 changesets/deploy/budget.py reset --store-mode shadow    # asks for RESET on the terminal

Why this exists: ``python3 -c "from shared import llm; ..."`` on the laptop
reads and resets .tmp/store.json, while the containers count spend in the
Modal Dict (key ``llm.spend_usd``). After the cap is hit, a laptop "reset"
leaves the deployed engine refusing every model call. This script reads and
writes that key in the deployed Dict directly. If the Dict cannot be read it
says so and exits 2; it never falls back to a laptop number.

The CAP is different: ``budget_usd`` comes from config/llm_budget.json, and
config/ is baked into the image at deploy time. Raising it on the laptop
changes nothing on Modal until the next deploy
(install_schedules.sh --deploy). ``status`` prints the laptop file's cap and
says so.

``reset`` also opens a new counter period (key ``llm.spend_period``): the
$8 warning and the $10 stop each push once per period, claimed in the same
Dict, so a reset re-arms them. Python 3.9.
"""
import argparse
import json
import os
import sys
from typing import Callable, List, Optional

try:
    from changesets.deploy import common
except ImportError:  # run as a script
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from changesets.deploy import common


def read_spend(store) -> float:
    from shared import llm

    return round(float(store.get(llm.SPEND_KEY, 0.0) or 0.0), 6)


def main(argv: Optional[List[str]] = None, store=None,
         confirm: Callable[[str, str], bool] = common.confirm_from_tty) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("action", choices=("status", "reset"))
    parser.add_argument("--store-mode", choices=("shadow", "live"), default="shadow")
    args = parser.parse_args(argv)

    from shared import llm, store as store_mod

    name = store_mod.modal_dict_name(args.store_mode)
    if store is None:
        store = store_mod.open_modal_store(args.store_mode, create_if_missing=False)
    try:
        spent = read_spend(store)
    except Exception as exc:  # noqa: BLE001 - no number is better than a laptop number
        print("could not read %s in %s (%s: %s). Nothing was changed." % (llm.SPEND_KEY, name, type(exc).__name__, exc))
        return 2
    cap = llm.budget_usd()
    status = {
        "store": name,
        "spent_usd": spent,
        "budget_usd_laptop_config": cap,
        "remaining_usd_against_laptop_config": round(cap - spent, 6),
        "over_budget_against_laptop_config": spent >= cap,
        "note": ("budget_usd is read from the laptop's config/llm_budget.json; the deployment uses the copy "
                 "baked in at its last deploy. Raising it needs a redeploy."),
    }
    print(json.dumps(status, indent=2, sort_keys=True))
    if args.action == "status":
        return 0
    if not confirm("RESET", "Zero the spend counter in %s (spent now: $%.4f)?" % (name, spent)):
        print("Not confirmed. The counter was not changed.")
        return 1
    period = llm.start_period(store)       # zero the counter and open a new alert period
    after = read_spend(store)
    print("Counter in %s is now $%.4f." % (name, after))
    try:
        from shared.job_log import log_run

        log_run("deploy.llm_budget", "reset", {"store": name, "spent_before_usd": spent, "period": period})
    except Exception:  # noqa: BLE001
        pass
    return 0 if after == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
