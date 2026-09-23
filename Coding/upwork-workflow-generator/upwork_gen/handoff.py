"""Get the generated artifacts onto the screen with no file-opening.

Both canvases accept a paste — n8n takes workflow JSON dropped on the canvas,
excalidraw.com takes a scene the same way. So the whole handoff is: open both
tabs, and make the right thing available to Cmd+V.

The clipboard holds one thing at a time, so the workflow gets it (that is the
paste on the critical path) and the diagram is one command away. Nothing here
drives the UI — keyboard automation would shave a keystroke and add a class of
failure that shows up mid-recording, which is the worst possible time.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config.json")
OUT_DIR = os.path.join(ROOT, "out")

EXCALIDRAW_URL = "https://excalidraw.com"

_DEFAULTS = {
    "n8n_url": "",
    # Empty means the system default browser. Naming one keeps the canvases in
    # the browser you are actually recording, rather than whichever app macOS
    # decides owns http today.
    "browser": "",
    "make_url": "https://www.make.com/en/login",
    "open_on_run": True,
}


def load_config() -> Dict[str, object]:
    config = dict(_DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                config.update({k: v for k, v in json.load(fh).items()
                               if not k.startswith("_")})
        except (ValueError, OSError):
            pass
    return config


def save_config(values: Dict[str, object]) -> Dict[str, object]:
    config = load_config()
    config.update(values)
    payload = {
        "_note": "n8n_url should be a BLANK canvas (/workflow/new), not the "
                 "workflow list — you cannot paste onto the list page. "
                 "browser: an app name like Arc, or empty for the system default.",
    }
    payload.update(config)
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return config


def copy(text: str) -> bool:
    try:
        process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        process.communicate(text.encode("utf-8"))
        return process.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def open_url(url: str, browser: Optional[str] = None,
             reuse_fragment: Optional[str] = None) -> bool:
    """Open the URL, in a named browser when one is configured.

    When the browser is Arc, an already-open tab is focused instead of opening
    another copy — across a day of applications, duplicate tabs are their own
    kind of friction.
    """
    if not url:
        return False
    if browser == "Arc" and reuse_fragment:
        from .arc import available as arc_available, focus_or_open
        if arc_available():
            return focus_or_open(url, reuse_fragment) != "failed"
    command = ["open"]
    if browser:
        command += ["-a", browser]
    command.append(url)
    try:
        return subprocess.call(command) == 0
    except (OSError, subprocess.SubprocessError):
        return False


def warm(url: Optional[str] = None) -> None:
    """Wake the n8n instance in the background at the start of a run.

    Render's free tier sleeps after inactivity and cold-starts in 30-50s. Left
    to happen when the tab opens, that is half a minute of spinner at exactly
    the wrong moment. Firing it up front means the instance is awake by the time
    generation finishes. Fire-and-forget: a failure here must never delay or
    break a generation.
    """
    target = url or str(load_config().get("n8n_url") or "")
    if not target:
        return
    try:
        subprocess.Popen(
            ["curl", "-s", "-o", "/dev/null", "--max-time", "60", target],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def newest(suffix: str, out_dir: Optional[str] = None) -> Optional[str]:
    """Most recent artifact of a kind — what `clip` acts on."""
    out_dir = out_dir or OUT_DIR
    if not os.path.isdir(out_dir):
        return None
    matches = [
        os.path.join(out_dir, f) for f in os.listdir(out_dir) if f.endswith(suffix)
    ]
    if not matches:
        return None
    return max(matches, key=os.path.getmtime)


def open_canvases(platform: str, has_diagram: bool) -> List[str]:
    """Open the workflow canvas and the diagram canvas. Returns status lines."""
    config = load_config()
    browser = str(config.get("browser") or "") or None
    lines: List[str] = []

    if platform == "n8n":
        url = str(config.get("n8n_url") or "")
        if url:
            open_url(url, browser, "/workflow/")
            lines.append("n8n canvas — Cmd+V here first")
        else:
            lines.append(
                "no n8n_url set — run: python3 -m upwork_gen config --n8n-url <your instance>"
            )
    else:
        url = str(config.get("make_url") or "")
        if url:
            open_url(url, browser)
            lines.append("opened {}".format(url))

    if has_diagram:
        open_url(EXCALIDRAW_URL, browser, "excalidraw.com")
        lines.append("excalidraw — run ./flow, then Cmd+V there")

    return lines
