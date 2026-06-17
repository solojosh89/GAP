"""GAP engine contract — the fixed shapes the pipeline produces and consumes.

These are deliberately small. The real (LLM-backed) engine and the stub engine
both speak in these objects, so either can plug into the same pipeline.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

# Proof scripts communicate their verdict by printing one of these markers.
BUG_PRESENT = "GAP_PROOF:BUG_PRESENT"
BUG_ABSENT = "GAP_PROOF:BUG_ABSENT"


@dataclass
class Finding:
    """One problem the engine claims exists in the submitted code."""
    problem: str            # plain-language description
    rank: int               # 1 = most dangerous; the pipeline acts on the top one only
    confidence: str         # "high" | "medium" | "low"
    why_it_matters: str = ""


@dataclass
class Proof:
    """A self-contained script that DEMONSTRATES the finding by running."""
    script: str             # python source; prints BUG_PRESENT or BUG_ABSENT


@dataclass
class Fix:
    """A replacement for the submitted code that should remove the problem."""
    fixed_code: str
    explanation: str = ""   # later: this is where 'teach, don't just patch' lives


@dataclass
class RunResult:
    """What the sandbox observed when it ran a script."""
    exit_code: Optional[int]
    stdout: str
    stderr: str
    timed_out: bool
    duration_s: float

    def saw(self, marker: str) -> bool:
        return marker in self.stdout
