"""GAP real engine — Claude-backed implementation of the Engine interface.

This is the part that needs a Claude API key. Everything else (sandbox, store,
pipeline, gates, UI) is proven and waiting on this. The engine does ONE judgment
job per call and returns the same Finding / Proof / Fix objects the StubEngine
returns, so it drops into the exact same pipeline.

Model rule (see docs/ENGINE_SPEC.md): judgment runs on Opus 4.8 with adaptive
thinking at high effort. Structured outputs guarantee the shapes the pipeline
consumes. No API key -> a clear error at construction, not a silent stub.

NOTE: this is the spec made executable. It is intentionally NOT wired into app.py
yet (no key available). The prompts below are grounded in the two proven worked
examples in docs/ENGINE_SPEC.md.
"""
from __future__ import annotations
import json

from .contract import BUG_ABSENT, BUG_PRESENT, Finding, Fix, Proof
from .engine import Engine

MODEL = "claude-opus-4-8"          # judgment task -> the crown-jewel model, per the rule
_COMMON = dict(
    model=MODEL,
    max_tokens=16000,
    thinking={"type": "adaptive"},        # adaptive only on 4.8; budget_tokens 400s
    output_config={"effort": "high"},     # judgment is intelligence-sensitive
)

# ---- the one rule the engine must obey, in every call -----------------------
PROVE_DONT_ASSERT = (
    "GAP's single inviolable rule: PROVE, never ASSERT. You may only claim a "
    "problem that can be DEMONSTRATED by running code. If you cannot construct a "
    "runnable demonstration that needs no expertise to trust, say so honestly "
    "(confidence 'none') rather than inventing a finding. A false finding is more "
    "dangerous than no finding, because the user will act on it."
)

FIND_SYSTEM = f"""You are GAP's finding engine. Given a source file, name the ONE
most dangerous real problem in it — the one most likely to cause silent wrong
behaviour in production months later.

{PROVE_DONT_ASSERT}

Rank by danger (1 = act on this first). Prefer problems that live in pure,
extractable logic (they can be proven by running) over problems that need a live
DB / network / framework (those can only be flagged). If you genuinely find no
provable problem, return confidence 'none' and say plainly that you did not.

Worked reference (the shape of a good finding):
- "migrate() reports rows it TRIED to copy, not rows that landed; skipped rows
  are still counted" — a count that lies, leading the user to trust it and delete
  a backup. High danger, provable by running.
- "analyzeEmotionalPatterns divides by a sentinel baseline of 1 when there is no
  neutral-mood data, so the multiplier becomes the raw dollar average (e.g. 175x)"
  — a fabricated magnitude shown as a high-risk diagnosis. Provable by running the
  extracted pure function."""

PROVE_SYSTEM = f"""You are GAP's proof engine. Write a SELF-CONTAINED script that
DEMONSTRATES the given finding by running, with no expertise required to read the
verdict.

{PROVE_DONT_ASSERT}

Rules for the script:
- It must print exactly one of "{BUG_PRESENT}" or "{BUG_ABSENT}" (plus a short
  human detail), based on observed behaviour — never on your assertion.
- It must exercise the REAL code under test. For a plain module, import it as the
  target. For a framework file (React/Vue/etc.), EXTRACT the pure function under
  test VERBATIM into the script and call it directly — do not depend on a DOM or
  framework runtime.
- Choose `language` = the language the code is written in (python | node).
- Keep it deterministic and fast (well under 10s, no network, no real DB)."""

FIX_SYSTEM = f"""You are GAP's fix engine. Produce the MINIMAL change that removes
the proven problem and breaks nothing else (Chesterton's Fence on the user's code).

{PROVE_DONT_ASSERT}

Return three things:
- fixed_code: the corrected version, matching the file's own style.
- explanation: one terse line on WHAT changed.
- lesson: the PATTERN behind the bug, so the user catches it themselves next time
  and needs GAP less over time — teach one notch, do not just patch. One or two
  plain sentences, with a gut-check they can apply (e.g. "if every item were
  skipped, would the count still climb? then you're counting tries, not results")."""

_FINDING_SCHEMA = {
    "type": "object",
    "properties": {
        "problem": {"type": "string"},
        "rank": {"type": "integer"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low", "none"]},
        "why_it_matters": {"type": "string"},
    },
    "required": ["problem", "rank", "confidence", "why_it_matters"],
    "additionalProperties": False,
}

_PROOF_SCHEMA = {
    "type": "object",
    "properties": {
        "language": {"type": "string", "enum": ["python", "node"]},
        "script": {"type": "string"},
    },
    "required": ["language", "script"],
    "additionalProperties": False,
}

_FIX_SCHEMA = {
    "type": "object",
    "properties": {
        "fixed_code": {"type": "string"},
        "explanation": {"type": "string"},
        "lesson": {"type": "string"},
    },
    "required": ["fixed_code", "explanation", "lesson"],
    "additionalProperties": False,
}


class RealEngine(Engine):
    def __init__(self, client=None):
        # Import lazily so the rest of GAP runs without the anthropic package.
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "RealEngine needs the 'anthropic' package: pip install anthropic"
            ) from e
        # anthropic.Anthropic() resolves ANTHROPIC_API_KEY from the environment;
        # with no key it raises a clear auth error on first use, not a silent stub.
        self.client = client or anthropic.Anthropic()

    def _ask(self, system: str, user: str, schema: dict) -> dict:
        resp = self.client.messages.create(
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": "high",
                           "format": {"type": "json_schema", "schema": schema}},
            model=MODEL,
            max_tokens=16000,
            thinking={"type": "adaptive"},
        )
        text = next(b.text for b in resp.content if b.type == "text")
        return json.loads(text)

    def find(self, code: str, language: str) -> Finding:
        d = self._ask(FIND_SYSTEM, f"Language: {language}\n\n```\n{code}\n```", _FINDING_SCHEMA)
        return Finding(problem=d["problem"], rank=d["rank"],
                       confidence=d["confidence"], why_it_matters=d["why_it_matters"])

    def prove(self, code: str, finding: Finding) -> Proof:
        user = (f"Finding: {finding.problem}\n\nCode under test:\n```\n{code}\n```\n\n"
                f"Write the demonstration script.")
        d = self._ask(PROVE_SYSTEM, user, _PROOF_SCHEMA)
        return Proof(script=d["script"], language=d["language"])

    def fix(self, code: str, finding: Finding) -> Fix:
        user = (f"Proven finding: {finding.problem}\n\nCode:\n```\n{code}\n```\n\n"
                f"Produce the minimal fix, an explanation, and the lesson.")
        d = self._ask(FIX_SYSTEM, user, _FIX_SCHEMA)
        return Fix(fixed_code=d["fixed_code"], explanation=d["explanation"],
                   lesson=d["lesson"])
