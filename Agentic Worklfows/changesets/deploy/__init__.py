"""Deploy tools for the Modal reply engine (runbooks/deployment.md).

modal_secret.py   build the Modal secret from .env (names and lengths only; --create runs it)
verify_health.py  post-deploy check: /health must report the expected mode, live flag and BASE_URL host
watch_report.py   read-only summary of the deployed evidence and the laptop runs against the 48-hour exit criteria
cutover.py        shadow -> live: hand-off list, clean live store, seeded poller cursor;
                  --reset, --redo, and --seed-shadow-from-live for rollback
budget.py         the LLM spend counter in the DEPLOYED store: status and reset
bounded_logs.py   a time-boxed read of `modal app logs` (the CLI command streams forever)

Every script is run by Lorenzo from his own terminal. None of them is run by
an agent, and none of them sets MODE or ALLOW_LIVE_WRITES.
"""
