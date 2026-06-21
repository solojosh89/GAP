"""GAP web interface -- Floor 1 intake UI.

Single page: drop a file, pick your level, get one real problem + proof + fix.
No accounts, no scores, no dashboard.

    python app.py
"""
from __future__ import annotations
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).parent / ".env")

from flask import Flask, render_template, request

from gap.engine import StubEngine
from gap.pipeline import run
from gap.store import Store

BASE = Path(__file__).parent
DB_PATH = str(BASE / "gap.db")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024  # 100 KB -- no giant files


def _make_engine():
    """Real LLM engine when a key is configured (BYOK, used transiently, never
    stored); StubEngine otherwise so the app still runs offline. Set:
        GAP_LLM_API_KEY  (required for the real engine)
        GAP_LLM_BASE_URL (default Kimi; e.g. Groq: https://api.groq.com/openai/v1)
        GAP_LLM_MODEL    (e.g. openai/gpt-oss-120b on Groq)
    """
    if os.environ.get("GAP_LLM_API_KEY"):
        from gap.openai_engine import OpenAICompatEngine
        eng = OpenAICompatEngine()
        print(f"[GAP] LLM engine active: {eng.model} @ {eng.base_url}")
        return eng
    print("[GAP] No GAP_LLM_API_KEY set -> StubEngine (offline demo: only the "
          "migrate example is recognised). Set a key for the real find->prove->"
          "adjudicate->fix engine.")
    return StubEngine()


_store = Store(DB_PATH)
_engine = _make_engine()

LEVELS = ["simple", "normal", "expert"]


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template("index.html", result=None, level="simple")

    level = request.form.get("level", "simple")
    if level not in LEVELS:
        level = "simple"

    # Two ways in: upload a file, OR paste code straight into the box. A file (if
    # present) wins; otherwise we treat the pasted text as the submission.
    uploaded = request.files.get("code_file")
    pasted = (request.form.get("code_text") or "").strip()
    filename = "pasted.py"
    if uploaded and uploaded.filename:
        try:
            code = uploaded.read().decode("utf-8", errors="replace")
        except Exception:
            return render_template("index.html", result=None, level=level,
                                   error="Could not read that file. Is it a text file?")
        filename = uploaded.filename
    elif pasted:
        code = pasted
    else:
        return render_template("index.html", result=None, level=level,
                               error="Paste some code, or choose a file.")

    try:
        outcome = run(code, "python", _engine, _store, user_level=level)
    except RuntimeError as e:
        msg = str(e)
        if "429" in msg:
            return render_template("index.html", result=None, level=level,
                                   error="The AI model is rate-limited. Wait 15 seconds and try again.")
        return render_template("index.html", result=None, level=level,
                               error=f"Engine error: {msg[:200]}")
    return render_template("index.html", result=outcome, level=level,
                           filename=filename, original_code=code)


@app.route("/decide", methods=["POST"])
def decide():
    """Record whether the user took the fix. This is the seed of the across-time
    loop (Floor 2): we keep what was offered and whether it was accepted."""
    try:
        fix_id = int(request.form.get("fix_id", ""))
    except (TypeError, ValueError):
        return render_template("index.html", result=None, level="simple",
                               error="Bad fix id."), 400

    choice = request.form.get("choice")
    if choice not in ("accept", "reject"):
        return render_template("index.html", result=None, level="simple",
                               error="Bad choice."), 400

    accepted = 1 if choice == "accept" else -1
    ok = _store.set_fix_accepted(fix_id, accepted)
    decided = choice if ok else None
    # Pass the fixed code (and original, for a real diff) back to the UI
    fixed_code    = request.form.get("fixed_code", "")
    lesson        = request.form.get("lesson", "")
    explanation   = request.form.get("explanation", "")
    original_code = request.form.get("original_code", "")
    diff_html = _build_diff(original_code, fixed_code) if (decided == "accept" and fixed_code) else ""
    return render_template("index.html", result=None, level="simple",
                           decided=decided,
                           fixed_code=fixed_code,
                           lesson=lesson,
                           explanation=explanation,
                           diff_html=diff_html)


@app.route("/experiment_result", methods=["POST"])
def experiment_result():
    """Record what the user found when they RAN the experiment for a flagged-but-
    unproven finding: 'real' (it was a bug) or 'fine' (it held up). First real data
    into the across-time/outcome loop (Floor 2) — the seed of honest calibration."""
    try:
        finding_id = int(request.form.get("finding_id", ""))
    except (TypeError, ValueError):
        return render_template("index.html", result=None, level="simple",
                               error="Bad finding id."), 400
    result = request.form.get("result")
    if result not in ("real", "fine"):
        return render_template("index.html", result=None, level="simple",
                               error="Bad result."), 400
    _store.add_outcome(finding_id, result)
    return render_template("index.html", result=None, level="simple",
                           experiment_recorded=result)


def _build_diff(original: str, fixed: str) -> str:
    """Line-level diff, rendered as simple HTML spans. No external dependency —
    difflib is stdlib. Unchanged lines are dimmed; only the changed lines stand
    out, so the user's eye goes straight to what GAP actually touched."""
    import difflib
    import html as _html
    out = []
    sm = difflib.SequenceMatcher(None, original.splitlines(), fixed.splitlines())
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for line in original.splitlines()[i1:i2]:
                out.append(f'<div class="diff-line diff-equal">  {_html.escape(line)}</div>')
        elif tag == "delete":
            for line in original.splitlines()[i1:i2]:
                out.append(f'<div class="diff-line diff-del">- {_html.escape(line)}</div>')
        elif tag == "insert":
            for line in fixed.splitlines()[j1:j2]:
                out.append(f'<div class="diff-line diff-add">+ {_html.escape(line)}</div>')
        elif tag == "replace":
            for line in original.splitlines()[i1:i2]:
                out.append(f'<div class="diff-line diff-del">- {_html.escape(line)}</div>')
            for line in fixed.splitlines()[j1:j2]:
                out.append(f'<div class="diff-line diff-add">+ {_html.escape(line)}</div>')
    return "\n".join(out)


if __name__ == "__main__":
    # NOTE: use_reloader=False is deliberate here. On this Windows setup the
    # stat-reloader was spuriously detecting changes in CPython's own stdlib
    # files (threading.py, subprocess.py) and restarting mid-request, which
    # surfaced as a silent reader-thread crash. Debug mode (tracebacks in
    # browser) stays on; only the auto-restart-on-file-change is off.
    # Restart manually (Ctrl+C, rerun) after editing source files.
    app.run(debug=True, port=5000, use_reloader=False)
