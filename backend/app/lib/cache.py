"""Disk cache for expensive/external calls (search, fetch, LLM).

Keyed by sha256 of the parts. Stores JSON. Prevents paying twice for the same
query/page/prompt (PRD §9). Best-effort: corrupt entries are ignored.
"""
import hashlib
import json
from typing import Any, Optional

from ..config import settings


def _path(parts: tuple) -> Any:
    key = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return settings.cache_dir / f"{key}.json"


def get_cached(*parts) -> Optional[Any]:
    p = _path(parts)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def set_cached(value: Any, *parts) -> None:
    try:
        _path(parts).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
