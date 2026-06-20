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

THE CONTRACT GATE — read this before flagging anything:
First, infer the code's EVIDENT INTENT (its contract) from its name, structure, and
any docstring, and state it in the `intent` field. Then a problem is legitimate ONLY
if it VIOLATES that intent on realistic, in-domain inputs. Specifically:
- Do NOT flag DELIBERATE behaviour as a bug. If a function clearly chooses a safe
  default on purpose (e.g. `safe_divide` that returns 0.0 when the divisor is 0, with
  an explicit guard), that IS its intent — disagreeing with the design choice is not
  a bug. Returning the documented/evident value is correct by definition.
- Do NOT manufacture a failure by feeding OUT-OF-DOMAIN garbage. A numeric `clamp`
  crashing on a string input is not a defect — strings are outside its domain.
- A real bug is a contradiction between what the code EVIDENTLY MEANS to do and what
  it ACTUALLY does on inputs it is meant to handle (e.g. a function named is_even
  that returns True for odd numbers; a count that claims successes but counts attempts).
If the only thing you can find is a design opinion or an out-of-domain crash, that is
NOT a finding — return confidence 'none'.

MOST CODE YOU REVIEW IS CORRECT. Returning confidence 'none' is a SUCCESS and the
right answer for clean code — it is NOT a failure or a cop-out. Never invent a finding
to seem useful. A false alarm is worse than saying "nothing provable here."

Rank by danger (1 = act on this first). Prefer problems in pure, extractable logic
(provable by running) over ones needing a live DB / network / framework (flag-only).

Worked reference (the shape of a good finding — all are intent violations on in-domain input):
- "migrate() reports rows it TRIED to copy, not rows that landed; skipped rows are
  still counted" — intent is to count successful inserts; it counts attempts. Provable.
- "is_even(n) returns True for odd numbers" — name promises even-check; behaviour is
  the opposite. Provable on ordinary integers."""

# Appended separately so the worked reference above stays focused on the technical
# judgment. This is the Simple-tier requirement: ALWAYS produce both fields, even
# though only the simple UI tier displays them — generating them is nearly free
# and means tier selection never silently falls back to the technical sentence.
FIND_SYSTEM += """

ADDITIONALLY, always fill two more fields for non-technical readers — do this even
when confidence is high and the finding is clearly technical:
- "plain": ONE sentence, no jargon, no function names, no numbers, no code terms.
  A non-programmer must understand exactly what could go wrong for them in practice.
  Example: "Your interest calculation could multiply some customers' balances by 100x
  instead of adding the small percentage you intended."
- "analogy": one short, homely, everyday comparison that makes the plain sentence
  click. Example: "It's like reading '5% off' as '500% off' at checkout."
If confidence is "none" (no real finding), set plain to a one-sentence reassurance
("I ran your code and could not find a provable problem in it.") and analogy to "" """

PROVE_SYSTEM = f"""You are GAP's proof engine. Write a SELF-CONTAINED script that
DEMONSTRATES the given finding by running, with no expertise required to read the
verdict.

{PROVE_DONT_ASSERT}

Rules for the script:
- It must print exactly one of "{BUG_PRESENT}" or "{BUG_ABSENT}" (plus a short
  human detail), based on observed behaviour — never on your assertion.
- CRITICAL: you MUST import the submitted code and call it — `import target` (python)
  or `from target import NAME`. Do NOT copy, paste, or redefine the function inside
  your script. The harness swaps `target.py` between the ORIGINAL and the FIXED code
  to re-check the fix; if you inline a copy, your proof tests the copy, not the real
  code, the fix check becomes meaningless, and the proof is rejected. (Node: the
  submitted code is written to `target.js` — `const t = require('./target')`.)
- Use REALISTIC, IN-DOMAIN inputs only. The demonstration must show behaviour that
  contradicts the code's evident intent — NOT a crash you forced with out-of-domain
  garbage, and NOT behaviour you merely consider suboptimal. If your only "proof"
  needs an input the function was never meant to handle, print "{BUG_ABSENT}".
- Only if a framework file genuinely CANNOT be imported may you extract the pure
  function verbatim — and say so. For plain modules, importing is mandatory.
- Choose `language` = the language the code is written in (python | node).
- Keep it deterministic and fast (well under 10s, no network, no real DB)."""

ADJUDICATE_SYSTEM = f"""You are GAP's adjudicator — a skeptical reviewer whose JOB is
to REJECT weak findings. A proof has already run and shown a "bug". Your call: is it a
GENUINE defect, or an artefact that should never reach the user?

{PROVE_DONT_ASSERT}

Answer INVALID (reject) if ANY of these is true:
- the proof used OUT-OF-DOMAIN inputs the function was never meant to handle
  (e.g. strings passed to a numeric add(); low > high invalid bounds to clamp();
  None where a real value is required),
- the flagged behaviour is the code's DELIBERATE, evident intent (e.g. a function
  that returns a safe default on purpose),
- it is a matter of design opinion, style, or a hypothetical, not wrong behaviour on
  realistic input.

Answer VALID (approve) if the proof shows the code doing something that CONTRADICTS
its evident intent on REALISTIC, in-domain inputs (e.g. is_even returns True for 3;
a 'rows migrated' count that overcounts on ordinary rows). These are real bugs —
approve them with confidence.

Decide on the merits, not a quota. Answer INVALID only when the proof clearly matches
one of the three artefact patterns above. Do NOT reject a genuine defect out of excess
caution, and do NOT approve an artefact to seem helpful. A clear contract violation on
ordinary input is always VALID; an out-of-domain crash or design opinion is always
INVALID."""

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
        "intent": {"type": "string"},
        "problem": {"type": "string"},
        "rank": {"type": "integer"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low", "none"]},
        "why_it_matters": {"type": "string"},
    },
    "required": ["intent", "problem", "rank", "confidence", "why_it_matters"],
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
                       confidence=d["confidence"], why_it_matters=d["why_it_matters"],
                       intent=d.get("intent", ""))

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
