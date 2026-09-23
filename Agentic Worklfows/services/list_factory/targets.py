"""Which campaigns the Sunday list factory feeds, and in what order (O8, R10).

``config/list_factory_targets.json`` holds one entry per campaign in
``config/ids.json``. It lives under ``config/`` because the repo's
``.gitignore`` ignores ``*.json`` everywhere else: beside this module it was
never committed, so a fresh checkout had no targets and the Sunday run
refused (R10 re-review). This module loads it, refuses a file that leaves a
campaign out, and groups the enabled entries into one source pull per niche.

Why one pull per niche, not one per campaign: the Apify actor returns
byte-identical rows for identical filters (measured, see ``sources.py``), and
both campaigns of a niche use the same filters. Two pulls would pay Apify twice
for the same businesses, and both campaigns would then stage the same
companies, because a staged CSV is not in the suppression list until it is
uploaded. One pull, split at the staging step, costs once and mails each
business from one campaign only.

Owner decision R10 (2026-09-22): cover every cold campaign, Cleaning
Reactivation first. Nothing here invents targeting: an entry is enabled only
when its niche has an ICP rubric in ``config/icp/`` that names the campaign, and
a disabled entry must say why. The job prints and logs every disabled entry on
every run.
"""
import json
import os
from typing import Any, Dict, List, Optional

from shared.paths import CONFIG_DIR

DEFAULT_PATH = str(CONFIG_DIR / "list_factory_targets.json")

VALID_SOURCES = ("apify", "gmaps", "fixture")
VALID_VERIFIERS = ("millionverifier", "replay")


class TargetsError(Exception):
    """The targets file is missing, malformed, or leaves a campaign out."""


def load(path: Optional[str] = None, campaigns: Optional[Dict[str, Any]] = None,
         icp_dir: Optional[str] = None) -> Dict[str, Any]:
    """Read and validate the targets file.

    ``campaigns`` defaults to ``shared.settings.CAMPAIGNS`` (config/ids.json).
    Every campaign there must have exactly one entry, so a campaign added to
    ids.json without a decision about its leads fails loudly here instead of
    silently running dry.
    """
    path = path or DEFAULT_PATH  # jobs/list_factory.py --targets overrides it
    if campaigns is None:
        from shared import settings

        campaigns = settings.CAMPAIGNS
    if icp_dir is None:
        from services.list_factory import icp

        icp_dir = icp.icp_dir()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, IOError, ValueError) as exc:
        raise TargetsError("could not read the list-factory targets at %s: %s" % (path, exc))
    entries = doc.get("campaigns")
    if not isinstance(entries, list) or not entries:
        raise TargetsError("%s has no campaigns list" % path)
    defaults = doc.get("defaults") or {}
    seen = []  # type: List[str]
    problems = []  # type: List[str]
    out = []  # type: List[Dict[str, Any]]
    for raw in entries:
        entry = dict(raw or {})
        key = entry.get("campaign_key") or ""
        if key in seen:
            problems.append("%s appears twice" % key)
            continue
        seen.append(key)
        if key not in campaigns:
            problems.append("%s is not a campaign in config/ids.json" % key)
            continue
        niche = entry.get("niche") or campaigns[key].get("niche") or ""
        entry["niche"] = niche
        entry["enabled"] = bool(entry.get("enabled"))
        entry["source"] = entry.get("source") or defaults.get("source") or ""
        entry["verify"] = entry.get("verify") or defaults.get("verify") or ""
        try:
            entry["weekly_target"] = int(entry.get("weekly_target") or 0)
        except (TypeError, ValueError):
            problems.append("%s has a weekly_target that is not a number" % key)
            continue
        if entry["enabled"]:
            rubric_path = os.path.join(icp_dir, "%s.json" % niche)
            rubric_campaigns = {}  # type: Dict[str, Any]
            try:
                with open(rubric_path, "r", encoding="utf-8") as fh:
                    rubric_campaigns = (json.load(fh) or {}).get("campaigns") or {}
            except (OSError, IOError, ValueError):
                problems.append("%s is enabled but has no ICP rubric at %s" % (key, rubric_path))
                continue
            if key not in rubric_campaigns.values():
                problems.append("%s is enabled but config/icp/%s.json does not name it in 'campaigns'"
                                % (key, niche))
            if entry["weekly_target"] <= 0:
                problems.append("%s is enabled with no weekly_target" % key)
            if entry["source"] not in VALID_SOURCES:
                problems.append("%s names source %r (one of %s)" % (key, entry["source"], ", ".join(VALID_SOURCES)))
            if entry["verify"] not in VALID_VERIFIERS:
                problems.append("%s names verifier %r (one of %s)"
                                % (key, entry["verify"], ", ".join(VALID_VERIFIERS)))
        elif not (entry.get("disabled_reason") or "").strip():
            problems.append("%s is disabled without a disabled_reason" % key)
        out.append(entry)
    missing = [key for key in campaigns if key not in seen]
    if missing:
        problems.append("no entry for %s: every campaign in config/ids.json needs one, enabled or "
                        "disabled with a reason" % ", ".join(sorted(missing)))
    if problems:
        raise TargetsError("list-factory targets at %s are not usable: %s" % (path, "; ".join(problems)))
    return {"path": path, "as_of": doc.get("as_of"), "target_basis": doc.get("target_basis"),
            "entries": out}


def enabled(targets: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [e for e in targets["entries"] if e["enabled"]]


def disabled(targets: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [e for e in targets["entries"] if not e["enabled"]]


def niche_groups(targets: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One group per niche, in the order the file lists the campaigns.

    The first enabled entry decides which niche runs first, so Cleaning
    Reactivation at the top of the file puts the cleaning pull first, and
    inside a group the campaigns keep file order, which is the order the staged
    leads are handed out in.
    """
    groups = []  # type: List[Dict[str, Any]]
    by_niche = {}  # type: Dict[str, Dict[str, Any]]
    for entry in enabled(targets):
        group = by_niche.get(entry["niche"])
        if group is None:
            group = {"niche": entry["niche"], "source": entry["source"], "verify": entry["verify"],
                     "campaigns": []}
            by_niche[entry["niche"]] = group
            groups.append(group)
        elif (group["source"], group["verify"]) != (entry["source"], entry["verify"]):
            raise TargetsError(
                "%s and %s share the %s pull but name different sources or verifiers"
                % (group["campaigns"][0][0], entry["campaign_key"], entry["niche"]))
        group["campaigns"].append((entry["campaign_key"], entry["weekly_target"]))
    for group in groups:
        group["target"] = sum(t for _k, t in group["campaigns"])
    return groups
