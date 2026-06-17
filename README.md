# GAP — Floor 1 walking skeleton

GAP (Guided Architectural Practice): you drop in code, it finds ONE real problem,
**proves** it's real by running it, **fixes** it, **re-proves** the fix, and records
everything. No score. No radar. Plain by default.

This folder is the **proven skeleton** — the whole loop working once, end to end, on
one Python file, with no UI. Built by Opus as the load-bearing first slice.

## What works right now (proven, not just written)
`find -> prove -> fix -> re-prove -> record`, demonstrated on `examples/buggy_migrate.py`
(a database-free stand-in for the real E-school 'rows migrated' count bug).

- A finding is only **asserted** if its proof actually runs and shows the bug.
- A fix is only **offered** if re-running the proof shows the bug gone AND a smoke
  check shows nothing broke (do-no-harm gate).
- Every finding / proof / fix is written to the data model and reads back
  (`outcome` table exists but stays empty — that's Floor 2, the across-time loop).
- The sandbox **contains** runaway and crashing code (proven by the safety test).

## Run it
```
python run_skeleton.py                # the full loop on the bundled example
python tests/test_sandbox_safety.py   # proves the sandbox contains runaway code
```

## Honest limits (NOT done — flagged on purpose, not hidden)
- **Engine is a STUB.** `gap/engine.py` hard-codes the finding/proof/fix for the
  example. The real Claude-backed engine implements the same `Engine` interface and
  drops into the same pipeline. This boundary is intentional.
- **Sandbox containment (proven by `tests/test_sandbox_safety.py`):** time limit,
  whole-process-tree kill (no orphans), per-process memory cap, and active-process
  cap (fork bombs) — via a Windows Job Object, with a POSIX process-group + rlimit
  fallback. It still does **NOT** jail the filesystem or network: a script can read,
  write, or delete files it has rights to, and open sockets. True fs/network
  isolation needs an OS-level jail (Windows AppContainer, a container, or a separate
  low-privilege user) — that is the remaining hardening job, and why `app.py` binds
  to localhost only.
- One language (Python), one finding. UI exists (drop file + level dial); no
  accept/reject on fixes yet, and `Fix.explanation` does not yet "teach one notch".

## Architecture map
- `gap/contract.py` — the shapes both engines speak (Finding, Proof, Fix, RunResult).
- `gap/sandbox.py` — runs a script in isolation with a hard timeout.
- `gap/store.py` — sqlite, six tables, rated for 5 floors.
- `gap/engine.py` — the Engine interface + StubEngine.
- `gap/pipeline.py` — orchestrates the loop and the two safety gates.
- `run_skeleton.py` — entry point.

## HANDOFF — what Sonnet picks up next
Opus's slice ends here (skeleton proven). Sonnet takes the **mechanism / breadth**:
1. **Real engine** behind the `Engine` interface — wire `gap/engine.py` to the Claude
   API (Opus 4.8 for the find/prove/fix reasoning, per the model rule), returning the
   same `Finding/Proof/Fix` objects. Keep `StubEngine` for offline tests.
2. **Intake UI** — a page to drop a file + the level dial (simple/normal/expert).
   The dial only changes how output is phrased; it is never a grade.
3. **More languages** beyond Python (a proof + smoke runner per language).
4. **'Teach, don't just patch'** — fill `Fix.explanation` so the user grows one notch
   and needs GAP less over time, not more.
5. Persist the store to a real DB file; accept/reject on fixes.

Do NOT start the team layer, scores, or the across-time loop — those are later floors.
