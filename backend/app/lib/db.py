"""Tiny SQLite JSON-document store.

Each collection is a table with a few indexed columns (for filtering) plus a JSON
blob holding the full pydantic-serialized object. Account is a singleton row.
Keeps deps to stdlib only; swap for SQLModel/Postgres later if needed.
"""
import json
import sqlite3
import threading
from typing import Optional

from ..config import settings

_lock = threading.Lock()

# collection -> extra indexed columns (besides id, created_at, data)
COLLECTIONS: dict[str, list[str]] = {
    "markets": ["status"],
    "forecasts": ["market_id", "status"],
    "bets": ["market_id", "forecast_id", "status"],
    "reviews": ["market_id", "forecast_id"],
}


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _lock, _conn() as c:
        for coll, cols in COLLECTIONS.items():
            extra = "".join(f", {col} TEXT" for col in cols)
            c.execute(
                f"CREATE TABLE IF NOT EXISTS {coll} "
                f"(id TEXT PRIMARY KEY, created_at TEXT{extra}, data TEXT)"
            )
        c.execute("CREATE TABLE IF NOT EXISTS account (id TEXT PRIMARY KEY, data TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS kb (id TEXT PRIMARY KEY, vector TEXT, payload TEXT)")
        c.commit()


def put(coll: str, obj: dict) -> None:
    cols = COLLECTIONS[coll]
    fields = ["id", "created_at", "data"] + cols
    vals = [obj["id"], obj.get("created_at"), json.dumps(obj)] + [obj.get(col) for col in cols]
    placeholders = ",".join(["?"] * len(fields))
    updates = ",".join(f"{f}=excluded.{f}" for f in fields if f != "id")
    with _lock, _conn() as c:
        c.execute(
            f"INSERT INTO {coll} ({','.join(fields)}) VALUES ({placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET {updates}",
            vals,
        )
        c.commit()


def get(coll: str, id: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute(f"SELECT data FROM {coll} WHERE id=?", (id,)).fetchone()
    return json.loads(row["data"]) if row else None


def list_all(coll: str, **filters) -> list[dict]:
    q = f"SELECT data FROM {coll}"
    where, vals = [], []
    for k, v in filters.items():
        if v is not None:
            where.append(f"{k}=?")
            vals.append(v)
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY created_at DESC"
    with _conn() as c:
        rows = c.execute(q, vals).fetchall()
    return [json.loads(r["data"]) for r in rows]


def delete(coll: str, id: str) -> None:
    with _lock, _conn() as c:
        c.execute(f"DELETE FROM {coll} WHERE id=?", (id,))
        c.commit()


def clear_all() -> None:
    """Wipe every collection + account + kb (used by scripts/reset.py)."""
    with _lock, _conn() as c:
        for coll in COLLECTIONS:
            c.execute(f"DELETE FROM {coll}")
        c.execute("DELETE FROM account")
        c.execute("DELETE FROM kb")
        c.commit()


def purge_legacy_mock() -> int:
    """Remove leftover demo/sample rows (ids like sample-* / demo-*) that older
    builds wrote into the DB. Real Polymarket ids are numeric, so this is safe."""
    removed = 0
    with _lock, _conn() as c:
        for pref in ("sample-%", "demo-%"):
            removed += c.execute("DELETE FROM markets WHERE id LIKE ?", (pref,)).rowcount
            for coll in ("forecasts", "bets", "reviews"):
                c.execute(f"DELETE FROM {coll} WHERE market_id LIKE ?", (pref,))
        c.commit()
    return removed


# ---- account singleton ------------------------------------------------------
def get_account() -> Optional[dict]:
    with _conn() as c:
        row = c.execute("SELECT data FROM account WHERE id='singleton'").fetchone()
    return json.loads(row["data"]) if row else None


def put_account(obj: dict) -> None:
    with _lock, _conn() as c:
        c.execute(
            "INSERT INTO account (id, data) VALUES ('singleton', ?) "
            "ON CONFLICT(id) DO UPDATE SET data=excluded.data",
            (json.dumps(obj),),
        )
        c.commit()


# ---- kb vector rows ---------------------------------------------------------
def kb_add(id: str, vector: list[float], payload: dict) -> None:
    with _lock, _conn() as c:
        c.execute(
            "INSERT INTO kb (id, vector, payload) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET vector=excluded.vector, payload=excluded.payload",
            (id, json.dumps(vector), json.dumps(payload)),
        )
        c.commit()


def kb_all() -> list[tuple[list[float], dict]]:
    with _conn() as c:
        rows = c.execute("SELECT vector, payload FROM kb").fetchall()
    return [(json.loads(r["vector"]), json.loads(r["payload"])) for r in rows]
