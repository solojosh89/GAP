
"""Run the GAP walking skeleton end-to-end on one file and print a plain result.

    python run_skeleton.py [path_to_python_file]

Defaults to the bundled example (the 'count lie' migration bug).
"""
import os
import sys

from dotenv import load_dotenv
load_dotenv()

from gap.engine import StubEngine
from gap.pipeline import run
from gap.store import Store

DEFAULT = os.path.join(os.path.dirname(__file__), "examples", "buggy_migrate.py")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    with open(path, "r", encoding="utf-8") as f:
        code = f.read()

    store = Store(":memory:")
    outcome = run(code, "python", StubEngine(), store, user_level="simple")

    print("=" * 60)
    print(f"GAP looked at: {os.path.basename(path)}")
    print("=" * 60)
    print(f"\nProblem found: {outcome.finding.problem}\n")
    print(f"Why it matters: {outcome.finding.why_it_matters}\n")
    if outcome.proven:
        print(f"PROVED it by running your code  ->  {outcome.proof_detail}")
    else:
        print(f"Could NOT prove it  ->  {outcome.proof_detail}")

    if outcome.fix_offered and outcome.fix is not None:
        print("\nFIX (re-proven, nothing broke):\n")
        print(outcome.fix.fixed_code)
        print(f"In short: {outcome.fix.explanation}")
    else:
        print(f"\nNo fix offered. {outcome.notes}")

    if outcome.sweep is not None:
        print("\nWhat I did NOT check (the standing sweep - so you never assume 'all clear'):")
        if outcome.sweep.acted_on_one:
            print("  - I showed the ONE most dangerous problem, not every problem.")
        for note in outcome.sweep.boundary_notes:
            print(f"  - {note}")
        if outcome.sweep.across_time_gap:
            print("  - I can't yet tell whether this breaks months from now (across-time check not built).")

    print("\n(There may be more problems - this shows one. Never assume 'all clear'.)")


if __name__ == "__main__":
    main()
