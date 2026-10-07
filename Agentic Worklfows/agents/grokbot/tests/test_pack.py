"""Checks on the onboarding pack files. Offline, reads local files only."""

import importlib.util
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
ONBOARDING = os.path.join(ROOT, "onboarding")

_spec = importlib.util.spec_from_file_location("build_pack", os.path.join(ROOT, "build_pack.py"))
build_pack = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_pack)

SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}"),
    re.compile(r"\bpit-[0-9a-f]{8}-"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{24,}"),
    re.compile(r"(api[_-]?key|token|secret|password)\s*[:=]\s*['\"][^'\"\s]{12,}['\"]", re.I),
]


def read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def pack_files():
    for base, _dirs, files in os.walk(ONBOARDING):
        for name in files:
            yield os.path.join(base, name)


class Pack(unittest.TestCase):
    def test_every_file_exists(self):
        for name in build_pack.DOCS + ["ask_opus.py", "GROK_ONBOARDING_PACK.md"]:
            self.assertTrue(os.path.isfile(os.path.join(ONBOARDING, name)), name)
        for name in build_pack.SKILLS:
            self.assertTrue(os.path.isfile(os.path.join(ONBOARDING, "skills", name + ".md")), name)
        for name in build_pack.LINKEDIN_FILES:
            self.assertTrue(os.path.isfile(os.path.join(ONBOARDING, "linkedin", name)), name)

    def test_script_inline_in_04_matches_the_file(self):
        doc = read(os.path.join(ONBOARDING, "04_ask_opus.md"))
        script = read(os.path.join(ONBOARDING, "ask_opus.py"))
        self.assertEqual(doc, build_pack.inline_script(doc, script))
        self.assertIn(script.rstrip(), doc)

    def test_combined_pack_is_current(self):
        self.assertEqual(read(os.path.join(ONBOARDING, "GROK_ONBOARDING_PACK.md")),
                         build_pack.combine())

    def test_skills_have_no_maintainer_sources(self):
        for name in build_pack.SKILLS:
            text = read(os.path.join(ONBOARDING, "skills", name + ".md"))
            self.assertNotIn("Sources (for maintainers)", text, name)
            self.assertTrue(text.startswith("---\nname: " + name + "\n"), name)

    def test_skill_copies_match_their_sources(self):
        skills_dir = os.path.expanduser("~/.claude/skills")
        checked = 0
        for name in build_pack.SKILLS:
            source = os.path.join(skills_dir, name, "SKILL.md")
            if not os.path.isfile(source):
                continue
            with self.subTest(skill=name):
                self.assertEqual(read(os.path.join(ONBOARDING, "skills", name + ".md")),
                                 build_pack.strip_sources(build_pack.read(source)),
                                 "%s drifted from its skill; run build_pack.py" % name)
            checked += 1
        if not checked:
            self.skipTest("no skill sources on this machine")

    def test_linkedin_copies_match_their_sources(self):
        for name in build_pack.LINKEDIN_FILES:
            with self.subTest(file=name):
                self.assertEqual(read(os.path.join(ONBOARDING, "linkedin", name)),
                                 read(os.path.join(build_pack.LINKEDIN_SRC, name)),
                                 "linkedin/%s drifted from its source; run build_pack.py" % name)

    def test_strip_sources_keeps_later_sections(self):
        text = "# A\n\n## Keep\nx\n\n## Sources (for maintainers)\n- `a/b.py`\n\n## After\ny\n"
        self.assertEqual(build_pack.strip_sources(text), "# A\n\n## Keep\nx\n\n## After\ny\n")

    def test_no_secrets_anywhere_in_the_pack(self):
        for path in pack_files():
            text = read(path)
            for pattern in SECRET_PATTERNS:
                self.assertIsNone(pattern.search(text), "%s matches %s" % (path, pattern.pattern))

    def test_our_docs_have_no_dashes_or_exclamation_style(self):
        for name in build_pack.DOCS:
            text = read(os.path.join(ONBOARDING, name))
            self.assertNotIn("—", text, name)
            self.assertNotIn("–", text, name)

    def test_pack_names_the_copy_doc_and_model(self):
        pack = read(os.path.join(ONBOARDING, "GROK_ONBOARDING_PACK.md"))
        self.assertIn("1bK3bkYfxYkhY0vFtHhB4RG6lMkKQrHvp6Qyasp8Pbt4", pack)
        self.assertIn("170b09dd897430a9", pack)
        self.assertIn("claude-opus-5-5", pack)


if __name__ == "__main__":
    unittest.main()
