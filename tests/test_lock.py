"""requirements.lock must be the export of uv.lock, so pip users get the versions uv users get."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EXPORT = ["uv", "export", "--locked", "--no-dev", "--no-emit-project", "--format", "requirements-txt", "-o", "requirements.lock"]


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")
def test_requirements_lock_is_uv_lock_exported():
    result = subprocess.run([*EXPORT[:-2], "--quiet"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    exported = [line for line in result.stdout.splitlines() if not line.startswith("#")]
    committed = [line for line in (ROOT / "requirements.lock").read_text().splitlines() if not line.startswith("#")]
    assert exported == committed, f"requirements.lock is stale; regenerate it with: {' '.join(EXPORT)}"
