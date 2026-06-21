"""GAP command-line scanner — point it at a file OR a whole project.

    python -m gap path/to/file.py            # scan one file
    python -m gap path/to/project            # scan a project (its .py files)
    python -m gap project --max-files 40 --spacing 4 --level expert

Runs the SAME find -> prove -> adjudicate -> fix pipeline per file as the web app.
It is HONEST about its limits: this is SINGLE-FILE analysis — it does NOT yet catch
cross-file bugs (a caller breaking another file's contract). It shows the ONE top
problem per file, proven by running, or says plainly it couldn't prove it.

BYOK: set GAP_LLM_API_KEY (a FREE Groq or Gemini key works). Your code and your key
stay local — nothing is uploaded anywhere except the LLM call you authorise. With no
key, GAP runs the offline demo engine (which only recognises the bundled migrate
example), so set a key to scan real code.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

try:  # .env is a convenience; the CLI works fine with plain environment variables.
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass

from gap.pipeline import run
from gap.store import Store

# Directories that are never the user's own code worth scanning.
SKIP_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "env", "node_modules", "build", "dist",
    ".idea", ".vscode", ".mypy_cache", ".pytest_cache", "site-packages", ".tox", ".eggs",
}
MAX_BYTES = 100_000  # skip files too big for the 100KB intake cap


def _make_engine():
    """Same selection as the web app: real LLM engine when a key is set (BYOK,
    transient), else the offline stub. Kept inline so the CLI doesn't depend on app.py."""
    if os.environ.get("GAP_LLM_API_KEY"):
        from gap.openai_engine import OpenAICompatEngine
        return OpenAICompatEngine()
    from gap.engine import StubEngine
    return StubEngine()


def _gather(target: Path, ext: str) -> list[Path]:
    if target.is_file():
        return [target]
    out = []
    for f in sorted(target.rglob(f"*{ext}")):
        if any(part in SKIP_DIRS for part in f.parts):
            continue
        try:
            if f.stat().st_size > MAX_BYTES:
                continue
        except OSError:
            continue
        out.append(f)
    return out


def main():
    ap = argparse.ArgumentParser(
        prog="python -m gap",
        description="GAP — find ONE real problem per file, PROVE it by running, offer a fix.",
    )
    ap.add_argument("path", help="a source file or a project directory")
    ap.add_argument("--ext", default=".py", help="file extension to scan (default .py)")
    ap.add_argument("--max-files", type=int, default=25,
                    help="cap files scanned (default 25; free LLM tiers rate-limit fast)")
    ap.add_argument("--level", default="normal", choices=["simple", "normal", "expert"])
    ap.add_argument("--spacing", type=float,
                    default=float(os.environ.get("GAP_EVAL_SPACING", "2")),
                    help="seconds between files; raise to 6-10 if you hit rate limits")
    args = ap.parse_args()

    # Don't let a stray unicode char (em dash, etc.) crash output on a Windows cp1252
    # console — same fix as the eval. Tolerant beats pretty.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    target = Path(args.path)
    if not target.exists():
        sys.exit(f"path not found: {target}")

    engine = _make_engine()
    from gap.engine import StubEngine
    if isinstance(engine, StubEngine):
        print("[GAP] No GAP_LLM_API_KEY set -> offline DEMO engine (recognises only the bundled\n"
              "      migrate example). Set a free Groq/Gemini key to scan real code — see QUICKSTART.md.\n")
    store = Store(":memory:")

    found = _gather(target, args.ext)
    if not found:
        sys.exit(f"no {args.ext} files found under {target}")
    files = found[:args.max_files]
    if len(found) > len(files):
        print(f"[GAP] {len(found)} files found; scanning the first {len(files)} "
              f"(raise --max-files for more).\n")

    proven, flagged, clean, voided = [], [], [], []
    for i, f in enumerate(files):
        if i and not isinstance(engine, StubEngine):
            time.sleep(args.spacing)  # don't burst a free-tier rate limit
        rel = f.relative_to(target) if target.is_dir() else f.name
        code = f.read_text(encoding="utf-8", errors="replace")
        try:
            out = run(code, "python", engine, store, user_level=args.level)
        except Exception as e:
            voided.append((rel, str(e)[:70]))
            print(f"  [skipped] {rel}  ({str(e)[:50]})")
            continue
        if out.proven:
            proven.append((rel, out))
            print(f"  [PROVED]  {rel}")
        elif out.finding.confidence == "none":
            clean.append(rel)
            print(f"  [clean]   {rel}")
        else:
            flagged.append((rel, out))
            print(f"  [flagged] {rel}  (suspected, not proven)")

    # ---- detail on the problems worth acting on ----
    if proven:
        print("\n" + "=" * 72)
        print("PROVEN PROBLEMS (GAP ran your code and demonstrated each one):")
        for rel, out in proven:
            print(f"\n  {rel}")
            print(f"    {out.finding.problem}")
            print(f"    proof: {(out.proof_detail or '').strip()[:90]}")
            if out.fix_offered and out.fix:
                print(f"    fix (re-proved, nothing broke): {out.fix.explanation}")
            elif out.notes:
                print(f"    fix withheld: {out.notes[:80]}")

    if flagged:
        print("\n" + "-" * 72)
        print("FLAGGED, NOT PROVEN (GAP suspects these but couldn't demonstrate them):")
        for rel, out in flagged:
            print(f"  {rel}: {out.finding.problem[:90]}")

    # ---- the standing project-level sweep: what GAP did NOT check ----
    print("\n" + "=" * 72)
    print(f"Scanned {len(files)} file(s): {len(proven)} proven, {len(flagged)} flagged, "
          f"{len(clean)} clean, {len(voided)} skipped.")
    print("\nWhat GAP did NOT check — so silence is never read as 'all clear':")
    print("  - CROSS-FILE bugs (a caller breaking another file's contract): GAP analyses")
    print("    each file ALONE. This is single-file analysis.")
    print("  - Files over 100KB, non-" + args.ext + " files, and anything in build/vendor dirs.")
    print("  - It shows the ONE top problem per file, not every problem.")
    if voided:
        print(f"  - {len(voided)} file(s) were SKIPPED (rate limit / error) — NOT checked, NOT 'clean'.")
        print("    Raise --spacing or lower --max-files and re-run those.")
    print("=" * 72)

    # Non-zero exit if anything was proven, so this can gate CI later.
    sys.exit(1 if proven else 0)


if __name__ == "__main__":
    main()
