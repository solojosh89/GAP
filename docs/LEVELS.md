# GAP explanation tiers — the dial spec

This locks the judgment (the *voices*) so the wiring is mechanical. Sonnet builds
from this; no design decisions are left.

## What the dial is (and is NOT)

The dial is a **volume knob for how GAP explains the SAME proven finding** — never a
grade GAP assigns to you, never stored as judgment, never shown to anyone, changeable
any time (re-run at a different setting). It changes *how much evidence is disclosed*.
It never changes what GAP finds or how hard it judges.

Label it as a preference, not an identity: **"How should I explain it?"** — each option
names the tier *and* a plain "you'll get…" line, so picking it is a choice about
disclosure depth, not a statement about the user. (Guards against the Dunning-Kruger
self-miscategorization: someone unsure picks by what they *want to see*, not by ranking
themselves.)

## The one rule: a DISCLOSURE LADDER (anti-theatre)

Each tier reveals **exactly one more real layer** than the tier below. If two settings
would render the same thing with different labels, that's theatre — collapse them. Every
rung must genuinely differ.

```
1 Vibe coder  plain truth + analogy + one safe choice           (no evidence, no code)
2 Beginner    + the proof RESULT in plain words                 ("I ran it: said 5, only 2 saved")
3 Amateur     + the actual fix CODE you can paste
4 Junior      + the WHY (lesson) and the sweep ("what I didn't check")
5 Senior      + the raw proof SCRIPT and tradeoffs, terse       (no hand-holding)
```

## Per-tier content (exact)

**1 — Vibe coder · "Just tell me."**  *(already built — the current "Simple")*
- `Finding.plain` (one jargon-free sentence) + `Finding.analogy` (homely picture).
- One safe choice: **Yes, fix it / Not now** → `/decide` (the accept/reject buttons).
- Caveat: the warm one-liner ("one real problem found, not all clean — there may be more,
  and I can't yet tell if it'll break months from now").
- Hidden behind "Show me the details": everything below.

**2 — Beginner · "Show me it's real."** = tier 1 **+ the proof result, in plain words.**
- Add one plain sentence rendering the proof: *"I ran your code — it reported 5 saved, but
  only 2 actually saved."* This is `Proof` phrased plainly — **NOT** the raw
  `GAP_PROOF:BUG_PRESENT reported=5 actual=2` marker.
- Still no code, no proof script. Same buttons, same caveat.
- *(Needs the plain proof line — see "One field to add" below.)*

**3 — Amateur · "Give me the fix."** = tier 2 **+ the fix code.**
- Add `Fix.fixed_code` in a copyable box + `Fix.explanation` (one plain line of what changed).
- Still no proof script, no tradeoffs.

**4 — Junior · "Explain the why."** = tier 3 **+ the lesson and the sweep.**
- Add `Fix.lesson` (teach-one-notch) and the **sweep panel** ("What I did NOT check").
- Plain developer language; may reference the changed line by name.

**5 — Senior · "Full detail."** = tier 4 **+ the proof script and tradeoffs, terse.**
- Add the raw proof script (`Proof.script`) and terse, line-cited framing. Raw
  `GAP_PROOF` markers are fine here. Minimal hand-holding.

## Field → tier map (so wiring is pure mechanism)

| field shown                         | 1 | 2 | 3 | 4 | 5 |
|-------------------------------------|---|---|---|---|---|
| `finding.plain` + `finding.analogy` | ✓ | ✓ | ✓ |   |   |
| `finding.problem` (dev wording)     |   |   |   | ✓ | ✓ |
| proof result, **plain words**       |   | ✓ | ✓ | ✓ |   |
| proof result, **raw marker**        |   |   |   |   | ✓ |
| `fix.fixed_code`                    |   |   | ✓ | ✓ | ✓ |
| `fix.explanation`                   |   |   | ✓ | ✓ | ✓ |
| `fix.lesson` (teach)                |   |   |   | ✓ | ✓ |
| sweep panel                         |   |   |   | ✓ | ✓ |
| `proof.script` (raw)                |   |   |   |   | ✓ |
| Yes-fix-it / Not-now buttons        | ✓ | ✓ | ✓ | ✓ | ✓ |
| caveat: warm one-liner / terse      | w | w | w | t | t |

Tiers 1–3 are the "plain" voices (no dev jargon, friendly framing); 4–5 are the developer
voices. The accept/reject choice exists at every tier — taking the fix is always a safe,
one-click action regardless of how much you read.

## One field to add (Sonnet)

Tier 2 needs the proof result in plain words. Cheapest honest path: the engine produces it.
Add `Proof.plain_result: str = ""`. For the StubEngine's migrate finding, set:

> `plain_result = "I ran your code — it reported 5 items saved, but only 2 actually saved."`

The RealEngine fills it from the same call that writes the proof. If empty, tier 2 falls back
to tier 1 (degrade gracefully, never show the raw marker at a plain tier).

## Wiring checklist (Sonnet)

1. Intake form: 3 radios → 5 (`vibe`, `beginner`, `amateur`, `junior`, `senior`), each with
   its "you'll get…" line. Keep `app.py` LEVELS list + validation in sync.
2. Result card: branch on the 5 values per the field→tier map. Reuse the current Simple
   block verbatim for tier 1. Build 2–5 by progressive disclosure — never duplicate a tier.
3. Add `Proof.plain_result` (above); render it at tiers 2–4; raw marker only at 5.
4. The level only changes display — the engine already produces every field; do not branch
   engine logic on level.
