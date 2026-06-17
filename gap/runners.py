"""Per-language proof/smoke runners.

Gate Test #2 surfaced the requirement: a real, runnable bug lived in a JavaScript
file, but the sandbox could only run Python. So a proof must be able to run in the
language it was written for. This registry maps a language to (a) the filename the
script is written to and (b) the argv prefix that executes it.

The sandbox stays language-agnostic: it writes `script` to `entry_name(language)`
and runs `argv(language) + [entry_name(language)]` with the same containment
(timeout, process-tree kill, memory cap) regardless of language.
"""
from __future__ import annotations
import sys

# language -> (entry filename, argv prefix). The argv prefix is completed with the
# entry filename by the caller. `python` uses the *current* interpreter so the
# sandbox runs the same Python that imported the code under test.
_RUNNERS = {
    "python": ("proof.py", [sys.executable]),
    "node":   ("proof.js", ["node"]),
}

# What the code-under-test is written to, per language, so the proof can import it.
_TARGETS = {
    "python": "target.py",
    "node":   "target.js",
}


def supported(language: str) -> bool:
    return language in _RUNNERS


def entry_name(language: str) -> str:
    return _RUNNERS[language][0]


def argv(language: str) -> list:
    return list(_RUNNERS[language][1])


def target_name(language: str) -> str:
    return _TARGETS[language]
