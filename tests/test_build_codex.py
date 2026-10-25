import json
import runpy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


BUILD = Path(__file__).resolve().parents[1] / "bin" / "build-codex"


class BaselineBuildTests(unittest.TestCase):
    def setUp(self):
        self.builder = runpy.run_path(str(BUILD))
        self.namespace = self.builder["main"].__globals__

    def test_bundle_survives_relocation_and_contains_every_baseline_import(self):
        with tempfile.TemporaryDirectory(prefix="codex baseline ") as temporary:
            output = Path(temporary) / "bundle"
            with patch.dict(self.namespace, OUTPUT=output), patch("sys.argv", [str(BUILD)]):
                self.builder["main"]()
            moved = output.rename(Path(temporary) / "relocated bundle")
            baseline = (moved / "baseline.md").read_text()
            paths = self.builder["baseline_paths"]()
            positions = []
            for relative in paths:
                positions.append(baseline.index(f"]({relative})"))
                contents = (moved / relative).read_text()
                self.assertNotIn("AskUserQuestion", contents)
                self.assertNotIn("ListAgents", contents)
            self.assertEqual(positions, sorted(positions))
            self.assertNotIn(str(output), baseline)
            self.assertTrue((moved / "scripts" / "proposals.py").is_file())

    def test_unknown_import_preserves_previous_build(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "profiles").mkdir()
            (root / "profiles" / "baseline.md").write_text("@unexpected/source.md\n")
            output = root / "bundle"
            output.mkdir()
            marker = output / "existing"
            marker.write_text("previous build")
            with patch.dict(self.namespace, REPO=root, OUTPUT=output):
                with patch("sys.argv", [str(BUILD)]), self.assertRaisesRegex(ValueError, "unsupported"):
                    self.builder["main"]()
            self.assertEqual(marker.read_text(), "previous build")

    def test_version_covers_documentation_and_metadata_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "bundle"
            with patch.dict(self.namespace, OUTPUT=output), patch("sys.argv", [str(BUILD)]):
                self.builder["main"]()
                manifest = output / "plugin.json"
                original = json.loads(manifest.read_text())["version"]
                self.builder["version_plugin"]()
                self.assertEqual(json.loads(manifest.read_text())["version"], original)
                readme = output / "README.md"
                readme.write_text(readme.read_text() + "\nUpdated installation instructions.\n")
                self.builder["version_plugin"]()
                updated = json.loads(manifest.read_text())["version"]
                self.assertNotEqual(updated, original)
                metadata = json.loads(manifest.read_text())
                metadata["description"] = "Updated package description"
                manifest.write_text(json.dumps(metadata, indent=2) + "\n")
                self.builder["version_plugin"]()
                self.assertNotEqual(json.loads(manifest.read_text())["version"], updated)
                compatibility = output / ".codex-plugin" / "plugin.json"
                self.assertEqual(json.loads(manifest.read_text())["version"],
                                 json.loads(compatibility.read_text())["version"])


if __name__ == "__main__":
    unittest.main()
