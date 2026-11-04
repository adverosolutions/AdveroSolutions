"""Offline behavior checks for preserving local instruction records."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("sync_config", Path(__file__).resolve().parents[1] / "sync_config.py")
SYNC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SYNC)


class SyncConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.home = base / "home"
        self.repo = base / "repo"
        self.source = self.home / ".claude/skills/example/SKILL.md"
        self.source.parent.mkdir(parents=True)
        self.source.write_text("installed")
        self.dest = self.repo / "ClaudeConfig/skills/example/SKILL.md"
        self.dest.parent.mkdir(parents=True)
        self.dest.write_text("repository")

    def test_default_preserves_conflicts_and_repository_only_files(self):
        extra = self.repo / "ClaudeConfig/skills/retained/SKILL.md"
        extra.parent.mkdir(parents=True)
        extra.write_text("keep")
        SYNC.synchronize(self.home, self.repo)
        self.assertEqual(self.dest.read_text(), "repository")
        self.assertEqual(extra.read_text(), "keep")

    def test_imports_additions_and_excludes_credential_record(self):
        new = self.home / ".claude/skills/added/SKILL.md"
        new.parent.mkdir(parents=True)
        new.write_text("new")
        secret = self.home / ".claude/projects/-Users-lorenzovillarreal-Desktop-AdveroSolutions/memory/millionverifier-keys.md"
        secret.parent.mkdir(parents=True)
        secret.write_text("excluded")
        SYNC.synchronize(self.home, self.repo, import_new=True)
        self.assertEqual((self.repo / "ClaudeConfig/skills/added/SKILL.md").read_text(), "new")
        self.assertEqual(self.dest.read_text(), "repository")
        self.assertFalse((self.repo / "ClaudeConfig/memory/millionverifier-keys.md").exists())

    def test_explicit_replacement_backs_up_previous_contents(self):
        SYNC.synchronize(self.home, self.repo, replacements=["ClaudeConfig/skills/example/SKILL.md"])
        self.assertEqual(self.dest.read_text(), "installed")
        backups = list((self.repo / ".tmp/config-import-backups").rglob("SKILL.md"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), "repository")

    def test_invalid_replacement_fails_before_any_import(self):
        new = self.home / ".claude/skills/added/SKILL.md"
        new.parent.mkdir(parents=True)
        new.write_text("new")
        with self.assertRaises(ValueError):
            SYNC.synchronize(self.home, self.repo, import_new=True, replacements=["unknown/path"])
        self.assertFalse((self.repo / "ClaudeConfig/skills/added/SKILL.md").exists())
        self.assertEqual(self.dest.read_text(), "repository")


if __name__ == "__main__":
    unittest.main()
