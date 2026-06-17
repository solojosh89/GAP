"""GAP data store (SPIKE) — sqlite, six tables, rated for 5 floors.

Floor 1 uses user/submission/finding/proof/fix. `outcome` exists now but stays
empty until Floor 2 (the across-time loop). Building it now is cheap; adding it
later would mean a migration.
"""
from __future__ import annotations
import hashlib
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS user (
    id INTEGER PRIMARY KEY,
    level_dial TEXT DEFAULT 'normal'
);
CREATE TABLE IF NOT EXISTS submission (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    code_hash TEXT,
    language TEXT,
    created_at REAL
);
CREATE TABLE IF NOT EXISTS finding (
    id INTEGER PRIMARY KEY,
    submission_id INTEGER,
    problem TEXT,
    rank INTEGER,
    confidence TEXT
);
CREATE TABLE IF NOT EXISTS proof (
    id INTEGER PRIMARY KEY,
    finding_id INTEGER,
    repro TEXT,
    ran_ok INTEGER          -- 1 = proof confirmed the bug is present
);
CREATE TABLE IF NOT EXISTS fix (
    id INTEGER PRIMARY KEY,
    finding_id INTEGER,
    diff TEXT,
    fix_proof_ok INTEGER,   -- 1 = after fix, proof confirmed bug is gone
    accepted INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS outcome (
    id INTEGER PRIMARY KEY,
    finding_id INTEGER,
    held_or_broke TEXT,     -- Floor 2 (across-time loop): empty for now
    created_at REAL
);
"""


class Store:
    def __init__(self, path: str = ":memory:"):
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def add_user(self, level_dial: str = "normal") -> int:
        cur = self.conn.execute("INSERT INTO user (level_dial) VALUES (?)", (level_dial,))
        self.conn.commit()
        return cur.lastrowid

    def add_submission(self, user_id: int, code: str, language: str) -> int:
        h = hashlib.sha256(code.encode("utf-8")).hexdigest()
        cur = self.conn.execute(
            "INSERT INTO submission (user_id, code_hash, language, created_at) VALUES (?,?,?,?)",
            (user_id, h, language, time.time()),
        )
        self.conn.commit()
        return cur.lastrowid

    def add_finding(self, submission_id: int, problem: str, rank: int, confidence: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO finding (submission_id, problem, rank, confidence) VALUES (?,?,?,?)",
            (submission_id, problem, rank, confidence),
        )
        self.conn.commit()
        return cur.lastrowid

    def add_proof(self, finding_id: int, repro: str, ran_ok: bool) -> int:
        cur = self.conn.execute(
            "INSERT INTO proof (finding_id, repro, ran_ok) VALUES (?,?,?)",
            (finding_id, repro, 1 if ran_ok else 0),
        )
        self.conn.commit()
        return cur.lastrowid

    def add_fix(self, finding_id: int, diff: str, fix_proof_ok: bool, accepted: int = 0) -> int:
        cur = self.conn.execute(
            "INSERT INTO fix (finding_id, diff, fix_proof_ok, accepted) VALUES (?,?,?,?)",
            (finding_id, diff, 1 if fix_proof_ok else 0, accepted),
        )
        self.conn.commit()
        return cur.lastrowid

    def full_record(self, submission_id: int) -> dict:
        """Read back a complete run — proves the data model round-trips."""
        c = self.conn
        sub = c.execute("SELECT * FROM submission WHERE id=?", (submission_id,)).fetchone()
        finds = c.execute("SELECT * FROM finding WHERE submission_id=?", (submission_id,)).fetchall()
        out = {"submission": sub, "findings": []}
        for f in finds:
            fid = f[0]
            proofs = c.execute("SELECT * FROM proof WHERE finding_id=?", (fid,)).fetchall()
            fixes = c.execute("SELECT * FROM fix WHERE finding_id=?", (fid,)).fetchall()
            out["findings"].append({"finding": f, "proofs": proofs, "fixes": fixes})
        return out
