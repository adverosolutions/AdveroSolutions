"""Where Offer Intel keeps its data. Everything lives under .tmp/offer_intel/,
never in git: raw posts carry member names and their own words.

    raw/<post_id>.json         one collected post (root + the author's replies)
    analyzed/<post_id>.json    gate + extract result for that post
    out/                       CSVs, digest, hand-check sheet
    look.json                  what `look` saw (categories, payload keys)
"""
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from shared.paths import tmp_dir

logger = logging.getLogger("offer_intel.files")


def root() -> Path:
    override = os.environ.get("OFFER_INTEL_DIR")
    path = Path(override) if override else tmp_dir() / "offer_intel"
    path.mkdir(parents=True, exist_ok=True)
    return path


def sub(name: str) -> Path:
    path = root() / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def raw_dir() -> Path:
    return sub("raw")


def analyzed_dir() -> Path:
    return sub("analyzed")


def out_dir() -> Path:
    return sub("out")


def _safe_id(post_id: str) -> str:
    keep = "".join(ch for ch in str(post_id) if ch.isalnum() or ch in "-_")
    if not keep:
        raise ValueError("unusable post id: %r" % (post_id,))
    return keep


def write_json(path: Path, obj: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".part")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, ensure_ascii=False, sort_keys=True)
        fh.write("\n")
    os.replace(str(tmp), str(path))


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        logger.warning("could not read %s: %s", path, exc)
        return None


def save_raw(record: Dict[str, Any]) -> Path:
    path = raw_dir() / ("%s.json" % _safe_id(record["post_id"]))
    write_json(path, record)
    return path


def load_raw(post_id: str) -> Optional[Dict[str, Any]]:
    path = raw_dir() / ("%s.json" % _safe_id(post_id))
    return read_json(path) if path.exists() else None


def iter_json(directory: Path) -> Iterator[Dict[str, Any]]:
    for path in sorted(directory.glob("*.json")):
        obj = read_json(path)
        if isinstance(obj, dict):
            yield obj


def all_raw() -> List[Dict[str, Any]]:
    return list(iter_json(raw_dir()))


def save_analyzed(result: Dict[str, Any]) -> Path:
    path = analyzed_dir() / ("%s.json" % _safe_id(result["post_id"]))
    write_json(path, result)
    return path


def load_analyzed(post_id: str) -> Optional[Dict[str, Any]]:
    path = analyzed_dir() / ("%s.json" % _safe_id(post_id))
    return read_json(path) if path.exists() else None


def all_analyzed() -> List[Dict[str, Any]]:
    return list(iter_json(analyzed_dir()))
