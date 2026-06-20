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

from .contract import BUG_ABSENT, BUG_PRESENT, Finding, Fix, RunResult, Sweep
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
    fix_id: Optional[int] = None   # db id of the offered fix, for accept/reject
    sweep: Optional[Sweep] = None  # the standing 'what aren't we asking?' gate


# Do-no-harm check: after the fix, the code must at least still import/compile
# cleanly — this catches a fix that breaks the file outright. It is a LIGHT, GENERIC
# check (honest limit): combined with the re-proof (the bug is gone), it is the
# Floor-1 do-no-harm floor. A per-finding BEHAVIOURAL smoke — assert the intended
# contract still holds on in-domain inputs — is the next improvement.
SMOKE = (
    "import target\n"
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
        user_level: str = "normal", smoke: Optional[str] = None) -> Outcome:
    user_id = store.add_user(user_level)
    submission_id = store.add_submission(user_id, code, language)

    # 1) FIND the top problem.
    finding = engine.find(code, language)
    finding_id = store.add_finding(submission_id, finding.problem, finding.rank, finding.confidence)

    # STANDING SWEEP GATE: runs every time, automatically. Discloses the boundaries
    # of what GAP did (acted on ONE problem; what could only be flagged; the
    # across-time gap) so 'all clear' is never implied. NOT a second guesser.
    sweep = Sweep(boundary_notes=engine.sweep(code, finding))

    # 2) PROVE it by running a demonstration against the original code.
    proof = engine.prove(code, finding)

    # Mechanical anti-inlining gate: a proof that does not IMPORT the submitted code
    # proves nothing about it (and silently breaks the fix re-proof, which swaps
    # target.py). Reject it rather than trust a self-referential demonstration.
    if "target" not in proof.script:
        store.add_proof(finding_id, proof.script, False)
        return Outcome(finding, False, "(proof did not import the submitted code)", False, None,
                       "Proof rejected: it did not import `target`, so it tested a copy, "
                       "not your actual code — that proves nothing.", sweep=sweep)

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
                           "Could not prove the problem by running it — flagged, not claimed.",
                           sweep=sweep)

        # 2b) ADJUDICATION GATE. A proof that RAN is necessary but not sufficient: the
        # engine can "prove" an out-of-domain crash or a design opinion. A skeptical
        # second pass rejects those before they ever reach the user. (No-op for engines
        # that don't override adjudicate, e.g. the stub.)
        valid, reason = engine.adjudicate(code, finding, proof.script, r1.stdout)
        if not valid:
            return Outcome(finding, False, f"adjudicator rejected: {reason}"[:200], False, None,
                           "Proof rejected by the adjudication gate — out-of-domain input or design "
                           "opinion, not a real defect on realistic input.", sweep=sweep)

        # 3) FIX, then RE-PROVE against the fixed code, then SMOKE-check for harm.
        fix = engine.fix(code, finding)
        _write(workdir, "target.py", fix.fixed_code)
        r2 = run_script("proof.py", workdir)
        gone = r2.saw(BUG_ABSENT)

        # Per-sample behavioural smoke if provided (the eval passes one); else the
        # light generic import-check. A behavioural smoke is what turns "the fix
        # re-proved" into "the fix actually produces correct behaviour".
        _write(workdir, "smoke.py", smoke or SMOKE)
        r3 = run_script("smoke.py", workdir)
        no_harm = r3.saw("GAP_SMOKE:OK")

        fix_ok = gone and no_harm
        fix_id = store.add_fix(finding_id, fix.fixed_code, fix_ok)

        if fix_ok:
            return Outcome(finding, True, _detail(r1), True, fix,
                           "Problem proven, fix re-proven, nothing broke.",
                           fix_id=fix_id, sweep=sweep)

        notes = "Fix withheld: "
        if not gone:
            notes += "re-proof still shows the bug. "
        if not no_harm:
            notes += "smoke check failed (the fix broke the code). "
        return Outcome(finding, True, _detail(r1), False, None, notes.strip(), sweep=sweep)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
