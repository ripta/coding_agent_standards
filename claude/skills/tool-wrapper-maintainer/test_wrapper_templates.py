"""Tests for the wrapper templates in SKILL.md. Run: uv run --with pytest pytest <this directory>"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SKILL = Path(__file__).with_name("SKILL.md")

# Stands in for `go install`. It writes a fake tool into $GOBIN and logs each call.
GO_STUB = """#!/bin/sh
echo "go $*" >> "$GO_LOG"
printf '#!/bin/sh\\necho fake-tool "$@"\\n' > "$GOBIN/toolname"
chmod +x "$GOBIN/toolname"
"""

TOOL = b'#!/bin/sh\necho fake-tool "$@"\n'


def _template(name: str) -> str:
    text = SKILL.read_text()
    match = re.search(rf"^### {name}\b.*?^```bash\n(.*?)^```", text, re.DOTALL | re.MULTILINE)
    assert match, f"no bash template under '### {name}' in SKILL.md"
    return match.group(1)


def _gloobin_wrapper(tmp_path: Path) -> str:
    """The GLOOBIN template, pointed at a local file instead of the placeholder URL."""
    download = tmp_path / "download" / "toolname-1.0.0"
    download.parent.mkdir()
    download.write_bytes(TOOL)
    digest = hashlib.sha256(TOOL).hexdigest()

    wrapper = _template("GLOOBIN")
    wrapper = re.sub(r'^GLOOBIN_URL=.*$', f'GLOOBIN_URL="file://{download}"', wrapper, flags=re.MULTILINE)
    wrapper = re.sub(r'^GLOOBIN_SHA256=.*$', f'GLOOBIN_SHA256="{digest}"', wrapper, flags=re.MULTILINE)
    return wrapper


def _project(tmp_path: Path, wrapper: str) -> Path:
    """A project root with bin/toolname and two app directories that call it."""
    project = tmp_path / "project"
    (project / "bin").mkdir(parents=True)
    (project / "apps" / "x").mkdir(parents=True)
    (project / "apps" / "y").mkdir(parents=True)

    script = project / "bin" / "toolname"
    script.write_text(wrapper)
    script.chmod(0o755)
    return project


def _run_from(project: Path, app: str, env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(project / "bin" / "toolname"), "--version"],
        cwd=project / "apps" / app,
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("kind", ["GOBIN", "GLOOBIN"])
def test_a_wrapper_caches_next_to_bin_whatever_directory_calls_it(tmp_path, kind):
    """Catches a cache resolved against the caller's directory.

    A Makefile in apps/x or apps/y would then download the tool again into its own .cache.
    """
    if kind == "GLOOBIN" and not (shutil.which("curl") and shutil.which("shasum")):
        pytest.skip("the GLOOBIN template needs curl and shasum")

    stub_bin = tmp_path / "stub-bin"
    stub_bin.mkdir()
    go = stub_bin / "go"
    go.write_text(GO_STUB)
    go.chmod(0o755)

    go_log = tmp_path / "go.log"
    env = {**os.environ, "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}", "GO_LOG": str(go_log)}

    wrapper = _template("GOBIN") if kind == "GOBIN" else _gloobin_wrapper(tmp_path)
    project = _project(tmp_path, wrapper)

    first = _run_from(project, "x", env)
    second = _run_from(project, "y", env)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert "fake-tool --version" in first.stdout

    assert not (project / "apps" / "x" / ".cache").exists()
    assert not (project / "apps" / "y" / ".cache").exists()
    assert sorted(path.name for path in (project / ".cache").iterdir()) == [
        "toolname-1.0.0" if kind == "GLOOBIN" else "toolname-v1.0.0"
    ]

    if kind == "GOBIN":
        assert go_log.read_text().count("go install") == 1
    else:
        assert "Downloading" in first.stderr
        assert "Downloading" not in second.stderr
