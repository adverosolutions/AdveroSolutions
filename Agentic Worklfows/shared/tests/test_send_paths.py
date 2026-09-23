"""Every reply send path in the repo must name its recipient.

`shared.instantly.reply_to_email` raises without `to=`, so a forgotten
recipient can no longer reach Instantly. This file is the second half of that
guard: it fails at review time, not at send time, if a new caller is written
without one. Instantly validates `to` against the thread before sending, which
is the only server-side protection against a stale or crossed `reply_to_uuid`
delivering Lorenzo's answer to a different lead.
"""
import io
import os

import pytest

from shared.paths import BASE_DIR

CALL = "reply_to_email("
SKIP_DIRS = {".git", ".tmp", "__pycache__", "node_modules", ".venv", "venv", "Coding", "Trash"}
# The library itself defines the function; its own tests exercise the refusal.
SKIP_FILES = {
    os.path.join("shared", "instantly.py"),
    os.path.join("shared", "tests", "test_instantly.py"),
    os.path.join("shared", "tests", "test_send_paths.py"),
}


def _python_files():
    for root, dirs, files in os.walk(str(BASE_DIR)):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for name in files:
            if name.endswith(".py"):
                full = os.path.join(root, name)
                rel = os.path.relpath(full, str(BASE_DIR))
                if rel not in SKIP_FILES:
                    yield rel, full


def _call_texts(source):
    """Each reply_to_email(...) call site, from the open paren to its match."""
    out = []
    idx = source.find(CALL)
    while idx != -1:
        i = idx + len(CALL) - 1
        depth = 0
        for j in range(i, len(source)):
            if source[j] == "(":
                depth += 1
            elif source[j] == ")":
                depth -= 1
                if depth == 0:
                    out.append(source[idx:j + 1])
                    break
        idx = source.find(CALL, idx + 1)
    return out


def _call_sites():
    sites = []
    for rel, full in _python_files():
        source = io.open(full, encoding="utf-8").read()
        if CALL not in source:
            continue
        for text in _call_texts(source):
            line = source[:source.index(text)].count("\n") + 1
            sites.append((rel, line, text))
    return sites


def test_the_repo_still_has_send_paths_to_check():
    """Guards the guard: a rename that hides every call site must not make this
    file silently vacuous."""
    assert _call_sites(), "no reply_to_email call sites found - has the API been renamed?"


@pytest.mark.parametrize("rel,line,text", [pytest.param(*s, id="%s:%s" % (s[0], s[1])) for s in _call_sites()])
def test_every_send_path_names_its_recipient(rel, line, text):
    assert "to=" in text or "skip_validation=True" in text, (
        "%s:%d calls reply_to_email without to=<lead email>. Instantly then performs no "
        "recipient-vs-thread check, so a stale or crossed reply_to_uuid delivers this reply to "
        "whoever owns that thread:\n%s" % (rel, line, text)
    )
