#!/usr/bin/env python3
"""Build the Grok Bot onboarding pack.

What it does:
1. Copies each skill's SKILL.md from the skills folder into onboarding/skills/<name>.md,
   unchanged except that the "Sources (for maintainers)" section (local file paths)
   is removed.
2. Puts the current onboarding/ask_opus.py inside 04_ask_opus.md, between the
   BEGIN/END markers.
3. Writes onboarding/GROK_ONBOARDING_PACK.md: files 00 to 07, then the skills,
   in one file for a single upload.

Usage (from Agentic Worklfows/):
    python3 agents/grokbot/build_pack.py                  # skills from ~/.claude/skills
    python3 agents/grokbot/build_pack.py --skills-dir DIR
    python3 agents/grokbot/build_pack.py --no-skills      # rebuild 04 and the pack only
"""

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ONBOARDING = os.path.join(HERE, "onboarding")
SKILLS_OUT = os.path.join(ONBOARDING, "skills")
PACK = os.path.join(ONBOARDING, "GROK_ONBOARDING_PACK.md")
SCRIPT = os.path.join(ONBOARDING, "ask_opus.py")
ASK_OPUS_DOC = os.path.join(ONBOARDING, "04_ask_opus.md")

DOCS = ["00_START_HERE.md", "01_business_context.md", "02_operating_model.md",
        "03_team.md", "04_ask_opus.md", "05_lead_state_ghl.md",
        "06_systems_and_access.md", "07_reports_and_scorecard.md"]
SKILLS = ["grok-operator", "cold-email-replies", "quiet-lead-followup", "booked-calls",
          "nurture-90-day", "upwork-followups", "lorenzo-voice", "claudeisms",
          "daily-reports-and-metrics", "sales-call", "cold-campaigns",
          "deliverability-and-inboxes", "client-fulfillment"]

BEGIN = "<!-- BEGIN ask_opus.py -->"
END = "<!-- END ask_opus.py -->"
SOURCES_RE = re.compile(r"^## Sources \(for maintainers\)\s*$")


def strip_sources(text):
    """Remove the '## Sources (for maintainers)' section up to the next '## ' heading."""
    out = []
    skipping = False
    for line in text.splitlines():
        if SOURCES_RE.match(line):
            skipping = True
            continue
        if skipping and line.startswith("## "):
            skipping = False
        if not skipping:
            out.append(line)
    return "\n".join(out).rstrip() + "\n"


def read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def write(path, text):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def copy_skills(skills_dir):
    os.makedirs(SKILLS_OUT, exist_ok=True)
    for name in SKILLS:
        source = os.path.join(skills_dir, name, "SKILL.md")
        write(os.path.join(SKILLS_OUT, name + ".md"), strip_sources(read(source)))


def inline_script(doc_text, script_text):
    start = doc_text.index(BEGIN) + len(BEGIN)
    end = doc_text.index(END)
    block = "\n```python\n" + script_text.rstrip() + "\n```\n"
    return doc_text[:start] + block + doc_text[end:]


def combine():
    parts = [
        "# Grok onboarding pack: Chief of Staff, AdveroSolutions\n",
        "One file for a single upload. Files 00 to 07 first, then the skills. "
        "Files 00 to 07 win over the skills where they differ (see 00, section 4).\n",
        "Contents:\n" + "\n".join("- " + name for name in DOCS)
        + "\n" + "\n".join("- skills/" + name + ".md" for name in SKILLS) + "\n",
    ]
    for name in DOCS:
        parts.append("\n---\n\n<!-- FILE: " + name + " -->\n\n" + read(os.path.join(ONBOARDING, name)).rstrip() + "\n")
    for name in SKILLS:
        parts.append("\n---\n\n<!-- FILE: skills/" + name + ".md -->\n\n"
                     + read(os.path.join(SKILLS_OUT, name + ".md")).rstrip() + "\n")
    return "\n".join(parts)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--skills-dir", default=os.path.expanduser("~/.claude/skills"))
    parser.add_argument("--no-skills", action="store_true")
    args = parser.parse_args(argv)
    if not args.no_skills:
        copy_skills(args.skills_dir)
    write(ASK_OPUS_DOC, inline_script(read(ASK_OPUS_DOC), read(SCRIPT)))
    write(PACK, combine())
    print("wrote %s" % PACK)
    return 0


if __name__ == "__main__":
    sys.exit(main())
