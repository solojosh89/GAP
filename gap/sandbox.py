"""GAP sandbox runner (SPIKE).

Runs a generated script in a throwaway working directory with a hard time limit,
captures its output, and reports what happened — without hanging the host if the
script loops forever or crashes.

HONEST LIMITS (flagged for hardening, see README):
  - Provides TIME/CRASH containment and a separate working directory.
  - Does NOT yet jail the filesystem or network. A script using absolute paths or
    sockets is NOT blocked here. Real isolation needs an OS-level sandbox
    (Docker / nsjail / Windows Job Objects) — that is a later job.
"""
from __future__ import annotations
import os
import subprocess
import sys
import time

from .contract import RunResult


def run_script(entry_name: str, workdir: str, timeout_s: float = 10.0) -> RunResult:
    """Run `python <entry_name>` inside workdir with a hard timeout."""
    start = time.monotonic()
    # Minimal environment — enough for Python to start, not the parent's full env.
    env = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),   # Python needs this on Windows
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    try:
        proc = subprocess.run(
            [sys.executable, entry_name],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env,
        )
        return RunResult(
            exit_code=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            timed_out=False,
            duration_s=time.monotonic() - start,
        )
    except subprocess.TimeoutExpired as e:
        out = e.stdout if isinstance(e.stdout, str) else ""
        err = e.stderr if isinstance(e.stderr, str) else ""
        return RunResult(
            exit_code=None,
            stdout=out,
            stderr=err + "\n[sandbox] killed: exceeded time limit",
            timed_out=True,
            duration_s=time.monotonic() - start,
        )
