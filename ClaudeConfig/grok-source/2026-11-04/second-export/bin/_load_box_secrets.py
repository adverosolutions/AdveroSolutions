import json, os
from pathlib import Path

def apply():
    """Load SendToUser card secrets into os.environ. Never print values."""
    p = Path("/home/box/sand-data/box-secrets.json")
    if not p.exists():
        return
    try:
        data = json.loads(p.read_text())
    except PermissionError:
        return
    for name, raw in (data.get("card") or {}).items():
        if os.environ.get(name):
            continue
        if isinstance(raw, str) and raw:
            os.environ[name] = raw
