import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="codex setup ")
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name).resolve() / "home"
        self.root = self.home / "plugins" / "cache" / "market" / "standards" / "1.0.0"
        scripts = self.root / "scripts"
        scripts.mkdir(parents=True)
        shutil.copy2(Path(__file__).with_name("setup.py"), scripts / "setup.py")
        hooks = self.root / "hooks"
        hooks.mkdir()
        for name in ("link-current.py", "check-setup.py"):
            shutil.copy2(Path(__file__).parent.parent / "hooks" / name, hooks / name)
        (self.root / "baseline.md").write_text("baseline")
        self.project = Path(self.temporary.name) / "project"
        self.project.mkdir()
        (self.project / ".git").mkdir()
        self.instructions = self.home / "AGENTS.md"
        self.link = self.home / "coding-standards-current"

    def run_setup(self, *args):
        script = self.root / "scripts" / "setup.py"
        if args == ("--startup",):
            script = self.root / "hooks" / "check-setup.py"
            args = ()
        return subprocess.run(
            [sys.executable, str(script), *args],
            env=dict(os.environ, CODEX_HOME=str(self.home)), cwd=self.project,
            capture_output=True, text=True,
        )

    def test_check_reports_missing_setup_without_writing(self):
        result = self.run_setup("--check")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("does not point", result.stdout)
        self.assertIn("do not reference", result.stdout)
        self.assertFalse(self.link.is_symlink())
        self.assertFalse(self.instructions.exists())

    def test_setup_preserves_instructions_and_is_repeatable(self):
        self.instructions.write_text("Existing instructions.\n")
        result = self.run_setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        first = self.instructions.read_text()
        self.assertTrue(first.startswith("Existing instructions.\n"))
        self.assertEqual(self.run_setup().returncode, 0)
        self.assertEqual(first, self.instructions.read_text())
        self.assertEqual(self.run_setup("--check").returncode, 0)

    def test_startup_warns_without_writing_instructions(self):
        result = self.run_setup("--startup")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.link.is_symlink())
        self.assertFalse(self.instructions.exists())
        self.assertIn("Run: python3", result.stdout)
        self.assertIn("do not reference", result.stdout)

    def test_project_adoption_is_accepted_and_startup_is_quiet(self):
        (self.project / "AGENTS.md").write_text(f"Read {self.link}/baseline.md")
        result = self.run_setup("--startup")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertFalse(self.instructions.exists())

    def test_override_hiding_global_baseline_is_reported(self):
        self.assertEqual(self.run_setup().returncode, 0)
        (self.home / "AGENTS.override.md").write_text("Other instructions")
        result = self.run_setup("--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("do not reference", result.stdout)

    def test_setup_updates_active_global_override(self):
        self.instructions.write_text("Global instructions.\n")
        override = self.home / "AGENTS.override.md"
        override.write_text("Active override instructions.\n")
        result = self.run_setup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.instructions.read_text(), "Global instructions.\n")
        self.assertTrue(override.read_text().startswith("Active override instructions.\n"))
        self.assertIn(str(self.link / "baseline.md"), override.read_text())
        self.assertEqual(self.run_setup("--check").returncode, 0)

    def test_instructions_outside_repository_do_not_satisfy_check(self):
        (self.project.parent / "AGENTS.md").write_text(f"Read {self.link}/baseline.md")
        result = self.run_setup("--startup")
        self.assertIn("do not reference", result.stdout)


if __name__ == "__main__":
    unittest.main()
