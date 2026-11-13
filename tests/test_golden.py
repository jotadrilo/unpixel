"""Golden outputs: the SVG of every battery case must match tests/golden.json byte for byte.

A failure means the engine's output changed, from the code or from a dependency. That needs the owner to
validate the new output on the battery before tools/golden.py --update and the "Record goldens" workflow
record it. See "Golden outputs" in the README.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import golden  # noqa: E402

pytestmark = pytest.mark.golden


def test_battery_matches_goldens(tmp_path):
    recorded = golden.goldens_for_platform()
    if recorded is None:
        pytest.skip(f"no goldens recorded for {golden.platform_key()}")
    python = golden.environment()["python"]
    if recorded["environment"]["python"] != python:
        pytest.skip(f"goldens are for Python {recorded['environment']['python']}, whose locked libraries differ from {python}'s")
    actual = golden.run_all(tmp_path)
    diff = golden.compare(recorded, actual)
    note = golden.environment_note(recorded)
    assert not diff, "\n".join(
        [f"{len(diff)} of {len(actual)} outputs changed on {golden.platform_key()}:", *diff]
        + ([note] if note else [])
        + ["Output changes need the owner's validation on the battery before the goldens are refreshed."]
    )
