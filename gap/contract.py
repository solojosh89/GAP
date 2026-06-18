"""GAP engine contract — the fixed shapes the pipeline produces and consumes.

These are deliberately small. The real (LLM-backed) engine and the stub engine
both speak in these objects, so either can plug into the same pipeline.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

# Proof scripts communicate their verdict by printing one of these markers.
BUG_PRESENT = "GAP_PROOF:BUG_PRESENT"
BUG_ABSENT = "GAP_PROOF:BUG_ABSENT"


@dataclass
class Finding:
    """One problem the engine claims exists in the submitted code."""
    problem: str            # developer-facing description (Normal/Expert tiers)
    rank: int               # 1 = most dangerous; the pipeline acts on the top one only
    confidence: str         # "high" | "medium" | "low" | "none"
    why_it_matters: str = ""
    # The code's EVIDENT contract, inferred from its name, structure, and docstring.
    # A finding is only legitimate if it shows behaviour that VIOLATES this intent on
    # realistic in-domain inputs — not behaviour the engine personally dislikes, and
    # not a crash forced by feeding out-of-domain garbage. This is the contract gate:
    # it stops the engine flagging deliberate defensive behaviour (e.g. a function
    # that returns a safe default on purpose) as if it were a defect.
    intent: str = ""
    # Vibe-coder tier (Simple): ONE plain sentence with no jargon, plus a homely
    # analogy. NEVER shows function names, line numbers, proof markers, or code.
    plain: str = ""
    analogy: str = ""


@dataclass
class Proof:
    """A self-contained script that DEMONSTRATES the finding by running."""
    script: str             # source; prints BUG_PRESENT or BUG_ABSENT
    language: str = "python"  # which runtime runs it (python | node | ...). The
                              # pipeline routes to the matching runner (see gap/runners.py).


@dataclass
class Fix:
    """A replacement for the submitted code that should remove the problem."""
    fixed_code: str
    explanation: str = ""   # terse: WHAT changed in the code
    lesson: str = ""        # 'teach, don't just patch': the pattern, so the user
                            # catches it themselves next time and needs GAP less


@dataclass
class Sweep:
    """The standing 'what aren't we asking?' gate — runs automatically every time,
    like the prove-gate and fix-gate. It is GAP's line over a linter: it raises the
    question the user didn't know to ask.

    CRITICAL: it does NOT invent more unproven problems (that would be the exact
    prove-don't-assert violation GAP exists to kill). It discloses the BOUNDARIES of
    what GAP just did — what it acted on, what it could only flag not prove, and what
    it cannot see at all — so 'all clear' is never implied. Never 'done', by design.
    """
    acted_on_one: bool = True       # Floor 1 acts on the single most-dangerous problem only
    across_time_gap: bool = True    # no outcome data yet -> can't say if this breaks later
    boundary_notes: list = field(default_factory=list)  # what could only be flagged, not proven


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
