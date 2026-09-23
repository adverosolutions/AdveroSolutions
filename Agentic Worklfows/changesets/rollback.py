"""Rollback points for every change-set that PATCHes ``/campaigns/{id}``.

One module, so the four scripts that change a live campaign (Phase 0 copy,
insurance promotion, inbox actions and the Oct 11 capacity change-set) cannot
disagree about what a rollback point is. GOL-9 and SAF-10 (re-review
2026-09-22) found every way the old per-script backups could be confused:
dry-run copies with no suffix in the same folder as the real ones, a restore
that accepted any JSON file with an ``id``, a full-body PATCH the API rejects,
a re-apply that overwrote the before-image, and a ``.preapply`` file said to
mean "wrote nothing" after a PATCH that had actually landed.

**What a rollback point is.** A JSON file holding the complete campaign object
as it was read immediately before the PATCH, plus a ``_rollback_point`` block
naming the script that wrote it, the campaign id and key, the fields that PATCH
changed, the values it set them to (the after-image) and the kind.
``--restore`` accepts a file only when all of these match the script and the
``--campaign`` it is run with. It then reads live first, prints what it would
change field by field, refuses when a field has moved on since the apply
(neither the after-image nor the before-image: a later apply, a burned inbox
removed, a hand edit) unless ``--override-later-changes`` is given, asks for
the typed confirmation, and PATCHes **only those fields** (all of them in the
contract's PATCH allow-list, because ``PATCH /campaigns/{id}`` is
``additionalProperties: false``). Restore compares by equality, never by
containment, so an additive change is not mistaken for "already restored".

Kinds, and the file name each one gets:

=============  =================================  ==============================
kind           name                               restorable
=============  =================================  ==============================
apply          ``<stem>.json`` (no suffix)        yes: THE rollback point
preapply       ``<stem>.preapply.json``           only with --accept-interrupted
not_applied    ``<stem>.not_applied.json``        no: shadow mode, no HTTP request
prerestore     ``<stem>.prerestore.json``         no: re-run the apply instead
dryrun         ``<stem>.dryrun.json`` under .tmp  no
evidence       ``<stem>.evidence.json``           no (accounts, label lists)
=============  =================================  ==============================

``preapply`` exists only while a PATCH is in flight. Every exit path renames
it. After an acknowledged PATCH, and after ANY PATCH error, it becomes the
unsuffixed rollback point: a 504 can land after the re-read that says
"unchanged", so an error must never leave the only before-image
unrestorable, and restoring a campaign that never changed is a no-op. Only a
shadow-mode run, which sent no HTTP request, becomes ``.not_applied.json``. A
``.preapply.json`` found on disk therefore means the process died mid-PATCH,
and nothing else.

Python 3.9.
"""
import contextlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Tuple

from shared import settings
from shared.paths import tmp_dir

SCHEMA = 2   # 2: the after-image of the changed fields is recorded (restore drift check)
META_KEY = "_rollback_point"

KIND_APPLY = "apply"
KIND_PREAPPLY = "preapply"
KIND_NOT_APPLIED = "not_applied"
KIND_PRERESTORE = "prerestore"
KIND_DRYRUN = "dryrun"
KIND_EVIDENCE = "evidence"
KINDS = (KIND_APPLY, KIND_PREAPPLY, KIND_NOT_APPLIED, KIND_PRERESTORE, KIND_DRYRUN, KIND_EVIDENCE)
NON_APPLY_SUFFIXES = tuple(".%s.json" % k for k in KINDS if k != KIND_APPLY)

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_REFUSED = 2
EXIT_API = 3

# config/instantly_api_contract.md, PATCH /campaigns/{id}: the allow-list. A
# rollback point may only name fields from here, so a restore can never send a
# key the API rejects.
PATCHABLE_CAMPAIGN_FIELDS = (
    "name", "pl_value", "campaign_schedule", "sequences", "email_gap", "random_wait_max",
    "text_only", "first_email_text_only", "email_list", "daily_limit", "stop_on_reply",
    "link_tracking", "open_tracking", "stop_on_auto_reply", "daily_max_leads",
    "prioritize_new_leads", "auto_variant_select", "match_lead_esp", "stop_for_company",
    "insert_unsubscribe_header", "allow_risky_contacts", "disable_bounce_protect", "cc_list",
    "bcc_list", "owned_by", "provider_routing_rules", "limit_emails_per_company_override",
)

WHY_NOT = {
    KIND_PREAPPLY: ("it is a .preapply file: the run that wrote it died while its PATCH was in "
                    "flight. Compare it with the live campaign first; if you are sure it is the "
                    "state you want back, re-run with --accept-interrupted"),
    KIND_NOT_APPLIED: ("it is a .not_applied file: the run was in shadow mode and sent no HTTP "
                       "request, so there is nothing to roll back"),
    KIND_PRERESTORE: ("it is a .prerestore file (the state a restore overwrote). To undo a "
                      "restore, re-run the apply; restoring it is refused so the rollback point "
                      "is never ambiguous"),
    KIND_DRYRUN: "it is a dry-run copy, which may hold the already-changed state",
    KIND_EVIDENCE: "it is an evidence copy (an account or a list), not a campaign rollback point",
}


class RollbackRefused(ValueError):
    """The file is not a rollback point this script may restore."""


# ------------------------------------------------------------------ naming
def stamp(now: datetime) -> str:
    return now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def file_name(stem: str, kind: str) -> str:
    if kind not in KINDS:
        raise ValueError("unknown rollback kind %r" % kind)
    return "%s.json" % stem if kind == KIND_APPLY else "%s.%s.json" % (stem, kind)


def dryrun_dir(name: str) -> str:
    """Dry-run copies never go to changesets/backups/ (SAF-10)."""
    return str(tmp_dir() / "changeset_dryruns" / name)


def _write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False, default=str)
        fh.write("\n")
    os.replace(tmp, path)


# ------------------------------------------------------------------ writing
def build_point(script: str, kind: str, obj: Dict[str, Any], fields: Sequence[str], now: datetime,
                campaign_id: Optional[str] = None, campaign_key: Optional[str] = None,
                object_type: str = "campaign", extra: Optional[Dict[str, Any]] = None,
                after: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The full object as read, plus the ``_rollback_point`` block.

    ``after`` is the after-image: the values the PATCH is about to set for
    ``fields``. A restore compares live with it and refuses when something
    else changed those fields since (a later apply, a hand edit in the UI)."""
    bad = [f for f in fields if object_type == "campaign" and f not in PATCHABLE_CAMPAIGN_FIELDS]
    if bad:
        raise ValueError("fields %s are not in the PATCH /campaigns allow-list" % bad)
    point = dict(obj or {})
    point.pop(META_KEY, None)
    meta = {
        "schema": SCHEMA,
        "kind": kind,
        "script": script,
        "object": object_type,
        "campaign_id": campaign_id if campaign_id is not None else (obj or {}).get("id"),
        "campaign_key": campaign_key,
        "fields": sorted(fields),
        "missing_in_live": sorted(f for f in fields if f not in (obj or {})),
        "written_at": now.astimezone(timezone.utc).replace(microsecond=0).isoformat(),
        "after": dict((f, (after or {})[f]) for f in fields if f in (after or {})),
    }  # type: Dict[str, Any]
    if extra:
        meta.update(extra)
    point[META_KEY] = meta
    return point


def _free_path(directory: str, stem: str, kind: str) -> str:
    """Never overwrite: two writes in the same second get ``<stem>_2`` etc., so
    an existing before-image or rollback point is never replaced."""
    path = os.path.join(directory, file_name(stem, kind))
    n = 2
    while os.path.exists(path):
        path = os.path.join(directory, file_name("%s_%d" % (stem, n), kind))
        n += 1
    return path


def write_point(directory: str, stem: str, point: Dict[str, Any]) -> str:
    kind = point[META_KEY]["kind"]
    path = _free_path(directory, stem, kind)
    _write_json(path, point)
    return path


def relabel(path: str, kind: str, **updates: Any) -> str:
    """Move a point to another kind (file name AND the block inside agree)."""
    with open(path, "r", encoding="utf-8") as fh:
        point = json.load(fh)
    meta = point[META_KEY]
    old_kind = meta["kind"]
    suffix = ".%s.json" % old_kind if old_kind != KIND_APPLY else ".json"
    if not path.endswith(suffix):
        raise ValueError("%s does not carry the %s suffix its block claims" % (path, old_kind))
    stem = path[: -len(suffix)]
    meta["kind"] = kind
    meta.update(updates)
    new_path = stem + (".json" if kind == KIND_APPLY else ".%s.json" % kind)
    if new_path != path and os.path.exists(new_path):
        new_path = _free_path(os.path.dirname(stem), os.path.basename(stem), kind)
    _write_json(new_path, point)
    if new_path != path:
        os.remove(path)
    return new_path


# ---------------------------------------------------------------- comparing
def _norm_list(value: Any) -> Any:
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return sorted(v.strip().lower() for v in value)
    return value


def _contains(live: Any, want: Any) -> bool:
    """``want`` is contained in ``live``: dict keys recursively (the API adds
    read-only keys the staged copy does not carry), lists element by element,
    scalars by equality. APPLY side only."""
    if isinstance(want, dict):
        if not isinstance(live, dict):
            return False
        return all(k in live and _contains(live[k], v) for k, v in want.items())
    if isinstance(want, list):
        if not isinstance(live, list) or len(live) != len(want):
            return False
        return all(_contains(a, b) for a, b in zip(live, want))
    return live == want


def mismatches(live: Dict[str, Any], desired: Dict[str, Any]) -> List[str]:
    """APPLY side: keys of ``desired`` that live does not already hold, by
    containment. ``email_list`` is compared as a case-insensitive set:
    Instantly does not promise an order."""
    out = []
    for key, want in desired.items():
        have = (live or {}).get(key)
        if key == "email_list":
            if not isinstance(have, list) or _norm_list(have) != _norm_list(want or []):
                out.append(key)
        elif not _contains(have, want):
            out.append(key)
    return sorted(out)


def field_equal(key: str, have: Any, want: Any) -> bool:
    """RESTORE side: exact equality (``email_list`` as a case-insensitive
    set). Containment would call a purely additive change, say a variant
    switched off with ``v_disabled``, "already restored" (GOL-9 re-review,
    defect 5)."""
    if key == "email_list":
        return isinstance(have, list) and isinstance(want, list) and _norm_list(have) == _norm_list(want)
    return have == want


def differing(live: Dict[str, Any], target: Dict[str, Any]) -> List[str]:
    return sorted(k for k, v in target.items() if k not in (live or {}) or not field_equal(k, live[k], v))


def _steps_summary(value: Any) -> str:
    try:
        steps = (value or [{}])[0].get("steps") or []
        variants = sum(len(st.get("variants") or []) for st in steps)
        disabled = sum(1 for st in steps for v in (st.get("variants") or []) if v.get("v_disabled"))
        return "%d steps, %d variants (%d disabled)" % (len(steps), variants, disabled)
    except (AttributeError, IndexError, TypeError):
        return "unreadable sequences"


_ABSENT = object()


def diff_paths(have: Any, want: Any, path: str = "", limit: int = 5) -> List[str]:
    """Where two JSON values differ, as ``path: have -> want`` lines (at most
    ``limit``). Used so a drift line on ``sequences`` names the key that moved
    instead of printing two identical summaries (re-review round 3, defect 2)."""
    found = []  # type: List[str]

    def show(v: Any) -> str:
        if v is _ABSENT:
            return "<absent>"
        text = json.dumps(v, sort_keys=True, default=str)
        return text if len(text) <= 60 else text[:57] + "..."

    def walk(a: Any, b: Any, where: str) -> None:
        if len(found) >= limit:
            return
        if isinstance(a, dict) and isinstance(b, dict):
            for k in sorted(set(a) | set(b), key=str):
                walk(a.get(k, _ABSENT), b.get(k, _ABSENT), "%s.%s" % (where, k) if where else str(k))
            return
        if isinstance(a, list) and isinstance(b, list):
            for i in range(max(len(a), len(b))):
                walk(a[i] if i < len(a) else _ABSENT, b[i] if i < len(b) else _ABSENT, "%s[%d]" % (where, i))
            return
        if a is _ABSENT or b is _ABSENT or a != b:
            found.append("%s: %s -> %s" % (where or "(value)", show(a), show(b)))

    walk(have, want, path)
    return found


def describe_field_change(key: str, have: Any, want: Any) -> str:
    """One line per field: what a PATCH from ``have`` to ``want`` does."""
    if key == "email_list" and isinstance(want, list):
        have_l = set(_norm_list(have) if isinstance(have, list) else [])
        want_l = set(_norm_list(want))
        removed = sorted(have_l - want_l)
        added = sorted(want_l - have_l)
        return "email_list %d -> %d inboxes; removes %s; adds %s" % (
            len(have_l), len(want_l), ", ".join(removed) or "nothing", ", ".join(added) or "nothing")
    if key == "sequences":
        return "sequences %s -> %s" % (_steps_summary(have), _steps_summary(want))
    if isinstance(want, (dict, list)) or isinstance(have, (dict, list)):
        text = json.dumps(want, sort_keys=True, default=str)
        return "%s changes (to %s%s)" % (key, text[:120], "..." if len(text) > 120 else "")
    return "%s %r -> %r" % (key, have, want)


# ----------------------------------------------------------------- the PATCH
def patch_and_settle(client: Any, campaign_id: str, patch: Dict[str, Any], preapply_path: str,
                     before: Dict[str, Any]) -> Dict[str, Any]:
    """Send one PATCH and settle what the ``.preapply`` file becomes.

    ``before`` holds the same keys as ``patch`` with their pre-apply values.
    Returns {ok, outcome, path, error, response, verified_by}. ``ok`` is True
    only for a write that was verified, from the PATCH response (the updated
    Campaign object) or a re-read.

    **A PATCH error never leaves the before-image unrestorable** (re-review
    defect 2). A 504 can land after the re-read that says "unchanged", and a
    re-run then sees live matching and writes nothing, so a before-image
    relabelled "not applied" would be the only copy and restore would refuse
    it. After any error the file becomes the unsuffixed rollback point;
    restoring a campaign that never changed is a no-op.
    """
    result = {"ok": False, "outcome": None, "path": preapply_path, "error": None,
              "response": None, "verified_by": None}  # type: Dict[str, Any]
    try:
        resp = client.update_campaign(campaign_id, patch)
    except Exception as exc:  # noqa: BLE001 - settled below, then reported
        result["error"] = str(exc)[:400]
        try:
            live = client.get_campaign(campaign_id)
            if not mismatches(live, patch):
                result["outcome"] = "landed_after_error"
            elif not differing(live, before):
                result["outcome"] = "unchanged_at_reread"
            else:
                result["outcome"] = "unknown_after_error"
        except Exception as exc2:  # noqa: BLE001
            result["outcome"] = "unknown_after_error"
            result["error"] += " (the re-read failed too: %s)" % str(exc2)[:200]
        updates = {"outcome": result["outcome"], "note": "PATCH raised: %s" % result["error"][:300]}
        if result["outcome"] == "landed_after_error":
            updates.update(_stored_after(live, patch))
        result["path"] = relabel(preapply_path, KIND_APPLY, **updates)
        return result

    result["response"] = resp
    if isinstance(resp, dict) and resp.get("shadow"):
        result["outcome"] = "shadow"
        result["path"] = relabel(preapply_path, KIND_NOT_APPLIED, outcome="shadow",
                                 note="guard_write returned a shadow record; no HTTP request")
        return result

    # The PATCH was acknowledged, so the before-image is the rollback point
    # whatever the verification below says.
    stored = None  # type: Optional[Dict[str, Any]]
    if isinstance(resp, dict) and all(k in resp for k in patch) and not mismatches(resp, patch):
        result["verified_by"] = "patch_response"
        stored = resp
    else:
        try:
            live = client.get_campaign(campaign_id)
            if not mismatches(live, patch):
                result["verified_by"] = "re_read"
                stored = live
            else:
                result["error"] = ("PATCH acknowledged but a re-read does not show %s; check the "
                                   "campaign in the Instantly UI" % ", ".join(mismatches(live, patch)))
        except Exception as exc:  # noqa: BLE001
            result["error"] = "PATCH acknowledged but the verifying re-read failed: %s" % str(exc)[:200]
    result["ok"] = result["verified_by"] is not None
    result["outcome"] = "landed_verified" if result["ok"] else "acknowledged_unverified"
    updates = {"outcome": result["outcome"], "verified_by": result["verified_by"]}
    if stored is not None:
        updates.update(_stored_after(stored, patch))
    result["path"] = relabel(preapply_path, KIND_APPLY, **updates)
    return result


def _stored_after(stored: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    """Round 3, defect 2: the after-image is what Instantly STORED for the
    patched fields (it may add defaults such as ``v_disabled: false``), not
    what was sent, or a later restore would call its own apply a drift."""
    after = dict((k, stored[k] if k in stored else v) for k, v in patch.items())
    return {"after": after, "after_source": "stored"}


def describe_outcome(settled: Dict[str, Any], rel: Callable[[str], str] = lambda p: p) -> str:
    o = settled.get("outcome")
    path = rel(settled["path"]) if settled.get("path") else "-"
    if o == "landed_verified":
        return "PATCH landed and was verified (%s). Rollback point: %s" % (settled["verified_by"], path)
    if o == "landed_after_error":
        return ("PATCH raised (%s) but a re-read shows it LANDED. Rollback point: %s"
                % (settled["error"], path))
    if o == "unchanged_at_reread":
        return ("PATCH raised (%s) and an immediate re-read still shows the old values. A gateway "
                "error does not prove the write was dropped (it can land later), so the "
                "before-image is kept as the rollback point %s; restoring an unchanged campaign is "
                "a no-op. Re-read the campaign before re-running." % (settled["error"], path))
    if o == "unknown_after_error":
        return ("PATCH raised (%s) and its outcome could not be established. The before-image is "
                "kept as the rollback point %s; check the campaign in the UI." % (settled["error"], path))
    if o == "acknowledged_unverified":
        return "PATCH acknowledged but NOT verified: %s. Rollback point: %s" % (settled["error"], path)
    if o == "shadow":
        return "shadow record only; no HTTP request was made (%s)" % path
    return "outcome %r (%s)" % (o, path)


# ------------------------------------------------------------------ restore
def load_point(path: str, script: str, campaign_id: str,
               accept_kinds: Sequence[str] = (KIND_APPLY,)) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """(point, meta, restore_patch) for a genuine rollback point, else RollbackRefused."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            point = json.load(fh)
    except (OSError, ValueError) as exc:
        raise RollbackRefused("cannot read %s: %s" % (path, exc))
    meta = point.get(META_KEY) if isinstance(point, dict) else None
    if not isinstance(meta, dict):
        raise RollbackRefused(
            "%s is not a rollback point: it has no %s block. Dry-run copies, legacy backups "
            "and hand-made files are refused; only the unsuffixed file an apply of %s wrote "
            "can be restored." % (path, META_KEY, script))
    if meta.get("schema") != SCHEMA:
        raise RollbackRefused("%s has rollback schema %r, expected %r (it records no after-image, "
                              "so later changes could not be detected)" % (path, meta.get("schema"), SCHEMA))
    if meta.get("script") != script:
        raise RollbackRefused("%s was written by %r, not %r: restore it with the script that "
                              "wrote it" % (path, meta.get("script"), script))
    if meta.get("object") != "campaign":
        raise RollbackRefused("%s is a %r backup, not a campaign rollback point" % (path, meta.get("object")))
    kind = meta.get("kind")
    if kind not in accept_kinds:
        raise RollbackRefused("%s is not a rollback point: %s" % (
            path, WHY_NOT.get(kind, "its kind is %r" % kind)))
    base = os.path.basename(path)
    if kind == KIND_APPLY and base.endswith(NON_APPLY_SUFFIXES):
        raise RollbackRefused("%s says kind=apply but its name carries a non-apply suffix; it was "
                              "renamed by hand" % path)
    if meta.get("campaign_id") != campaign_id or point.get("id") != campaign_id:
        raise RollbackRefused(
            "%s holds campaign %s, but --campaign resolves to %s. Restoring it would overwrite a "
            "different campaign." % (path, meta.get("campaign_id") or point.get("id"), campaign_id))
    fields = meta.get("fields") or []
    bad = [f for f in fields if f not in PATCHABLE_CAMPAIGN_FIELDS]
    if bad or not fields:
        raise RollbackRefused("%s names fields %s, which cannot be PATCHed" % (path, bad or "none"))
    after = meta.get("after")
    if not isinstance(after, dict) or any(f not in after for f in fields):
        raise RollbackRefused("%s records no after-image for %s, so a later change to those fields "
                              "could not be detected" % (path, fields))
    restore_patch = dict((f, point[f]) for f in fields if f in point)
    if not restore_patch:
        raise RollbackRefused("%s holds no before-value for %s" % (path, fields))
    return point, meta, restore_patch


OVERRIDE_WITH_YES = (
    "REFUSED: --override-later-changes cannot be combined with --yes. Undoing changes made after "
    "the apply needs a person to read the printed diff and type the confirmation; drop --yes.")


def override_with_yes(args: Any) -> bool:
    """Round 3, defect 3: the override skips the drift gate, so it must never
    also skip the typed confirmation."""
    return bool(getattr(args, "override_later_changes", False) and getattr(args, "yes", False))


def restore(client: Any, script: str, path: str, campaign_id: str, campaign_key: str,
            backup_dir: str, stem: str, now: datetime, out: Callable[[str], None],
            accept_kinds: Sequence[str] = (KIND_APPLY,),
            confirm: Optional[Callable[[], bool]] = None,
            override_later_changes: bool = False) -> Tuple[int, Dict[str, Any]]:
    """PATCH a rollback point's fields back. Returns (exit code, details).

    Order (re-review defect 3): validate the file (no network); refuse in
    shadow (writes nothing); READ live; print what the restore would change,
    field by field; refuse when a field has moved on since the apply (it
    equals neither the recorded after-image nor the before-image) unless
    ``override_later_changes``; only THEN ask ``confirm``; READ live AGAIN
    and refuse if any of the point's fields moved while the prompt was open
    (round 3); write a ``.prerestore`` copy from that second read; PATCH only
    the fields that differ; verify by equality. ``details`` always carries
    ``override_later_changes`` and the drift lines, for the Job_Log row. Every field in the point must end up restored, or the outcome
    is ``partial`` and the exit is non-zero.
    """
    info = {"backup": path, "campaign_id": campaign_id, "campaign_key": campaign_key}  # type: Dict[str, Any]
    try:
        point, meta, restore_patch = load_point(path, script, campaign_id, accept_kinds)
    except RollbackRefused as exc:
        out("REFUSED: %s" % exc)
        info["refused"] = str(exc)
        return EXIT_INVALID, info
    fields = list(meta["fields"])
    unrestorable = sorted(f for f in fields if f not in restore_patch)
    out("restore %s (%s) from %s" % (campaign_key, campaign_id, path))
    out("  rollback point written %s by %s, outcome %s, fields %s" % (
        meta.get("written_at"), meta.get("script"), meta.get("outcome"), fields))
    if not settings.is_live():
        out("REFUSED: a restore is a live write and needs MODE=live and ALLOW_LIVE_WRITES=1 (have "
            "MODE=%s). Nothing was read or written." % settings.get_mode())
        info["refused"] = "not live"
        return EXIT_REFUSED, info

    current = client.get_campaign(campaign_id)
    after = meta["after"]
    drifted = sorted(f for f in restore_patch
                     if f in current
                     and not field_equal(f, current[f], after[f])
                     and not field_equal(f, current[f], restore_patch[f]))
    drifted += sorted(f for f in restore_patch if f not in current)
    differ = differing(current, restore_patch)
    info["differ"] = differ
    info["drifted"] = drifted
    info["override_later_changes"] = bool(override_later_changes)
    drift_lines = []  # type: List[str]
    info["drift"] = drift_lines
    for f in fields:
        if f in unrestorable:
            out("  %s: NO before-value recorded; it cannot be restored" % f)
        elif f in differ:
            out("  would change: %s" % describe_field_change(f, current.get(f), restore_patch[f]))
        else:
            out("  %s: already at the rollback value" % f)
    if drifted:
        for f in drifted:
            line = ("CHANGED SINCE THE APPLY: %s (live is neither what the apply set nor what it "
                    "replaced): %s" % (f, describe_field_change(f, after.get(f), current.get(f))))
            if f != "email_list" and isinstance(current.get(f), (dict, list)):
                line += "; differs from the after-image at %s" % "; ".join(
                    diff_paths(after.get(f), current.get(f), f))
            drift_lines.append(line)
            out("  " + line)
        if not override_later_changes:
            out("REFUSED: %s changed after this rollback point was written (a later apply, a "
                "removal of a burned inbox, a hand edit). Restoring would silently undo that. "
                "Nothing was written. Re-run with --override-later-changes only if you mean to "
                "undo those changes too." % ", ".join(drifted))
            info["refused"] = "later changes: %s" % drifted
            return EXIT_REFUSED, info
        out("  --override-later-changes given: the later changes above WILL be undone.")
    if not differ:
        if unrestorable:
            out("PARTIAL: live already holds every restorable value, but %s cannot be restored "
                "from this point." % unrestorable)
            info["outcome"] = "partial"
            return EXIT_API, info
        out("  live already matches the rollback point; no PATCH sent, nothing written.")
        info["outcome"] = "already_restored"
        return EXIT_OK, info
    if confirm is not None and not confirm():
        out("aborted: confirmation did not match; nothing was written")
        info["outcome"] = "aborted"
        return EXIT_REFUSED, info
    # Round 3, defect 1: the prompt can stay open for minutes. Read again and
    # act only if none of the point's fields moved meanwhile; the .prerestore
    # copy is built from THIS read, so it holds the state actually overwritten.
    fresh = client.get_campaign(campaign_id)
    moved = sorted(f for f in fields
                   if (f in current) != (f in fresh)
                   or (f in current and not field_equal(f, fresh[f], current[f])))
    if moved:
        for f in moved:
            line = "MOVED WHILE THE PROMPT WAS OPEN: %s" % describe_field_change(f, current.get(f), fresh.get(f))
            if f != "email_list" and isinstance(fresh.get(f), (dict, list)):
                line += "; at %s" % "; ".join(diff_paths(current.get(f), fresh.get(f), f))
            out("  " + line)
        out("REFUSED: %s changed while the confirmation was open; nothing was sent or written. "
            "Re-run the restore and read the new diff." % ", ".join(moved))
        info["refused"] = "moved during the prompt: %s" % moved
        info["outcome"] = "moved_during_prompt"
        return EXIT_REFUSED, info
    current = fresh
    differ = differing(current, restore_patch)
    info["differ"] = differ
    patch = dict((k, restore_patch[k]) for k in differ)
    pre = build_point(script, KIND_PRERESTORE, current, differ, now, campaign_id, campaign_key,
                      extra={"restoring_from": path}, after=patch)
    pre_path = write_point(backup_dir, stem, pre)
    info["prerestore"] = pre_path
    out("  current live state saved to %s (not a rollback point)" % pre_path)
    out("  PATCH /campaigns/%s with %s" % (campaign_id, differ))
    try:
        resp = client.update_campaign(campaign_id, patch)
    except Exception as exc:  # noqa: BLE001
        info["error"] = str(exc)[:400]
        try:
            live = client.get_campaign(campaign_id)
            landed = not differing(live, patch)
        except Exception:  # noqa: BLE001
            landed = None
        info["outcome"] = {True: "landed_after_error", False: "not_restored_at_reread", None: "unknown"}[landed]
        out("  PATCH raised (%s); re-read says: %s" % (info["error"], info["outcome"]))
        return EXIT_API, info
    if isinstance(resp, dict) and resp.get("shadow"):
        out("  shadow record only; nothing restored")
        info["outcome"] = "shadow"
        return EXIT_REFUSED, info
    seen = None  # type: Optional[Dict[str, Any]]
    if isinstance(resp, dict) and all(k in resp for k in patch) and not differing(resp, patch):
        verified = True
    else:
        try:
            seen = client.get_campaign(campaign_id)
            verified = not differing(seen, patch)
        except Exception:  # noqa: BLE001
            verified = False
    if not verified:
        info["outcome"] = "restored_unverified"
        out("  PATCH acknowledged but a re-read does not show the restored values exactly; check the UI.")
        for f in differing(seen or {}, patch) if seen is not None else []:
            where = diff_paths(patch[f], seen.get(f), f) if f != "email_list" else []
            line = describe_field_change(f, patch[f], seen.get(f))
            out("    %s%s" % (line, ("; differs at %s" % "; ".join(where)) if where else ""))
            info.setdefault("unverified", []).append(line + ("; " + "; ".join(where) if where else ""))
        return EXIT_API, info
    if unrestorable:
        info["outcome"] = "partial"
        out("PARTIAL: restored %s, but %s could not be restored from this point." % (differ, unrestorable))
        return EXIT_API, info
    info["outcome"] = "restored_verified"
    out("  restored and verified. writes=1")
    return EXIT_OK, info


# --------------------------------------------------------------- dry-run logs
@contextlib.contextmanager
def scratch_logs(name: str) -> Iterator[None]:
    """Redirect Job_Log and shadow log to .tmp/scratch/<name>/ for a dry-run,
    and undo it on the way out (main() is also called as a library)."""
    from shared.job_log import use_scratch_logs

    keys = ("JOB_LOG_PATH", "SHADOW_LOG_PATH", "JOB_LOG_READ_PATH")
    saved = dict((k, os.environ.get(k)) for k in keys)
    use_scratch_logs(name)
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def campaign_id_for(key: str) -> Optional[str]:
    return ((settings.CAMPAIGNS or {}).get(key) or {}).get("id")


def campaign_key_for(campaign_id: str) -> Optional[str]:
    for key, meta in (settings.CAMPAIGNS or {}).items():
        if (meta or {}).get("id") == campaign_id:
            return key
    return None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
