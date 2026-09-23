"""Self-maintenance: things that must happen on every run without being asked.

Three jobs, all of which were previously manual and therefore skippable:

* **Corpus capture.** Every job post is archived with what it matched. This is
  the only record of what the classifier is actually seeing, and it is what
  makes it possible to re-derive better keywords later. Losing it means losing
  the ability to improve.
* **Self-check.** Cheap integrity pass that surfaces silent degradation — an
  archetype with no keywords is invisible to the classifier, and nothing about
  a normal run would reveal that.
* **Auto-commit.** A promotion writes new files into the vault. Left
  uncommitted they are exactly as exposed as the whole project was before it
  was tracked, so the vault commits itself whenever it changes.
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VAULT_DIR = os.path.join(ROOT, "vault")
ARCHETYPE_DIR = os.path.join(VAULT_DIR, "archetypes")
SOURCES_DIR = os.path.join(VAULT_DIR, "sources")
CORPUS_PATH = os.path.join(VAULT_DIR, "corpus.jsonl")
KEYWORDS_PATH = os.path.join(VAULT_DIR, "keywords.json")


# --------------------------------------------------------------------------
# Corpus
# --------------------------------------------------------------------------


def record_corpus(job_text: str, archetype: Optional[str], engine: str,
                  platform: str, confidence: float) -> None:
    """Append one line per generation. Append-only, never rewritten.

    Kept as JSONL rather than a file per post so a hundred applications do not
    become a hundred files, and so it can be mined in one pass.
    """
    if not job_text or not job_text.strip():
        return
    entry = {
        "at": datetime.datetime.now().isoformat(timespec="seconds"),
        "archetype": archetype,
        "engine": engine,
        "platform": platform,
        "confidence": round(float(confidence), 1),
        "text": job_text.strip(),
    }
    try:
        with open(CORPUS_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass  # never let bookkeeping break a generation


def archive_source(archetype: str, job_text: str, overwrite: bool = False) -> bool:
    """Keep the canonical posting for a learned archetype.

    The first post to produce an archetype is the one its keywords came from,
    so it is not overwritten by later posts that merely matched it.
    """
    if not archetype or not job_text:
        return False
    if not os.path.isdir(SOURCES_DIR):
        os.makedirs(SOURCES_DIR)
    path = os.path.join(SOURCES_DIR, "{}.txt".format(archetype))
    if os.path.exists(path) and not overwrite:
        return False
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(job_text.strip() + "\n")
        return True
    except OSError:
        return False


def corpus_stats() -> Dict[str, Any]:
    if not os.path.exists(CORPUS_PATH):
        return {"runs": 0, "by_archetype": {}, "by_engine": {}}
    runs = 0
    by_archetype: Dict[str, int] = {}
    by_engine: Dict[str, int] = {}
    with open(CORPUS_PATH, "r", encoding="utf-8") as fh:
        for line in fh:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            runs += 1
            key = entry.get("archetype") or "(no match)"
            by_archetype[key] = by_archetype.get(key, 0) + 1
            engine = entry.get("engine") or "?"
            by_engine[engine] = by_engine.get(engine, 0) + 1
    return {"runs": runs, "by_archetype": by_archetype, "by_engine": by_engine}


# --------------------------------------------------------------------------
# Self-check
# --------------------------------------------------------------------------


def selfcheck() -> List[str]:
    """Fast integrity pass. Returns problems worth showing after a run.

    Deliberately cheap — this runs on every generation, and a health check that
    costs a second is a health check that gets turned off.
    """
    problems: List[str] = []

    from .learn import load_learned

    learned = load_learned()
    specs = set()
    if os.path.isdir(ARCHETYPE_DIR):
        specs = {f[:-5] for f in os.listdir(ARCHETYPE_DIR) if f.endswith(".json")}

    if not specs:
        problems.append("vault/archetypes is empty — the vault engine cannot run")

    for archetype_id, entry in learned.items():
        if not entry.get("kw"):
            problems.append(
                "learned archetype {!r} has no keywords — it can never be matched; "
                "re-promote it with --jd".format(archetype_id)
            )
        if archetype_id not in specs:
            problems.append(
                "keywords exist for {!r} but its spec file is gone".format(archetype_id)
            )
        if not os.path.exists(os.path.join(SOURCES_DIR, "{}.txt".format(archetype_id))):
            problems.append(
                "no source posting kept for {!r} — keywords cannot be re-derived "
                "if they go bad".format(archetype_id)
            )

    for name in ("n8n_nodes.json", "make_modules.json"):
        if not os.path.exists(os.path.join(ROOT, "upwork_gen", "catalog", name)):
            problems.append("catalog {} is missing".format(name))

    return problems


# --------------------------------------------------------------------------
# Auto-commit
# --------------------------------------------------------------------------


def _git(*args: str) -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "-C", ROOT] + list(args),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.decode("utf-8", "replace")


# What a generation run is allowed to commit. Deliberately narrow: the vault
# and the run log are what a run produces. Code changes, and anything else in
# the repository, stay the author's to commit deliberately.
_TRACKED_PATHS = [VAULT_DIR, os.path.join(ROOT, "runs.csv")]


def vault_is_dirty() -> bool:
    status = _git("status", "--porcelain", "--", *_TRACKED_PATHS)
    return bool(status and status.strip())


def autocommit(reason: str) -> Optional[str]:
    """Commit what this run produced. Returns a short description, or None.

    Scoped on purpose: a generation should never sweep up unrelated edits
    elsewhere in the repository, and should never commit code — only the vault
    it just grew and the log of the run that grew it.
    """
    if _git("rev-parse", "--git-dir") is None:
        return None
    if not vault_is_dirty():
        return None

    if _git("add", "--", *_TRACKED_PATHS) is None:
        return None

    message = "Vault: {}\n\nCommitted automatically after a generation run.".format(reason)
    if _git("commit", "-m", message, "--", *_TRACKED_PATHS) is None:
        return None

    head = _git("rev-parse", "--short", "HEAD")
    changed = _git("show", "--stat", "--oneline", "HEAD")
    count = 0
    if changed:
        for line in changed.splitlines():
            if "|" in line:
                count += 1
    return "{} ({} file{})".format(
        (head or "").strip(), count, "" if count == 1 else "s"
    )
