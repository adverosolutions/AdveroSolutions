#!/usr/bin/env python3
"""Build the Grok Bot onboarding pack.

What it does:
1. Copies each skill's SKILL.md from the skills folder into onboarding/skills/<name>.md,
   unchanged except that the "Sources (for maintainers)" section (local file paths)
   is removed.
2. Copies the LinkedIn plan and profile kit from linkedin/ (in Agentic Worklfows/)
   into onboarding/linkedin/, unchanged.
3. Puts the current onboarding/ask_opus.py inside 04_ask_opus.md, between the
   BEGIN/END markers.
4. Writes onboarding/GROK_ONBOARDING_PACK.md: files 00 to 09, then the skills,
   then the LinkedIn files, in one file for a single upload.

Usage (from Agentic Worklfows/):
    python3 agents/grokbot/build_pack.py                  # skills from this repo: ClaudeConfig/skills
    python3 agents/grokbot/build_pack.py --skills-dir DIR
    python3 agents/grokbot/build_pack.py --no-skills      # skip the skills copy; LinkedIn files, 04 and the pack are rebuilt
"""

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_SKILLS = os.path.normpath(os.path.join(HERE, "..", "..", "..", "ClaudeConfig", "skills"))
ONBOARDING = os.path.join(HERE, "onboarding")
SKILLS_OUT = os.path.join(ONBOARDING, "skills")
PACK = os.path.join(ONBOARDING, "GROK_ONBOARDING_PACK.md")
SCRIPT = os.path.join(ONBOARDING, "ask_opus.py")
ASK_OPUS_DOC = os.path.join(ONBOARDING, "04_ask_opus.md")
LINKEDIN_SRC = os.path.normpath(os.path.join(HERE, "..", "..", "linkedin"))
LINKEDIN_OUT = os.path.join(ONBOARDING, "linkedin")

DOCS = ["00_START_HERE.md", "01_business_context.md", "02_operating_model.md",
        "03_team.md", "04_ask_opus.md", "05_lead_state_ghl.md",
        "06_systems_and_access.md", "07_reports_and_scorecard.md",
        "08_about_lorenzo.md", "09_company_and_process_overview.md"]
SKILLS = sorted(name for name in os.listdir(REPO_SKILLS)
                if os.path.isfile(os.path.join(REPO_SKILLS, name, "SKILL.md")))
CURRENT_PROCESS = os.path.join(REPO_SKILLS, "..", "PROCESS_AUTHORITY.md")
CURRENT_RULEBOOK = os.path.join(REPO_SKILLS, "..", "grok-source", "2026-11-04",
                              "first-export", "advero", "state", "org", "LEAN_ORG.md")

LINKEDIN_FILES = ["PLAN.md", "profile_kit.md"]

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


def prepare_skill(text):
    """Keep relative source links usable in this repository's onboarding folder."""
    return strip_sources(text).replace(
        "](../../", "](../../../../../ClaudeConfig/")


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
        write(os.path.join(SKILLS_OUT, name + ".md"), prepare_skill(read(source)))


def copy_linkedin():
    os.makedirs(LINKEDIN_OUT, exist_ok=True)
    for name in LINKEDIN_FILES:
        write(os.path.join(LINKEDIN_OUT, name), read(os.path.join(LINKEDIN_SRC, name)))


def inline_script(doc_text, script_text):
    start = doc_text.index(BEGIN) + len(BEGIN)
    end = doc_text.index(END)
    block = "\n```python\n" + script_text.rstrip() + "\n```\n"
    return doc_text[:start] + block + doc_text[end:]


def combine():
    parts = [
        "# Grok onboarding pack: Chief of Staff, AdveroSolutions\n",
        "One file for a single upload. Files 00 to 09 first, then the skills, then the LinkedIn files. "
        "CURRENT_PROCESS.md and the newest dated Lorenzo rulings in CURRENT_RULEBOOK.md "
        "take precedence over conflicting older files 00-09, skills and LinkedIn references. "
        "The older material remains historical evidence, not current live status.\n",
        "Contents:\n- CURRENT_PROCESS.md\n- CURRENT_RULEBOOK.md\n" + "\n".join("- " + name for name in DOCS)
        + "\n" + "\n".join("- skills/" + name + ".md" for name in SKILLS)
        + "\n" + "\n".join("- linkedin/" + name for name in LINKEDIN_FILES) + "\n",
    ]
    for name in ("CURRENT_PROCESS.md", "CURRENT_RULEBOOK.md"):
        parts.append("\n---\n\n<!-- FILE: " + name + " -->\n\n"
                     + read(os.path.join(ONBOARDING, name)).rstrip() + "\n")
    for name in DOCS:
        parts.append("\n---\n\n<!-- FILE: " + name + " -->\n\n" + read(os.path.join(ONBOARDING, name)).rstrip() + "\n")
    for name in SKILLS:
        parts.append("\n---\n\n<!-- FILE: skills/" + name + ".md -->\n\n"
                     + read(os.path.join(SKILLS_OUT, name + ".md")).rstrip() + "\n")
    for name in LINKEDIN_FILES:
        parts.append("\n---\n\n<!-- FILE: linkedin/" + name + " -->\n\n"
                     + read(os.path.join(LINKEDIN_OUT, name)).rstrip() + "\n")
    return "\n".join(parts)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--skills-dir", default=REPO_SKILLS)
    parser.add_argument("--no-skills", action="store_true")
    args = parser.parse_args(argv)
    if not args.no_skills:
        copy_skills(args.skills_dir)
    copy_linkedin()
    write(os.path.join(ONBOARDING, "CURRENT_PROCESS.md"), read(CURRENT_PROCESS))
    write(os.path.join(ONBOARDING, "CURRENT_RULEBOOK.md"), read(CURRENT_RULEBOOK))
    write(ASK_OPUS_DOC, inline_script(read(ASK_OPUS_DOC), read(SCRIPT)))
    write(PACK, combine())
    print("wrote %s" % PACK)
    return 0


if __name__ == "__main__":
    sys.exit(main())
