"""GAP pipeline (Floor 1) — orchestrates find -> prove -> fix -> re-prove -> record.

The scary part lives here: a finding is only ASSERTED if its proof actually ran
and showed the bug; a fix is only OFFERED if re-running the proof shows the bug
gone AND a smoke check shows we did not break the code.
"""
from __future__ import annotations
import os
import shutil
import tempfile
from dataclasses import dataclass
from typing import Optional

from .contract import BUG_ABSENT, BUG_PRESENT, Finding, Fix, RunResult
from .engine import Engine
from .sandbox import run_script
from .store import Store


@dataclass
class Outcome:
    finding: Finding
    proven: bool
    proof_detail: str
    fix_offered: bool
    fix: Optional[Fix]
    notes: str


# Do-no-harm check: after the fix, the code must still do its basic job.
SMOKE = (
    "import target\n"
    "d = {}\n"
    "n = target.migrate([(1, 'x')], d)\n"
    "assert n == 1 and d == {1: 'x'}, 'smoke failed'\n"
    "print('GAP_SMOKE:OK')\n"
)


def _write(workdir: str, name: str, content: str) -> None:
    with open(os.path.join(workdir, name), "w", encoding="utf-8") as f:
        f.write(content)


def _detail(r: RunResult) -> str:
    if r.timed_out:
        return "(proof timed out)"
    return (r.stdout or r.stderr).strip()


def run(code: str, language: str, engine: Engine, store: Store,
        user_level: str = "normal") -> Outcome:
    user_id = store.add_user(user_level)
    submission_id = store.add_submission(user_id, code, language)

    # 1) FIND the top problem.
    finding = engine.find(code, language)
    finding_id = store.add_finding(submission_id, finding.problem, finding.rank, finding.confidence)

    # 2) PROVE it by running a demonstration against the original code.
    proof = engine.prove(code, finding)
    workdir = tempfile.mkdtemp(prefix="gap_")
    try:
        _write(workdir, "target.py", code)
        _write(workdir, "proof.py", proof.script)
        r1 = run_script("proof.py", workdir)
        proven = r1.saw(BUG_PRESENT)
        store.add_proof(finding_id, proof.script, proven)

        if not proven:
            # Honest gate: if we cannot prove it, we FLAG it, we do not claim it.
            return Outcome(finding, False, _detail(r1), False, None,
                           "Could not prove the problem by running it — flagged, not claimed.")

        # 3) FIX, then RE-PROVE against the fixed code, then SMOKE-check for harm.
        fix = engine.fix(code, finding)
        _write(workdir, "target.py", fix.fixed_code)
        r2 = run_script("proof.py", workdir)
        gone = r2.saw(BUG_ABSENT)

        _write(workdir, "smoke.py", SMOKE)
        r3 = run_script("smoke.py", workdir)
        no_harm = r3.saw("GAP_SMOKE:OK")

        fix_ok = gone and no_harm
        store.add_fix(finding_id, fix.fixed_code, fix_ok)

        if fix_ok:
            return Outcome(finding, True, _detail(r1), True, fix,
                           "Problem proven, fix re-proven, nothing broke.")

        notes = "Fix withheld: "
        if not gone:
            notes += "re-proof still shows the bug. "
        if not no_harm:
            notes += "smoke check failed (the fix broke the code). "
        return Outcome(finding, True, _detail(r1), False, None, notes.strip())
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
