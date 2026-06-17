"""GAP engine — interface + a STUB implementation.

The stub is deliberately hard-coded for the example file, so the SKELETON proves
the machinery (sandbox + prove/fix/re-prove + recording) WITHOUT depending on a
live LLM. The real Claude-backed engine implements the same three methods and
drops into the exact same pipeline. This boundary is intentional and named.
"""
from __future__ import annotations

from .contract import BUG_ABSENT, BUG_PRESENT, Finding, Fix, Proof


class Engine:
    """Interface. find -> the top problem; prove -> a runnable demo; fix -> patched code."""

    def find(self, code: str, language: str) -> Finding:
        raise NotImplementedError

    def prove(self, code: str, finding: Finding) -> Proof:
        raise NotImplementedError

    def fix(self, code: str, finding: Finding) -> Fix:
        raise NotImplementedError


class StubEngine(Engine):
    """Hard-coded for examples/buggy_migrate.py (the 'count lie' bug).

    Honesty rule: the stub only KNOWS one bug. If the submitted code is not the
    example it recognizes, it must NOT fabricate a finding about code it never
    analyzed — it says so. (The real engine replaces this; the stub must still
    obey the prove-don't-assert principle.)
    """

    def _recognizes(self, code: str) -> bool:
        return "def migrate" in code and "migrated" in code

    def find(self, code: str, language: str) -> Finding:
        if not self._recognizes(code):
            return Finding(
                problem=(
                    "This is the DEMO (stub) engine - it only knows one example bug "
                    "and did NOT recognize your file. It will not invent a problem it "
                    "cannot prove. The real Claude-backed engine is what analyzes "
                    "arbitrary code."
                ),
                rank=0,
                confidence="none",
                why_it_matters=(
                    "GAP's whole point is to prove, never to assert. A demo that "
                    "guessed a bug here would be the exact dishonesty GAP exists to kill."
                ),
            )
        return Finding(
            problem=(
                "migrate() reports how many rows it TRIED to copy, not how many "
                "actually landed. Rows that already exist are skipped but still counted."
            ),
            rank=1,
            confidence="high",
            why_it_matters=(
                "The success number can say '5 migrated' while moving 0 - trust it and "
                "delete your backup, and the skipped rows are gone."
            ),
        )

    def prove(self, code: str, finding: Finding) -> Proof:
        if finding.confidence == "none":
            # Nothing was claimed, so there is nothing to prove. Print BUG_ABSENT
            # cleanly instead of crashing on code the stub never understood.
            return Proof(script=f'print("{BUG_ABSENT}")  # stub had no claim to prove\n')
        # The proof imports the code-under-test as `target` and compares the
        # reported count against the rows that actually got inserted.
        script = f'''
import target

dest = {{1: "a", 2: "b", 3: "c"}}          # 3 rows already present
rows = [(1, "a"), (2, "b"), (3, "c"), (4, "d"), (5, "e")]
before = len(dest)
reported = target.migrate(rows, dest)
actual = len(dest) - before
detail = f"reported={{reported}} actual={{actual}}"
print("{BUG_PRESENT}" if reported != actual else "{BUG_ABSENT}", detail)
'''
        return Proof(script=script)

    def fix(self, code: str, finding: Finding) -> Fix:
        fixed = (
            "def migrate(rows, destination):\n"
            "    migrated = 0\n"
            "    for key, value in rows:\n"
            "        if key not in destination:      # skip rows that already exist\n"
            "            destination[key] = value\n"
            "            migrated += 1               # count only rows that actually landed\n"
            "    return migrated\n"
        )
        return Fix(
            fixed_code=fixed,
            explanation="Move `migrated += 1` inside the `if` so it counts real inserts, not attempts.",
            lesson=(
                "Count the success, not the attempt: put your `+= 1` on the line that "
                "does the actual work, so a skipped item never inflates the total. "
                "Gut check next time - if every item were skipped, would the count "
                "still climb? If yes, you're counting tries, not results."
            ),
        )
