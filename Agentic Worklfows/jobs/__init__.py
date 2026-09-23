"""Scheduled jobs (Blueprint Section 6, O1-O8).

Every job here has ``--dry-run``, writes a Job_Log row through
``shared.job_log.log_run`` and never writes to a live system unless
MODE=live and ALLOW_LIVE_WRITES=1 are both set (see shared/README.md).
"""
