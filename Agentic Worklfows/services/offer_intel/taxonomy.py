"""Free text -> fixed industry and mechanism keys. Deterministic and free.

"dentists", "dental practices" and "orthodontists" have to count as one
market or the ranking means nothing. Keywords live in
config/offer_intel/taxonomy.json (matching rules in its _about).

Keys returned:
    <key>     a match
    other     the post states it, nothing in the list matches (digest lists these)
    unknown   the post does not state it
"""
import json
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional, Pattern, Tuple

from shared.paths import CONFIG_DIR

TAXONOMY_PATH = CONFIG_DIR / "offer_intel" / "taxonomy.json"
OTHER = "other"
UNKNOWN = "unknown"
PREFIX_MIN = 5


def _keyword_re(keyword: str) -> Pattern:
    word = re.escape(keyword.strip().lower())
    tail = r"" if len(keyword.strip()) >= PREFIX_MIN else r"s?\b"
    return re.compile(r"\b" + word + tail)


@lru_cache(maxsize=4)
def load(path: str = str(TAXONOMY_PATH)) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    compiled = {}
    for kind in ("industries", "mechanisms"):
        compiled[kind] = [(key, entry.get("label") or key, [_keyword_re(k) for k in entry.get("keywords") or []])
                          for key, entry in data[kind].items()]
    data["_compiled"] = compiled
    return data


def classify(text: Optional[str], kind: str, data: Optional[Dict[str, Any]] = None) -> str:
    if not text or not str(text).strip():
        return UNKNOWN
    data = data or load()
    haystack = str(text).lower()
    best = (0, OTHER)  # type: Tuple[int, str]
    for key, _label, patterns in data["_compiled"][kind]:
        hits = sum(1 for p in patterns if p.search(haystack))
        if hits > best[0]:
            best = (hits, key)
    return best[1]


def label(key: str, kind: str, data: Optional[Dict[str, Any]] = None) -> str:
    if key in (OTHER, UNKNOWN):
        return "(not stated)" if key == UNKNOWN else "Other"
    data = data or load()
    entry = data[kind].get(key) or {}
    return entry.get("label") or key


def normalize(fields: Dict[str, Any], data: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """Industry from the stated industry, then the buyer and offer line;
    mechanism from the stated mechanism, then the offer line. The fallbacks
    only fire when the first field is empty, never to override it."""
    data = data or load()

    def text(name: str) -> str:
        item = fields.get(name)
        return str(item.get("value")) if isinstance(item, dict) and item.get("value") else ""

    industry = classify(text("industry"), "industries", data)
    if industry == UNKNOWN:
        fallback = classify(" ".join(x for x in (text("buyer_role"), text("offer_one_line")) if x),
                            "industries", data)
        industry = fallback if fallback != OTHER else UNKNOWN
    mechanism = classify(text("mechanism"), "mechanisms", data)
    if mechanism == UNKNOWN:
        fallback = classify(text("offer_one_line"), "mechanisms", data)
        mechanism = fallback if fallback != OTHER else UNKNOWN
    return {"industry": industry, "mechanism": mechanism,
            "industry_text": text("industry"), "mechanism_text": text("mechanism")}


def ours(data: Optional[Dict[str, Any]] = None) -> Tuple[List[str], List[str]]:
    data = data or load()
    return list(data.get("our_mechanisms") or []), list(data.get("our_industries") or [])
