# GAP — Full Engineering Audit

**Date:** 2026-06-18
**Auditor:** Claude (Opus 4.8), by reading every source file and *running* the system.
**Rule honoured:** GAP's own — *prove, never assert.* Every claim below was verified by
running the code, not by trusting the README.

---

## TL;DR — what phase are we in?

> **Floor 1 (the walking skeleton → working product) is ~85% complete and its core
> thesis is VALIDATED on a free model. It is not yet hardened. Floor 2+ has not started.**

- The full loop **find → prove → adjudicate → fix → re-prove → record** runs end-to-end
  on real, unseen code via a free LLM (Groq `gpt-oss-120b`).
- GAP's #1 promise — **find real bugs, never invent them** — holds: **0 false positives
  across ~6 eval runs** with valid (importing) proofs.
- Recall is **strong but not flat 100%** (~80–100%, variance) — the honest, *safe*
  failure direction for this tool.
- Real remaining work is **hardening** (recall stability, fix-stage do-no-harm, an
  OS-level jail for untrusted code), not core design.

**Phase scorecard**

| Phase / Floor | Scope | Status |
|---|---|---|
| Floor 1 — single-file find→prove→fix, no across-time | the product's heart | **~85% — built + precision-validated, not hardened** |
| Floor 2 — across-time loop (does the fix hold later?) | outcome learning | **~5% — schema seeded, `outcome` table empty, `accept/reject` wired** |
| Floors 3–5 — teams, scores, breadth | later | **0% — not started (correctly deferred)** |

---

## 1. What GAP is

You drop in code; GAP finds **one** real problem, **proves it by running a
demonstration**, **fixes it**, **re-proves** the fix removed the bug without breaking
the file, and **records** everything. No score, no radar, plain by default. The
inviolable rule: *prove, never assert* — a false finding is worse than no finding,
because the user (often a "vibe coder") will act on it.

---

## 2. Component-by-component audit

Legend: ✅ proven by running · 🟡 built, partially verified · 🟠 stub/placeholder · 🔴 missing

| Component | File | Status | Notes |
|---|---|---|---|
| Contract (data shapes) | `gap/contract.py` | ✅ | Finding now carries `intent`. Clean, minimal. |
| Sandbox containment | `gap/sandbox.py` | ✅ | Time-limit, **whole process-tree kill**, memory cap, fork-bomb cap — all proven by `tests/test_sandbox_safety.py`. |
| Data store | `gap/store.py` | 🟡 | 6 tables, round-trips. Stores code as **sha256 hash** (privacy-good). **Gap: `intent` is not persisted** (Finding has it; `add_finding` drops it). `outcome` empty (Floor 2). |
| Stub engine | `gap/engine.py` | ✅ | Honestly refuses unknown code; only knows the migrate example. |
| Real engine (provider-agnostic) | `gap/openai_engine.py` | ✅ | Any OpenAI-compatible API (Kimi/Groq/OpenAI/local), stdlib-only HTTP, browser UA to clear Cloudflare 1010, BYOK-transient. **Run & validated on Groq gpt-oss-120b.** |
| Real engine (Anthropic) | `gap/real_engine.py` | 🟠 | Holds the single-source prompts (used by both engines). The Anthropic client path itself (`adaptive` thinking, `output_config.effort`, json_schema) is **written-from-spec, never executed** — verify vs live SDK before trusting. |
| Pipeline + gates | `gap/pipeline.py` | ✅ | Orchestrates the loop and all gates. Verified end-to-end. |
| Per-language runners | `gap/runners.py` | 🟠 | Exists for python/node, but pipeline still **hard-codes Python** (writes `target.py`, runs `python`). Node path unproven. |
| Intake UI | `app.py` + `templates/` | 🟡 | Flask page; **now wired to the real engine** (env-driven, falls back to stub). Localhost-only. Not load/UX tested. |
| Validation eval | `evals/` | ✅ | 10-sample corpus + scorer; honest VOID handling; gates CI via exit code. Run many times today. |

---

## 3. The gate stack (GAP's actual moat)

A finding only reaches the user if it survives **all** of these. This layered design is
the genuinely novel part — most "AI code review" tools have only step 4-ish.

1. **Contract gate (find)** — *prompt-level.* The engine must state the code's evident
   `intent`; only behaviour that violates that intent on in-domain inputs may be flagged.
   Kills "I dislike this design" and "I crashed it with garbage input" findings.
2. **Anti-inlining gate (pipeline)** — ✅ *mechanical.* A proof that doesn't `import target`
   is rejected — it tested a copy, not your code. (This caught real inlining today.)
3. **Prove gate (pipeline + sandbox)** — ✅ *mechanical.* The proof must actually print
   `GAP_PROOF:BUG_PRESENT` when run in the sandbox. The engine cannot talk its way past it.
4. **Adjudication gate (pipeline)** — *LLM-level.* An independent skeptical pass rejects
   out-of-domain / design-opinion / intended-behaviour "proofs." Fails toward rejection.
5. **Fix gates (pipeline)** — ✅ *mechanical.* The fix is offered only if re-running the
   proof shows `BUG_ABSENT` **and** a do-no-harm smoke passes.
- **Standing Sweep** — always discloses boundaries ("I showed ONE problem; here's what I
  could not check") so "all clear" is never implied.

**Honest note on the gates:** steps 1 and 4 are *judgment* (LLM), so they carry
variance; steps 2, 3, 5 are *mechanical* (deterministic). The mechanical gates are what
make the LLM gates safe — they're the floor under the judgment.

---

## 4. Validation evidence (run today, free Groq `gpt-oss-120b`)

| Metric | Result | Verdict |
|---|---|---|
| **Precision (no false alarms)** | **FP = 0 across ~6 runs** (20+ clean-code trials) | ✅ **Validated & stable** |
| **Recall (bugs caught)** | ~80–100%, varies (5/5 best runs, 4/5 some) | 🟡 Strong, not flat |
| Adjudicator caught a live false finding | `add` (string inputs) rejected in the act | ✅ Mechanism works |
| Anti-inlining caught real inlining | `add`, `safe_divide_documented` rejected | ✅ Mechanism works |

**Critical honesty:** an earlier "100% recall, 0 FP" result was **partly on invalid
proofs** — the model was inlining a copy of the code instead of importing it, so the
proofs were self-referential. Wiring into the app exposed this. After the fix, the
re-validation above used *valid* proofs. This is the audit's single most important
finding: **the eval that scored only find+prove masked a broken proof mechanism; only
running the fix stage revealed it.**

---

## 5. Honest limits & risks (not hidden — flagged)

### Security
- **Sandbox does NOT jail filesystem or network.** Submitted code can read/write/delete
  files it has rights to and open sockets. Mitigated only by **localhost-only** binding.
  🔴 **This becomes mandatory to fix the moment GAP runs untrusted code** (an OS-level
  jail: container / Windows AppContainer / low-priv user).
- BYOK keys are used transiently and never stored — ✅ correct. (Code is stored only as a
  hash.)

### Correctness / quality
- **Recall variance** — occasional missed bug, partly from LLM nondeterminism, partly
  from the adjudicator defaulting to *reject* when its API call is rate-limited.
- **Fix-stage do-no-harm is light** — currently only "the fixed file still imports."
  A per-finding *behavioural* smoke (assert intended behaviour on in-domain inputs) is
  not built. So a fix could pass while subtly changing unrelated behaviour.
- **`intent` is computed but not persisted** to the store.
- **Corpus is small** (10 samples). 20 clean trials is signal, not a benchmark.

### Breadth
- **Python only** in practice (node specced, not wired into the pipeline).
- **Anthropic engine path unexecuted** (spec-only).
- Free-tier **rate limits** (Groq 429s) are the dominant operational noise.

---

## 6. What is explicitly NOT done (and correctly so)

Floor 2+ is deferred by design — do not start until Floor 1 is hardened:
- The **across-time loop** (does a fix still hold months later? `outcome` table).
- Team layer, scores, radar — all later floors.
- `accept/reject` on fixes is *seeded* (`/decide` route + `fix.accepted`) but unused.

---

## 7. Prioritized next actions

**To finish hardening Floor 1 (in order):**
1. **Recall stability** — retry the adjudicator once before defaulting to reject; add
   light backoff/spacing for 429s.
2. **Behavioural do-no-harm** — engine-generated smoke (assert intended behaviour on
   in-domain inputs) so fixes are checked beyond "still imports."
3. **Persist `intent`** in `store.add_finding` (one column + one arg).
4. **Real multi-language** — route the sandbox by `Proof.language` via `runners.py`;
   prove the node path with one real JS bug.
5. **Expand the corpus** to ~40 (more clean traps + harder/contestable bugs); turn
   "passes on 10" into a number you can show people.

**Before exposing GAP to untrusted code (hard gate):**
6. **OS-level fs/network jail** for the sandbox.

**Then, and only then:**
7. Begin **Floor 2** (the across-time outcome loop).

---

## 8. Bottom line

GAP is **past the riskiest point**. The thing most likely to kill it — "can an LLM
find real bugs without inventing fake ones?" — has been answered **yes, on free
infrastructure**, with a layered gate design that is genuinely more disciplined than
typical AI code-review tools. What remains is **engineering, not invention**: harden
recall, jail the sandbox, broaden languages, grow the corpus.

This is not a prototype hoping to work. It is a validated Floor-1 system with a known,
honest punch-list. **Phase: late Floor 1 — validated, pre-hardening.**
