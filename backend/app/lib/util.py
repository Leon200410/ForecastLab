"""Small shared helpers: ids, timestamps, json extraction, math."""
import json
import re
import uuid
from datetime import datetime, timedelta, timezone

BEIJING = timezone(timedelta(hours=8))   # the project's display timezone (UTC+8)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_str() -> str:
    """Current date in Beijing (UTC+8) — injected into prompts so the Agent knows 'now'."""
    return datetime.now(BEIJING).strftime("%Y-%m-%d")


def _parse_iso(s: str):
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def beijing_date(iso: str) -> str:
    """A (UTC) ISO timestamp -> Beijing date string (for the forecast prompt)."""
    dt = _parse_iso(iso)
    return dt.astimezone(BEIJING).strftime("%Y-%m-%d") if dt else (iso or "")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _loads_lenient(s: str) -> dict | None:
    """json.loads, retried once with trailing commas stripped (a common LLM slip)."""
    try:
        v = json.loads(s)
    except json.JSONDecodeError:
        try:
            v = json.loads(re.sub(r",(\s*[}\]])", r"\1", s))
        except json.JSONDecodeError:
            return None
    return v if isinstance(v, dict) else None


def _brace_objects(text: str):
    """Yield each top-level {...} substring by brace matching (ignores nested ones)."""
    depth, start = 0, -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0:
                yield text[start:i + 1]


def extract_json(text: str) -> dict | None:
    """Pull the first parseable JSON object out of an LLM response.

    Handles ```json fences, surrounding prose, multiple objects, and trailing
    commas — returns the first candidate that parses to a dict, else None.
    """
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        d = _loads_lenient(fence.group(1))
        if d is not None:
            return d
    d = _loads_lenient(text.strip())
    if d is not None:
        return d
    for cand in _brace_objects(text):
        d = _loads_lenient(cand)
        if d is not None:
            return d
    return None
