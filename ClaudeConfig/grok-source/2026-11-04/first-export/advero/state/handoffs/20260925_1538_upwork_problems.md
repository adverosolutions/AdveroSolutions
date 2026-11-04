# Problems — Upwork draft run 2026-09-25 15:38 CDT

## API / discovery quirks (non-blocking)
- `list_rooms` (limit=100) returned only 3 rooms with hasMore=false. Dashboard messages preview showed 5 (added John Smith + Mainul Haque). Blocked / lost-access rooms appear omitted from `list_rooms`.
- `get_room` / `find_room` for Accepted proposals with no client-started conversation returned NOT_FOUND (expected).
- `search_rooms` by name was empty for Mainul/John in some queries; `list_messages` worked once room_id was known.

## Blocked rooms (listed once, no draft)
- **Mainul Haque, RoutVox Consulting LLC** — `room_eede7f6bb60e18378ba2c10d69bdedbf` — "Automation Specialist – Work from Anywhere (EST-friendly)". Newest: System blocked (2026-09-09). Prior client message 2026-08-27 asking to schedule (Google Calendar link — would be NEEDS_YOU / never pasted). Not drafted.
- **John Smith** — `room_ceda04038bd9eff1e60d4a52eb026a5f` — "Claude Code Dashboard Creator". System blocked (2026-09-16) then lost access (2026-09-25). Lorenzo last substantive (2026-09-09). Listed as blocked once; not awaiting reply.

## No other blockers
- KILL_SWITCH: clear
- ANTHROPIC_API_KEY: unset (ask_opus → Claude Code CLI / Max); unused (0 drafts)
- No Upwork write/confirm tools called
