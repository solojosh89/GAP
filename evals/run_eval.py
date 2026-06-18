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

NOTE (honest scope): the FIX do-no-harm gate uses an example-coupled smoke check in
Floor 1, so FIX is NOT scored here — only FIND + PROVE, which is the load-bearing
claim. Fix scoring lands once the smoke check is per-sample.
"""
from __future__ import annotations
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gap.engine import StubEngine          # noqa: E402
from gap.pipeline import run               # noqa: E402
from gap.store import Store                # noqa: E402
from evals.corpus import SAMPLES           # noqa: E402


def make_engine(kind: str):
    if kind == "stub":
        return StubEngine()
    if kind == "llm":
        from gap.openai_engine import OpenAICompatEngine
        return OpenAICompatEngine()
    raise SystemExit(f"unknown engine '{kind}' (use: stub | llm)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default=os.environ.get("GAP_ENGINE", "stub"),
                    choices=["stub", "llm"], help="which engine to grade")
    args = ap.parse_args()

    engine = make_engine(args.engine)
    store = Store(":memory:")

    tp = fp = tn = fn = err = 0
    rows = []
    for s in SAMPLES:
        errored = False
        try:
            out = run(s["code"], s["language"], engine, store, user_level="normal")
            proven = out.proven
            detail = (out.proof_detail or "").replace("\n", " ")[:48]
        except Exception as e:  # transport/quota failure: measured NOTHING — must not count
            errored = True
            proven = False
            detail = f"ERROR: {e}".replace("\n", " ")[:48]

        bug = s["has_bug"]
        if errored:
            # A failed call is NOT a true negative. Counting silence-by-error as a
            # pass is the exact false comfort GAP exists to kill. It's VOID.
            verdict, mark = "ERR", "VOID (no answer)"
            err += 1
        elif bug and proven:
            verdict, mark = "TP", "OK"
            tp += 1
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
                     "proven" if proven else "silent", verdict, mark, detail))

    # ---- report ---- #
    print("=" * 78)
    print(f"GAP VALIDATION EVAL   engine={args.engine}   samples={len(SAMPLES)}")
    if args.engine == "stub":
        print("(StubEngine only knows the migrate bug - other buggy samples will MISS.\n"
              " That is expected: the stub is a stand-in. Run --engine llm for a real score.)")
    print("=" * 78)
    print(f"{'sample':22} {'kind':6} {'result':7} {'class':5} {'flag':12} detail")
    print("-" * 78)
    for name, kind, result, verdict, mark, detail in rows:
        print(f"{name:22} {kind:6} {result:7} {verdict:5} {mark:12} {detail}")
    print("-" * 78)

    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None

    def pct(x):
        return "n/a" if x is None else f"{x*100:.0f}%"

    scored = tp + fn + tn + fp
    print(f"TP={tp}  FN={fn}  TN={tn}  FP={fp}  ERR(void)={err}   scored={scored}/{len(SAMPLES)}")
    print(f"Recall (bugs caught)      : {pct(recall)}   [{tp}/{tp+fn}]")
    print(f"Precision (claims correct): {pct(precision)}   [{tp}/{tp+fp}]")
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

    # ---- verdict: false positives are the cardinal sin ---- #
    if fp > 0:
        print(f"VERDICT: [FAIL] THESIS VIOLATED - {fp} false alarm(s) on clean code.")
        print("GAP's whole promise is 'prove, never assert'. A proven bug in correct code")
        print("means the engine fooled its own gate. This engine is NOT safe to ship as-is.")
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

    # Non-zero exit on the unforgivable failure, so this can gate CI later.
    sys.exit(1 if fp > 0 else 0)


if __name__ == "__main__":
    main()
