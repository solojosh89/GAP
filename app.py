"""GAP web interface -- Floor 1 intake UI.

Single page: drop a file, pick your level, get one real problem + proof + fix.
No accounts, no scores, no dashboard.

    python app.py
"""
from __future__ import annotations
from pathlib import Path

from flask import Flask, render_template, request

from gap.engine import StubEngine
from gap.pipeline import run
from gap.store import Store

BASE = Path(__file__).parent
DB_PATH = str(BASE / "gap.db")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024  # 100 KB -- no giant files

_store = Store(DB_PATH)
_engine = StubEngine()

LEVELS = ["simple", "normal", "expert"]


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template("index.html", result=None, level="simple")

    level = request.form.get("level", "simple")
    if level not in LEVELS:
        level = "simple"

    uploaded = request.files.get("code_file")
    if not uploaded or not uploaded.filename:
        return render_template("index.html", result=None, level=level,
                               error="Please choose a file.")

    try:
        code = uploaded.read().decode("utf-8", errors="replace")
    except Exception:
        return render_template("index.html", result=None, level=level,
                               error="Could not read that file. Is it a text file?")

    outcome = run(code, "python", _engine, _store, user_level=level)
    return render_template("index.html", result=outcome, level=level,
                           filename=uploaded.filename)


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
    return render_template("index.html", result=None, level="simple",
                           decided=decided)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
