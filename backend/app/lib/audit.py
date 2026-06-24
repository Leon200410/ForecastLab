"""Lightweight append-only audit trail (C5) — who did what, when.

For an internal team tool: records user + action + target to data_dir/audit.jsonl
so forecasts / bets / reviews are attributable, without any DB schema change.
Readable via GET /api/audit. Failures are swallowed — auditing must never break
the request it's logging.
"""
import json

from ..config import settings
from .util import now_iso


def _path():
    return settings.data_dir / "audit.jsonl"


def record(user: str, action: str, target: str = "") -> None:
    try:
        with open(_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": now_iso(), "user": user, "action": action,
                                "target": target}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def recent(limit: int = 100) -> list[dict]:
    try:
        with open(_path(), encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return []
    out: list[dict] = []
    for ln in lines[-limit:]:
        try:
            out.append(json.loads(ln))
        except ValueError:
            pass
    return list(reversed(out))  # newest first
