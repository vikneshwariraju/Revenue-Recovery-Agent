"""Audit log + duplicate-action lock, backed by SQLite (no server needed).

Two tables:
  decisions : one row per decision (what the LLM said, what code finally did, why)
  actions   : one row per payment, UNIQUE(payment_id). This is the lock that
              stops the same payment from being acted on twice.
"""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import List

from app.schemas import Decision, FailedPayment

DEFAULT_DB = os.getenv("AUDIT_DB", "data/audit.db")


@contextmanager
def _conn(db_path: str):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db(db_path: str = DEFAULT_DB) -> None:
    with _conn(db_path) as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                payment_id TEXT NOT NULL,
                customer_id TEXT NOT NULL,
                amount_inr INTEGER NOT NULL,
                failure_reason TEXT NOT NULL,
                llm_action TEXT NOT NULL,
                llm_reason TEXT,
                llm_confidence REAL,
                final_action TEXT NOT NULL,
                delay_minutes INTEGER NOT NULL DEFAULT 0,
                overrides TEXT NOT NULL DEFAULT '[]'
            )"""
        )
        con.execute(
            """CREATE TABLE IF NOT EXISTS actions (
                payment_id TEXT PRIMARY KEY,
                action TEXT NOT NULL,
                claimed_at TEXT NOT NULL
            )"""
        )


def log_decision(payment: FailedPayment, llm: Decision, final: Decision,
                 overrides: List[str], db_path: str = DEFAULT_DB) -> None:
    with _conn(db_path) as con:
        con.execute(
            """INSERT INTO decisions
               (created_at, payment_id, customer_id, amount_inr, failure_reason,
                llm_action, llm_reason, llm_confidence, final_action,
                delay_minutes, overrides)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (datetime.now(timezone.utc).isoformat(), payment.payment_id,
             payment.customer_id, payment.amount_inr, payment.failure_reason,
             llm.action.value, llm.reason, llm.confidence, final.action.value,
             final.delay_minutes, json.dumps(overrides)),
        )


def claim_action(payment_id: str, action: str, db_path: str = DEFAULT_DB) -> bool:
    """Try to take the lock for this payment.
    True  -> first time, safe to execute the action.
    False -> already acted on, do NOT execute again."""
    with _conn(db_path) as con:
        cur = con.execute(
            "INSERT OR IGNORE INTO actions (payment_id, action, claimed_at) VALUES (?,?,?)",
            (payment_id, action, datetime.now(timezone.utc).isoformat()),
        )
        return cur.rowcount == 1


def has_action(payment_id: str, db_path: str = DEFAULT_DB) -> bool:
    """True if this payment was already acted on (cheap check, no LLM call needed)."""
    with _conn(db_path) as con:
        row = con.execute(
            "SELECT 1 FROM actions WHERE payment_id = ?", (payment_id,)
        ).fetchone()
    return row is not None


def get_log(limit: int = 100, db_path: str = DEFAULT_DB) -> List[dict]:
    with _conn(db_path) as con:
        rows = con.execute(
            "SELECT * FROM decisions ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["overrides"] = json.loads(d["overrides"])
        out.append(d)
    return out


def summary(db_path: str = DEFAULT_DB) -> dict:
    """Counts for the dashboard / README."""
    with _conn(db_path) as con:
        total = con.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        by_action = {
            r["final_action"]: r["n"]
            for r in con.execute(
                "SELECT final_action, COUNT(*) AS n FROM decisions GROUP BY final_action"
            )
        }
        overridden = con.execute(
            "SELECT COUNT(*) FROM decisions WHERE overrides != '[]'"
        ).fetchone()[0]
    return {"total": total, "by_action": by_action, "overridden_by_safety": overridden}