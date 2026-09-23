"""Retro packet generator (Blueprint O6, brief A10) and the client scorecard (F3, A12).

One generator, two outputs. ``packet.build_internal_packet`` produces Lorenzo's
Friday retro; ``scorecard.build_client_scorecard`` produces a client-facing
weekly scorecard from the same collected week. Both return a
``render.Packet`` and are rendered by ``render.render_markdown``.

Nothing in here writes to a live system. The job that drives it
(``jobs/retro_packet.py``) writes a markdown file under ``.tmp/retro/`` and
records the Skool post as a would_do; posting stays manual, forever.

    from services.retro import collect, packet, render
    week = collect.collect_week(now, ...)
    md = render.render_markdown(packet.build_internal_packet(week))
"""
__all__ = [
    "weeks", "metrics", "recaps", "sources", "lessons", "render", "packet", "scorecard", "collect",
]
