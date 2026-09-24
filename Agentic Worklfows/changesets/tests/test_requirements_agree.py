"""The top-level requirements.txt must not undo the engine's pins.

Both files install into the same python3. The top-level file serves the old
execution/ scripts; if it pinned an older anthropic/httpx/pydantic than
services/reply_engine/requirements.txt, `pip install -r requirements.txt`
from the code root would break every engine model call (shared/llm.py passes
`thinking=`, which old anthropic SDKs reject).
"""
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
TOP = BASE_DIR / "requirements.txt"
ENGINE = BASE_DIR / "services" / "reply_engine" / "requirements.txt"


def _pins(path):
    pins = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        m = re.match(r"^([A-Za-z0-9_.\-]+)(\[[^\]]*\])?\s*==\s*(\S+)$", line)
        if m:
            pins[re.sub(r"[-_.]+", "-", m.group(1)).lower()] = m.group(3)
    return pins


def test_every_package_pinned_in_both_files_has_the_same_pin():
    top, engine = _pins(TOP), _pins(ENGINE)
    shared = sorted(set(top) & set(engine))
    assert "anthropic" in shared and "httpx" in shared and "pydantic" in shared
    mismatched = ["%s: top-level %s, engine %s" % (n, top[n], engine[n]) for n in shared if top[n] != engine[n]]
    assert mismatched == [], "requirements.txt disagrees with services/reply_engine/requirements.txt: %s" % (
        "; ".join(mismatched))
