# GAP — 2-minute quickstart

GAP points at your code, finds **one real problem**, **proves it by running it**
(so you don't have to trust the AI), and offers a fix it has re-run to confirm.
Its rule: never claim a bug it can't demonstrate.

## Run it on your own project

**1. Get a FREE API key** (no card needed) — either works:

| Provider | Key | `GAP_LLM_BASE_URL` | `GAP_LLM_MODEL` |
|---|---|---|---|
| Groq | https://console.groq.com | `https://api.groq.com/openai/v1` | `openai/gpt-oss-120b` |
| Gemini | https://aistudio.google.com/apikey | `https://generativelanguage.googleapis.com/v1beta/openai` | `gemini-2.5-flash` |

**2. Set it.** Your key is used only for the call — GAP never stores it. Either export it, or put it in a `.env` file in the repo root:

```
GAP_LLM_API_KEY=your_key_here
GAP_LLM_BASE_URL=https://api.groq.com/openai/v1
GAP_LLM_MODEL=openai/gpt-oss-120b
```

PowerShell: `$env:GAP_LLM_API_KEY="..."` etc.

**3. Scan.** (Only dependency is `python-dotenv`, and only if you use a `.env` file — the engine itself is stdlib.)

```
pip install python-dotenv
python -m gap path/to/one_file.py        # a single file
python -m gap path/to/your/project       # a whole project (its .py files)
```

Useful flags: `--max-files 40` (default 25), `--spacing 6` (raise if you hit rate limits), `--level simple|normal|expert`.

## What you'll get

- Per file: one real problem **proved by running it** — or an honest "flagged, couldn't prove it."
- For proven problems: a fix that's been **re-run to confirm** it removes the bug and breaks nothing.
- A footer listing **what GAP did NOT check** — so silence is never "all clear."

## Honest limits (so you can judge it fairly)

- **Single-file analysis.** It does NOT yet catch cross-file bugs (a caller breaking another file's contract).
- **Free tiers rate-limit.** If you see `skipped`, raise `--spacing` or lower `--max-files` and re-run. A `skipped` file was **not** checked — it is not "clean."
- It shows the **one** top problem per file, not every problem.

## The only thing I'm actually asking

After you run it on real code: **did it tell you something *true* that you couldn't already see?**

That's the one question that matters — not whether it felt useful, but whether it was *right*. A blunt "no" is more valuable to me than a polite "nice."
