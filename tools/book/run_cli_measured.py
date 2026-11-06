#!/usr/bin/env python
"""The real command line in its own process, so peak memory is that run's alone. Prints JSON.

usage: run_cli_measured.py IMAGE OUT.svg [CLI OPTIONS...]. Unlike run_engine.py this includes the CLI's own checks.
"""
import contextlib
import io
import json
import os
import resource
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from unpixel.cli import main  # noqa: E402

image, out, *options = sys.argv[1:]
captured = io.StringIO()
t0 = time.perf_counter()
with contextlib.redirect_stdout(captured):
    code = main([image, "-o", out, "--force", "--no-report", "--json", *options])
seconds = time.perf_counter() - t0
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(json.dumps({
    "code": code,
    "seconds": round(seconds, 2),
    "peak_rss_mb": round(rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024),
    "svg_kb": round(os.path.getsize(out) / 1024, 1),
    "warnings": json.loads(captured.getvalue()).get("warnings", []),
}))
