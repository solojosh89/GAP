# GAP Engine Spec

The blueprint for the real find→prove→fix engine. Written so that **the Claude API
key is the only remaining gate** — when it arrives, wiring is mechanical.

Grounded in two real worked examples we proved by hand (see `## Corpus`).

---

## The one rule

**Prove, never assert.** The engine may only claim a problem it can *demonstrate*
by running code. If it can't build a runnable demonstration that needs no expertise
to trust, it returns `confidence: "none"` and says so. A false finding is more
dangerous than no finding — the user (often a vibe coder) will act on it.

This rule is enforced twice over: the engine is *told* to obey it, and the
**pipeline's prove-gate enforces it mechanically** — a finding is only surfaced if
its proof script actually prints `GAP_PROOF:BUG_PRESENT`. The engine cannot lie its
way past a running sandbox.

---

## Interface (unchanged)

The real engine implements the exact `Engine` interface the `StubEngine` already
satisfies, so it drops into the same `pipeline.run()`:

```
find(code, language)  -> Finding(problem, rank, confidence, why_it_matters)
prove(code, finding)  -> Proof(script, language)
fix(code, finding)    -> Fix(fixed_code, explanation, lesson)
```

Implementation: [`gap/real_engine.py`](../gap/real_engine.py) — one Claude call per
method, structured outputs guaranteeing the shapes.

**Model rule:** judgment runs on **Opus 4.8** (`claude-opus-4-8`) with adaptive
thinking at `effort: high`. Judgment is the crown jewel — it is not economised onto
a cheaper model. Mechanism (UI, CRUD, parsing, runners) is Sonnet's lane.

---

## The three calls

Each is a single structured-output call. Full prompts live in `gap/real_engine.py`;
the essence:

1. **find** — name the ONE most dangerous real problem; rank by danger; prefer
   problems in *pure, extractable logic* (provable) over ones needing a live
   DB/network/framework (flag-only). Return `confidence: "none"` honestly if none.
2. **prove** — write a self-contained script that prints `GAP_PROOF:BUG_PRESENT` or
   `GAP_PROOF:BUG_ABSENT` from *observed behaviour*. For a framework file, **extract
   the pure function under test verbatim** into the script (no DOM/runtime needed).
   Declare `language` (`python` | `node`).
3. **fix** — the minimal change that removes the proven bug and breaks nothing
   (Chesterton's Fence on the user's code). Plus `explanation` (what changed) and
   `lesson` (the pattern — teach one notch so the user needs GAP less over time).

---

## Per-language runners (the Gate Test #2 requirement)

Gate Test #2 proved a real JS bug the Python-only sandbox could not run. So a proof
runs in the language it was written for. [`gap/runners.py`](../gap/runners.py) maps
a language to its entry filename, argv prefix, and target filename. The sandbox's
containment (timeout, process-tree kill, memory cap) is language-agnostic and
unchanged — only the command and filenames vary.

Supported today: `python`, `node`. Adding a language = one registry entry + a smoke
template.

---

## Extraction step

The highest-value provable bugs tend to live in pure functions buried inside
framework files (the JS bug was in a module-top `analyzeEmotionalPatterns`, not the
JSX). The prove step must lift that function out verbatim and exercise it directly.
This is a prompt instruction now; if extraction proves unreliable, promote it to a
separate engine call (`extract(code, finding) -> pure_snippet`) before `prove`.

---

## Corpus (the two proven examples — regression tests + few-shot)

Both were found, proven by running, and fixed by hand. They are the engine's
ground-truth anchors and belong in an eval set the real engine must still pass.

| # | Bug | Language | Proof verdict | Fix |
|---|-----|----------|---------------|-----|
| 1 | `migrate()` counts attempts, not inserts (`migrated += 1` outside the `if`) | python | reported=5 actual=2 | move `+= 1` inside the `if` |
| 2 | `analyzeEmotionalPatterns` sentinel baseline `1` → fabricated "175x" multiplier | node | reported=175 == raw avg 175 | skip when no neutral-mood baseline |

Bug class shared by both: **a value that looks plausible but is computed wrong** —
a count that counts the wrong thing; a "multiplier" that is really a dollar average.
The lesson the engine teaches is the gut-check that catches the class.

---

## Remaining mechanical wiring (Sonnet, once the key is available)

Everything below is plumbing — no new judgment:

1. `pip install anthropic`; set `ANTHROPIC_API_KEY`; swap `StubEngine()` for
   `RealEngine()` in `app.py` (keep the stub for offline tests).
2. **Route the sandbox by `Proof.language`** — `pipeline.run()` and `sandbox.run_script`
   currently hard-code Python. Use `gap/runners.py`: write the script to
   `runners.entry_name(lang)`, the code to `runners.target_name(lang)`, run
   `runners.argv(lang) + [entry]`. The containment layer does not change.
3. **Per-language smoke templates** — the do-no-harm `SMOKE` check in `pipeline.py`
   is Python-specific; add a node equivalent, keyed by language.
4. **fs/network jail** — becomes MANDATORY the moment `RealEngine` runs submitted
   code (see `sandbox.py` honest limits). Until then, `app.py` stays localhost-only.
5. Turn the corpus above into an automated eval the real engine must pass.

When 1–3 are done, GAP runs find→prove→fix on unseen code in any supported
language, end to end. That is Floor 1 complete.
