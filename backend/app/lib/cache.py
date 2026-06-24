"""Disk cache for expensive/external calls (search, fetch, LLM).

Keyed by sha256 of the parts. Stores JSON. Prevents paying twice for the same
query/page/prompt (PRD §9). Best-effort: corrupt entries are ignored. Tracks
hit/miss counts (surfaced as a cache hit-rate) and honours an optional TTL
(CACHE_TTL_HOURS, 0 = never expire) as a freshness/size guard.
"""
import hashlib
import json
import threading
import time
from typing import Any, Optional

from ..config import settings

_lock = threading.Lock()
_hits = 0
_misses = 0


def _path(parts: tuple) -> Any:
    key = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return settings.cache_dir / f"{key}.json"


def _bump(hit: bool) -> None:
    global _hits, _misses
    with _lock:
        if hit:
            _hits += 1
        else:
            _misses += 1


def get_cached(*parts) -> Optional[Any]:
    p = _path(parts)
    if not p.exists():
        _bump(False)
        return None
    ttl = settings.cache_ttl_hours
    if ttl > 0:
        try:
            if time.time() - p.stat().st_mtime > ttl * 3600:
                _bump(False)   # stale → treat as a miss; caller recomputes & overwrites
                return None
        except OSError:
            _bump(False)
            return None
    try:
        value = json.loads(p.read_text(encoding="utf-8"))
        _bump(True)
        return value
    except (json.JSONDecodeError, OSError):
        _bump(False)
        return None


def set_cached(value: Any, *parts) -> None:
    try:
        _path(parts).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def stats() -> dict:
    with _lock:
        total = _hits + _misses
        return {"hits": _hits, "misses": _misses,
                "hit_rate": round(_hits / total, 4) if total else 0.0}
