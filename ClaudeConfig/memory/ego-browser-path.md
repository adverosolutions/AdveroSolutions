---
name: ego-browser-path
description: ego lite browser was removed; its stale URL-handler registration hijacked the default browser until fixed — Lorenzo's default browser is Dia
metadata:
  node_type: memory
  type: reference
  originSessionId: 60632215-3c8e-4876-bde0-9b1b5e53ec0a
  modified: 2026-08-13T19:57:04.764Z
---

ego lite (`com.citrolabs.ego.lite`, formerly `/Applications/ego lite.app` + CLI at `~/.local/bin/ego-browser`) is **no longer installed** as of 2026-08-13 — mdfind finds no bundle. Do not prescribe ego-browser commands.

Its ghost LaunchServices registration kept http/https pointed at the missing app, so links fell back to Safari even though Lorenzo's chosen default browser is **Dia** (`company.thebrowser.dia`). Fixed 2026-08-13 via `NSWorkspace.setDefaultApplicationAtURL` (PyObjC, now pip-installed --user); manual edits to `com.apple.launchservices.secure.plist` do NOT work on this macOS — use the API. Backup of the pre-fix plist: `~/Library/Preferences/com.apple.LaunchServices/com.apple.launchservices.secure.plist.bak-ego`.

**How to apply:** anything that should open in Lorenzo's browser can just use `open <url>` — it lands in Dia now. If default-browser weirdness recurs, check for stale handler bundle ids first.
