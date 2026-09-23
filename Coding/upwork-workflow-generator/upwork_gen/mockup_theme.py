"""Per-platform chrome and palette for the builder-mockup target.

Merged in from the standalone mockup generator so one WorkflowSpec drives every
output. Only the theming lives here; the card stack is built in
compile_mockup.py from the same graph the n8n and Excalidraw targets read.

The two builders differ in ways a client will notice instantly if you get them
wrong — Zapier numbers its steps and is orange, GoHighLevel does not number and
is blue, and their top bars carry different controls. Everything that differs
lives here so the renderer stays one code path.

No logos are used anywhere. App tiles are drawn from initials on a generated
colour, which sidesteps trademark use entirely and — the practical reason —
keeps the file self-contained with no network request that could fail to paint
mid-recording.
"""

from __future__ import annotations

from typing import Dict

THEMES: Dict[str, Dict[str, object]] = {
    "ghl": {
        "name": "GoHighLevel",
        "accent": "#188bf6",
        "accent_soft": "#e8f2fe",
        "canvas": "#f6f7f9",
        "card": "#ffffff",
        "border": "#e3e7ee",
        "text": "#22272f",
        "muted": "#6b7280",
        "line": "#c8cfda",
        "grid": True,          # GHL's canvas carries a faint dot grid.
        "numbered": False,     # It labels cards by role, not by index.
        "publish": "Publish",
        "draft_pill": True,
        "tabs": ("Builder", "Settings", "History", "Enrollment History"),
        "data_label": "Sample payload",
        "trigger_kicker": "Trigger",
        "radius": "10px",
        "card_w": "440px",
    },
    "zapier": {
        "name": "Zapier",
        "accent": "#ff4f00",
        "accent_soft": "#ffece4",
        "canvas": "#f7f6f3",
        "card": "#ffffff",
        "border": "#e2ddd5",
        "text": "#2d2e2e",
        "muted": "#6f6f6f",
        "line": "#cfc9c0",
        "grid": False,
        "numbered": True,
        "publish": "Publish",
        "draft_pill": False,
        "tabs": (),
        "data_label": "Test data",
        "trigger_kicker": "Trigger",
        "radius": "8px",
        "card_w": "420px",
    },
}

# Ten colours that sit together without any one shouting. Assignment is by a
# stable hash of the app name, so the same app is the same colour in every
# mockup you ever record — small thing, but inconsistency between two Looms of
# the same stack is the kind of detail that reads as sloppy.
TILE_COLORS = (
    "#2563eb", "#0891b2", "#7c3aed", "#db2777", "#ea580c",
    "#16a34a", "#0f766e", "#4f46e5", "#b45309", "#be123c",
)

# A few apps people recognise by colour. Anything not listed gets a hashed one.
KNOWN_TILES = {
    "gohighlevel": "#188bf6",
    "highlevel": "#188bf6",
    "ghl": "#188bf6",
    "zapier": "#ff4f00",
    "slack": "#4a154b",
    "gmail": "#ea4335",
    "google sheets": "#0f9d58",
    "google calendar": "#4285f4",
    "hubspot": "#ff7a59",
    "stripe": "#635bff",
    "twilio": "#f22f46",
    "openai": "#10a37f",
    "chatgpt": "#10a37f",
    "claude": "#d97757",
    "anthropic": "#d97757",
    "airtable": "#fcb400",
    "notion": "#111111",
    "calendly": "#006bff",
    "facebook lead ads": "#1877f2",
    "facebook": "#1877f2",
    "instagram": "#c13584",
    "webhook": "#64748b",
    "webhooks": "#64748b",
    "shopify": "#5e8e3e",
    "salesforce": "#00a1e0",
    "mailchimp": "#ffe01b",
    "typeform": "#262627",
    "vapi": "#5b21b6",
}


def tile_color(app: str) -> str:
    key = (app or "").strip().lower()
    if key in KNOWN_TILES:
        return KNOWN_TILES[key]
    if not key:
        return "#94a3b8"
    # Deterministic across runs and across Python processes — `hash()` is not,
    # since string hashing is randomised per interpreter.
    total = 0
    for index, char in enumerate(key):
        total += (index + 1) * ord(char)
    return TILE_COLORS[total % len(TILE_COLORS)]


def initials(app: str) -> str:
    words = [w for w in (app or "").replace("-", " ").replace(".", " ").split() if w]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[1][0]).upper()


def theme_for(platform: str) -> Dict[str, object]:
    return THEMES[platform]
