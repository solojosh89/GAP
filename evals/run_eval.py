
"""GAP validation eval — runs the corpus through the REAL pipeline and scores it.

What it measures: the core thesis — FIND + PROVE.
  - On a buggy sample, did GAP PROVE the bug by running?  (true positive)
  - On a clean sample, did GAP stay SILENT?                 (true negative)
A "proven finding" on clean code is a FALSE POSITIVE — the one failure GAP must
never make. The verdict weighs that above everything else.

Usage:
    python evals/run_eval.py                  # StubEngine (offline; only knows migrate)
    python evals/run_eval.py --engine llm     # your OpenAI-compatible engine (Kimi etc.)

For the llm engine, set the key first (never stored):
    set GAP_LLM_API_KEY=...      (Windows)   /   export GAP_LLM_API_KEY=...  (POSIX)
    optional: GAP_LLM_BASE_URL, GAP_LLM_MODEL  (default Kimi/Moonshot)

Also scores the FIX stage: each buggy sample carries a behavioural oracle, and any
OFFERED fix is INDEPENDENTLY re-run against it in a fresh sandbox. A fix that
re-proves green but fails the oracle (still broken) is the fix-stage cardinal sin —
it FAILs the verdict, exactly like a false positive on clean code.
"""
from __future__ import annotations
import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gap.engine import StubEngine          # noqa: E402
from gap.pipeline import run               # noqa: E402
from gap.sandbox import run_script         # noqa: E402
from gap.store import Store                # noqa: E402
from evals.corpus import SAMPLES           # noqa: E402


def make_engine(kind: str):
    if kind == "stub":
        return StubEngine()
    if kind == "llm":
        from gap.openai_engine import OpenAICompatEngine
        return OpenAICompatEngine()
    raise SystemExit(f"unknown engine '{kind}' (use: stub | llm)")


def _verify_fix(sample, fixed_code):
    """Independently confirm an OFFERED fix actually produces correct behaviour.

    Defense-in-depth (the #10 lesson: don't trust an untested path): re-run the
    sample's behavioural oracle against the fixed code in a FRESH sandbox, rather
    than trusting the pipeline's own smoke result. Returns:
        True  -> fix verified correct
        False -> fix offered but behaviour is still wrong (fix-stage cardinal sin)
        None  -> no oracle for this sample, cannot verify
    """
    smoke = sample.get("smoke")
    if not smoke:
        return None
    wd = tempfile.mkdtemp(prefix="gap_fixchk_")
    try:
        with open(os.path.join(wd, "target.py"), "w", encoding="utf-8") as f:
            f.write(fixed_code)
        with open(os.path.join(wd, "smoke.py"), "w", encoding="utf-8") as f:
            f.write(smoke)
        return run_script("smoke.py", wd).saw("GAP_SMOKE:OK")
    finally:
        shutil.rmtree(wd, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default=os.environ.get("GAP_ENGINE", "stub"),
                    choices=["stub", "llm"], help="which engine to grade")
    ap.add_argument("--spacing", type=float,
                    default=float(os.environ.get("GAP_EVAL_SPACING", "3")),
                    help="seconds to wait between samples when engine=llm (default 3). "
                         "Raise to 8-10 if you hit 429s on free tiers.")
    args = ap.parse_args()

    engine = make_engine(args.engine)
    store = Store(":memory:")

    tp = fp = tn = fn = err = 0
    fix_ok = fix_miss = fix_bad = 0
    rows = []
    for i, s in enumerate(SAMPLES):
        # Space calls so free-tier quotas don't stack up into cascading 429s.
        # The adjudicator already retries once; spacing stops the burst from forming.
        if args.engine == "llm" and i > 0:
            import time
            time.sleep(args.spacing)

        errored = False
        out = None
        try:
            out = run(s["code"], s["language"], engine, store,
                      user_level="normal", smoke=s.get("smoke"))
            proven = out.proven
            detail = (out.proof_detail or "").replace("\n", " ")[:48]
        except Exception as e:  # transport/quota failure: measured NOTHING — must not count
            errored = True
            proven = False
            detail = f"ERROR: {e}".replace("\n", " ")[:48]

        bug = s["has_bug"]
        fixmark = ""
        if errored:
            # A failed call is NOT a true negative. Counting silence-by-error as a
            # pass is the exact false comfort GAP exists to kill. It's VOID.
            verdict, mark = "ERR", "VOID (no answer)"
            err += 1
        elif bug and proven:
            verdict, mark = "TP", "OK"
            tp += 1
            # FIX-STAGE SCORE. `proven` already guarantees a valid importing proof
            # (the pipeline's anti-inlining gate), so a fix re-proof is meaningful.
            # Independently re-verify any OFFERED fix against the behavioural oracle.
            if out is not None and out.fix_offered and out.fix is not None:
                verified = _verify_fix(s, out.fix.fixed_code)
                if verified is True:
                    fix_ok += 1; fixmark = "FIX OK"
                elif verified is False:
                    fix_bad += 1; fixmark = "FIX BROKEN"   # cardinal sin of the fix stage
                else:
                    fixmark = "fix (no oracle)"
            else:
                fix_miss += 1; fixmark = "FIX MISS"
        elif bug and not proven:
            verdict, mark = "FN", "MISS"
            fn += 1
        elif (not bug) and proven:
            verdict, mark = "FP", "FALSE ALARM"
            fp += 1
        else:
            verdict, mark = "TN", "OK"
            tn += 1
        rows.append((s["name"], "bug" if bug else "clean",
                     "proven" if proven else "silent", verdict, mark, fixmark, detail))

    # ---- report ---- #
    print("=" * 78)
    print(f"GAP VALIDATION EVAL   engine={args.engine}   samples={len(SAMPLES)}")
    if args.engine == "stub":
        print("(StubEngine only knows the migrate bug - other buggy samples will MISS.\n"
              " That is expected: the stub is a stand-in. Run --engine llm for a real score.)")
    print("=" * 78)
    print(f"{'sample':22} {'kind':6} {'result':7} {'cls':4} {'flag':12} {'fix':15} detail")
    print("-" * 96)
    for name, kind, result, verdict, mark, fixmark, detail in rows:
        print(f"{name:22} {kind:6} {result:7} {verdict:4} {mark:12} {fixmark:15} {detail}")
    print("-" * 96)

    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None

    def pct(x):
        return "n/a" if x is None else f"{x*100:.0f}%"

    scored = tp + fn + tn + fp
    fix_scored = fix_ok + fix_miss + fix_bad
    print(f"TP={tp}  FN={fn}  TN={tn}  FP={fp}  ERR(void)={err}   scored={scored}/{len(SAMPLES)}")
    print(f"Recall (bugs caught)      : {pct(recall)}   [{tp}/{tp+fn}]")
    print(f"Precision (claims correct): {pct(precision)}   [{tp}/{tp+fp}]")
    if fix_scored:
        print(f"Fix (of proven bugs)      : {pct(fix_ok / fix_scored)}   "
              f"[OK={fix_ok} MISS={fix_miss} BROKEN={fix_bad}]")
    print("=" * 78)

    # ---- void check FIRST: if calls failed, we measured nothing ---- #
    if err >= len(SAMPLES):
        print("VERDICT: [VOID] could NOT measure GAP — every call failed (quota / rate")
        print("limit / network), so this says nothing about GAP's quality. Not a verdict.")
        print("Fix: wait for the free quota to reset, or switch engine (e.g. Groq), then rerun.")
        print("=" * 78)
        sys.exit(2)
    if err > 0:
        print(f"NOTE: {err} sample(s) VOID (call failed) — excluded from the score below.")

    # ---- verdict: false positives AND broken offered fixes are the cardinal sins ---- #
    if fp > 0 or fix_bad > 0:
        bits = []
        if fp > 0:
            bits.append(f"{fp} false alarm(s) on clean code")
        if fix_bad > 0:
            bits.append(f"{fix_bad} offered fix(es) that DON'T actually fix the bug")
        print(f"VERDICT: [FAIL] THESIS VIOLATED - {'; '.join(bits)}.")
        print("GAP's promise is 'prove, never assert' — and that extends to fixes: never")
        print("offer one the behaviour says is still broken. This engine is NOT safe as-is.")
    elif tp + fn == 0:
        print("VERDICT: [--] no buggy samples scored (check corpus).")
    elif recall == 1.0:
        print("VERDICT: [PASS] STRONG - every bug proven, zero false alarms on clean code.")
        print("On this corpus, GAP holds its promise with this engine.")
    else:
        print(f"VERDICT: [~] PROMISING - zero false alarms, but missed {fn} bug(s).")
        print("Safe (it never lied), but not yet complete. Misses are far less dangerous")
        print("than false alarms - GAP flags what it can't prove rather than guessing.")
    print("=" * 78)

    # Non-zero exit on the unforgivable failures, so this can gate CI later.
    sys.exit(1 if (fp > 0 or fix_bad > 0) else 0)


if __name__ == "__main__":
    main()
