import runpy
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


SCRIPT = Path(__file__).with_name("link-current.py")
LINK_CURRENT = runpy.run_path(str(SCRIPT))["link_current"]


class LinkCurrentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="codex home ")
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.root = self.home / "plugins" / "cache" / "market" / "standards" / "1.0.0"
        self.root.mkdir(parents=True)
        (self.root / "baseline.md").write_text("baseline")
        self.link = self.home / "coding-standards-current"

    def test_create_repeat_upgrade_and_repair_dangling_link(self):
        LINK_CURRENT(self.root, self.home)
        LINK_CURRENT(self.root, self.home)
        self.assertEqual(self.link.resolve(), self.root.resolve())
        upgraded = self.root.with_name("2.0.0")
        upgraded.mkdir()
        (upgraded / "baseline.md").write_text("new baseline")
        LINK_CURRENT(upgraded, self.home)
        self.assertEqual((self.link / "baseline.md").read_text(), "new baseline")
        self.link.unlink()
        self.link.symlink_to(self.home / "missing")
        LINK_CURRENT(upgraded, self.home)
        self.assertEqual(self.link.resolve(), upgraded.resolve())

    def test_preserve_existing_file_and_directory(self):
        self.link.write_text("user content")
        with self.assertRaisesRegex(ValueError, "not a symlink"):
            LINK_CURRENT(self.root, self.home)
        self.assertEqual(self.link.read_text(), "user content")
        self.link.unlink()
        self.link.mkdir()
        with self.assertRaisesRegex(ValueError, "not a symlink"):
            LINK_CURRENT(self.root, self.home)
        self.assertTrue(self.link.is_dir())

    def test_reject_working_tree_and_missing_baseline(self):
        with self.assertRaisesRegex(ValueError, "working tree"):
            LINK_CURRENT(self.home, self.home)
        (self.root / "baseline.md").unlink()
        with self.assertRaisesRegex(ValueError, "no baseline"):
            LINK_CURRENT(self.root, self.home)
        self.assertFalse(self.link.is_symlink())

    def test_concurrent_sessions_leave_valid_link_and_no_temporary_files(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: LINK_CURRENT(self.root, self.home), range(32)))
        self.assertEqual(self.link.resolve(), self.root.resolve())
        self.assertEqual(list(self.home.glob(".coding-standards-*")), [])


if __name__ == "__main__":
    unittest.main()
