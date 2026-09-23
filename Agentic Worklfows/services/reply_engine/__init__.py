"""Reply engine (Blueprint S1): classify -> route -> draft -> approve.

Shadow contract: MODE=shadow (default) means every write to Instantly or GHL
returns a would_do record from shared.settings.guard_write() and nothing
reaches a live system. Rule (2026-09-22): an engine email is sent
automatically only when its text is exactly a template Lorenzo approved with
jobs/approve_templates.py and unchanged since, the template kill switch is
off, and every send check passes; anything else goes to Lorenzo as an
approval card (replies) or is held (cadence, show-rate, no-show). See
template_gate.py.

    from services.reply_engine.app import process_event
"""
__all__ = ["models", "classify", "draft", "router", "approval", "app", "poller", "replay"]
