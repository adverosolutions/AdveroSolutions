"""GATE_RULES_VERSION is bumped by hand; this pin catches a forgotten bump.

template_gate.GATE_RULES_VERSION feeds cadence._d1_gate_fingerprint. A rule
change without the bump fails safe (a held D1 is simply not re-checked after
the deploy), but it is easy to forget. The test hashes template_gate.py's
source with the `GATE_RULES_VERSION = N` line removed and compares it with
the digest recorded for the current version. Any edit to the file (a rule,
a comment, whitespace) moves the digest: if a gate rule changed, bump the
version; then record the new digest below.
"""
import hashlib
import re
from pathlib import Path

from services.reply_engine import template_gate

GATE_SOURCE = Path(template_gate.__file__).resolve()

# {GATE_RULES_VERSION: sha256 of template_gate.py without its version line}
RECORDED = {
    1: "20c52877dee5a894ee85c765641f4488365d1d30dd3e5159ab9dfa82d342080f",
    # 2: the researched day 2 line (E2): cadence.d2.research_rules and the
    # verdict-time research_rules.validate check
    2: "417fa18454bb552e3c8dfb579f4e174d7c00d7fae88dc13110d5b83578ec101f",
}

_VERSION_LINE = re.compile(r"^GATE_RULES_VERSION = \d+\s*$")


def _digest():
    text = GATE_SOURCE.read_bytes().decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    kept = [line for line in lines if not _VERSION_LINE.match(line)]
    assert len(lines) - len(kept) == 1, "expected exactly one `GATE_RULES_VERSION = N` line"
    return hashlib.sha256("\n".join(kept).encode("utf-8")).hexdigest()


def test_gate_rules_version_is_pinned_to_the_gate_source():
    version = template_gate.GATE_RULES_VERSION
    digest = _digest()
    assert {version: RECORDED.get(version)} == {version: digest}, (
        "template_gate.py changed (sha256 without the version line is now %s). If a gate rule "
        "changed, bump GATE_RULES_VERSION; then record the new digest here as %d: %r."
        % (digest, version, digest))
