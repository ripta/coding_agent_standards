import json
import os
import re
import runpy
import shutil
import subprocess
import sys
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

    def test_queue_dependencies_resolve_after_relocation(self):
        with tempfile.TemporaryDirectory(prefix="codex queue ") as temporary:
            output = Path(temporary) / "bundle"
            with patch.dict(self.namespace, OUTPUT=output), patch("sys.argv", [str(BUILD)]):
                self.builder["main"]()
            moved = output.rename(Path(temporary) / "relocated bundle")
            documents = [moved / "skills" / name / "SKILL.md" for name in
                         ("work-queue", "work-on", "schedule-proposal", "session-report")]
            documents += sorted((moved / "references" / "agents").glob("*.md"))
            self.assertEqual(len(documents), 7)
            for document in documents:
                with self.subTest(document=document.relative_to(moved)):
                    contents = document.read_text()
                    self.assertIsNone(self.builder["UNSUPPORTED"].search(contents))
                    for relative in re.findall(r"(?:\./)?\.\./\.\./[\w./-]+", contents):
                        target = (document.parent / relative).resolve()
                        self.assertTrue(target.is_relative_to(moved.resolve()))
                        self.assertTrue(target.exists(), f"{document}: {relative}")
            self.assertTrue((moved / "scripts" / "detect_era.py").is_file())
            self.assertTrue((moved / "knowledge" / "wiki.md").is_file())
            self.assertFalse((moved / "agents").exists())
            self.assertFalse((moved / "scripts" / "agent_liveness.py").exists())
            for name in ("work-queue", "work-on"):
                policy = moved / "skills" / name / "agents" / "openai.yaml"
                self.assertIn("allow_implicit_invocation: false", policy.read_text())

    def test_changed_or_duplicated_adaptation_preserves_previous_build(self):
        source = self.namespace["SOURCE"]
        original = (source / "commands" / "work-queue.md").read_text()
        for changed in (
            original.replace("Call ExitPlanMode. That approval is the only gate in the run.",
                             "Request approval through a different mechanism."),
            original + "\nCall ExitPlanMode. That approval is the only gate in the run.\n",
        ):
            with self.subTest(changed=changed[-80:]), tempfile.TemporaryDirectory() as temporary:
                copied = Path(temporary) / "claude"
                shutil.copytree(source, copied)
                (copied / "commands" / "work-queue.md").write_text(changed)
                output = Path(temporary) / "bundle"
                output.mkdir()
                marker = output / "previous"
                marker.write_text("keep this build")
                with patch.dict(self.namespace, SOURCE=copied, OUTPUT=output):
                    with patch("sys.argv", [str(BUILD)]), self.assertRaisesRegex(ValueError, "stale"):
                        self.builder["main"]()
                self.assertEqual(marker.read_text(), "keep this build")

    def test_shared_workflow_updates_survive_conversion(self):
        source = self.namespace["SOURCE"] / "commands" / "work-queue.md"
        text = source.read_text().replace("## 6. Finish", "Preserve this new shared rule.\n\n## 6. Finish")
        converted = self.builder["convert_skill"](text, "work-queue", command=True)
        self.assertIn("Preserve this new shared rule.", converted)

    def test_untranslated_dependency_is_rejected_in_workflows_and_roles(self):
        for role in self.builder["ROLES"]:
            source = self.namespace["SOURCE"] / "agents" / f"{role}.md"
            with self.subTest(role=role), self.assertRaisesRegex(ValueError, "untranslated"):
                self.builder["convert_role"](source.read_text() + "\nUse SendMessage.\n", role)
        source = self.namespace["SOURCE"] / "commands" / "work-queue.md"
        with self.assertRaisesRegex(ValueError, "untranslated"):
            self.builder["convert_skill"](source.read_text() + "\nUse the Skill tool.\n",
                                          "work-queue", command=True)

    def test_bundled_scripts_read_external_specs_and_dependencies(self):
        with tempfile.TemporaryDirectory(prefix="codex layouts ") as temporary:
            root = Path(temporary)
            output = root / "bundle"
            with patch.dict(self.namespace, OUTPUT=output), patch("sys.argv", [str(BUILD)]):
                self.builder["main"]()
            moved = output.rename(root / "moved bundle")
            for layout, other_path in (
                ("monorepo", "apps/other/spec/proposals"),
                ("submodules", "modules/other/spec/proposals"),
                ("polyrepo", "other-checkout/docs/proposals"),
                ("hybrid", "apps/other/modules/library/docs/proposals"),
            ):
                with self.subTest(layout=layout):
                    workspace = root / layout
                    checkout = workspace / "code"
                    checkout.mkdir(parents=True)
                    specs = workspace / "external specs"
                    proposals = specs / "proposals"
                    proposals.mkdir(parents=True)
                    (checkout / "spec").symlink_to(specs, target_is_directory=True)
                    other = workspace / other_path
                    other.mkdir(parents=True)
                    for directory, prefix in ((proposals, "PROJ"), (other, "OTHER")):
                        (directory / f"{prefix}-001-feature.md").write_text(
                            f"# {prefix}-001: Feature\n\n**Status:** accepted\n\n"
                            "## Milestones\n\n### M1: Build\n\n**Status:** NOT STARTED\n\n"
                            "- The feature works.\n")
                        dependency = "OTHER-001 M1" if prefix == "PROJ" else "None"
                        (directory / "queue.md").write_text(
                            "# Queue\n\n| Milestones | Depends on | Note |\n|---|---|---|\n"
                            f"| {prefix}-001 M1 | {dependency} | |\n")
                    queue = proposals / "queue.md"
                    queue.write_text(queue.read_text() + "\n## Other proposals\n\n"
                                     + f"- OTHER: {os.path.relpath(other, proposals)}\n")
                    era = subprocess.run([
                        sys.executable, str(moved / "scripts" / "detect_era.py"),
                        "--specs-dir", str(checkout / "spec"),
                    ], cwd=checkout, capture_output=True, text=True, check=True)
                    self.assertEqual(json.loads(era.stdout)["era"], 3)
                    row = subprocess.run([
                        sys.executable, str(moved / "scripts" / "proposals.py"), "row", "PROJ-001",
                        "--proposals-dir", str(checkout / "spec" / "proposals"),
                    ], cwd=checkout, capture_output=True, text=True, check=True)
                    data = json.loads(row.stdout)
                    self.assertFalse(data["ready"])
                    self.assertEqual(data["dependencies"][0]["state"], "unmet")
                    self.assertEqual(data["dependencies"][0]["dependency"], "OTHER-001 M1")

    def test_version_covers_documentation_and_metadata_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "bundle"
            with patch.dict(self.namespace, OUTPUT=output), patch("sys.argv", [str(BUILD)]):
                self.builder["main"]()
                manifest = output / ".codex-plugin" / "plugin.json"
                self.assertFalse((output / "plugin.json").exists())
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

    @unittest.skipUnless(shutil.which("codex"), "Codex CLI is required for runtime discovery")
    def test_installed_startup_hook_is_discovered_by_codex(self):
        with tempfile.TemporaryDirectory(prefix="codex runtime ") as temporary:
            output = Path(temporary) / "bundle"
            with patch.dict(self.namespace, OUTPUT=output), patch("sys.argv", [str(BUILD)]):
                self.builder["main"]()
            home = Path(temporary) / "home"
            home.mkdir()
            env = dict(os.environ, CODEX_HOME=str(home))
            subprocess.run(["codex", "plugin", "marketplace", "add", str(output)],
                           env=env, capture_output=True, text=True, check=True, timeout=30)
            installation = subprocess.run([
                "codex", "plugin", "add", "coding-standards-portable@coding-standards-portable", "--json",
            ], env=env, capture_output=True, text=True, check=True, timeout=30)
            installed = Path(json.loads(installation.stdout)["installedPath"])
            verification = subprocess.run([
                sys.executable, str(installed / "scripts" / "verify_hooks.py"), "--json",
            ], env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(verification.returncode, 1, verification.stdout + verification.stderr)
            hooks = json.loads(verification.stdout)
            self.assertEqual(len(hooks), 1, verification.stderr)
            self.assertTrue(hooks[0]["enabled"])
            self.assertEqual(hooks[0]["trustStatus"], "untrusted")
            self.assertIn("review and trust", verification.stderr)


if __name__ == "__main__":
    unittest.main()
