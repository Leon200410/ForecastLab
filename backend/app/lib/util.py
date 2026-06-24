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


def extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of an LLM response (handles ```json fences)."""
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fence.group(1) if fence else None
    if candidate is None:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start:end + 1]
    if candidate is None:
        return None
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None
