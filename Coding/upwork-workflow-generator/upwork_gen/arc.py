"""Drive Arc tabs from the command line.

Two jobs: focus a tab that is already open rather than opening another copy of
it, and paste the diagram into Excalidraw without a keystroke from the user.

The paste clears the canvas first (Cmd+A, Delete) so a new diagram replaces the
last one instead of landing on top of it. That is destructive, so the sequence
**verifies the focused tab is actually Excalidraw before sending anything**. If
focusing fails for any reason — the tab was closed, Arc was mid-navigation, the
window changed — the keystrokes are never sent. A select-all-and-delete
delivered to the wrong tab is a far worse outcome than a diagram that did not
paste.
"""

from __future__ import annotations

import subprocess
from typing import Optional

EXCALIDRAW = "excalidraw.com"


def _osascript(script: str) -> Optional[str]:
    """Run AppleScript, returning stdout, or None if it failed."""
    try:
        result = subprocess.run(
            ["osascript", "-"], input=script.encode("utf-8"),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", "replace").strip()


def available() -> bool:
    return _osascript('tell application "System Events" to return (exists process "Arc")') == "true"


def focus_tab(fragment: str) -> Optional[str]:
    """Focus the first tab whose URL contains `fragment`.

    Returns the active tab's URL afterwards, so the caller can confirm the
    focus actually took effect rather than assuming it did.
    """
    script = '''
    tell application "Arc"
      tell front window
        set found to 0
        set i to 0
        repeat with t in tabs
          set i to i + 1
          if URL of t contains "{}" then
            if found = 0 then set found to i
          end if
        end repeat
        if found = 0 then return "NOTFOUND"
        tell tab found to select
        return URL of active tab
      end tell
    end tell
    '''.format(fragment)
    return _osascript(script)


def focus_or_open(url: str, fragment: Optional[str] = None) -> str:
    """Reuse an open tab when there is one; otherwise open the URL.

    Opening unconditionally accumulates duplicate tabs across a day of
    applications, which is its own kind of friction.
    """
    key = fragment or url
    active = focus_tab(key)
    if active and active != "NOTFOUND":
        return "focused"
    try:
        subprocess.call(["open", "-a", "Arc", url])
    except (OSError, subprocess.SubprocessError):
        return "failed"
    return "opened"


def paste_into_excalidraw(clear_first: bool = True) -> str:
    """Focus Excalidraw and paste whatever is on the clipboard.

    The clipboard must already hold the scene. Returns a short status string.
    """
    active = focus_tab(EXCALIDRAW)
    if active is None:
        return "arc-unreachable"
    if active == "NOTFOUND":
        return "no-excalidraw-tab"
    # The guard: only send keystrokes once Arc reports Excalidraw is frontmost.
    if EXCALIDRAW not in active:
        return "focus-failed"

    clear = '''
      keystroke "a" using command down
      delay 0.15
      key code 51
      delay 0.15
    ''' if clear_first else ""

    script = '''
    tell application "Arc" to activate
    delay 0.4
    tell application "System Events"
      tell process "Arc"
        {}
        keystroke "v" using command down
      end tell
    end tell
    return "ok"
    '''.format(clear)
    result = _osascript(script)
    return "pasted" if result == "ok" else "keystroke-failed"
