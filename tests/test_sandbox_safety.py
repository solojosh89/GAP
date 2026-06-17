"""Proves the sandbox CONTAINS misbehaving code: an infinite loop is killed by
the time limit instead of hanging the host, and a crash is captured cleanly.

    python tests/test_sandbox_safety.py
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gap.sandbox import run_script  # noqa: E402


def test_infinite_loop_is_killed():
    workdir = tempfile.mkdtemp(prefix="gap_safety_")
    try:
        with open(os.path.join(workdir, "runaway.py"), "w", encoding="utf-8") as f:
            f.write("while True:\n    pass\n")
        r = run_script("runaway.py", workdir, timeout_s=2.0)
        assert r.timed_out, "expected the runaway script to be killed by the timeout"
        assert r.duration_s < 5.0, "kill took too long"
        print(f"OK: runaway script killed after {r.duration_s:.2f}s (host not hung)")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_crash_is_captured():
    workdir = tempfile.mkdtemp(prefix="gap_safety_")
    try:
        with open(os.path.join(workdir, "boom.py"), "w", encoding="utf-8") as f:
            f.write("raise RuntimeError('boom')\n")
        r = run_script("boom.py", workdir, timeout_s=5.0)
        assert not r.timed_out and r.exit_code != 0, "expected a captured non-zero exit"
        assert "RuntimeError" in r.stderr
        print("OK: crashing script captured cleanly (exit != 0, stderr has the error)")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    test_infinite_loop_is_killed()
    test_crash_is_captured()
    print("\nAll sandbox safety checks passed.")
