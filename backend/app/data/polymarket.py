"""Polymarket Gamma API client (read-only). REAL data only — no sample fallback.

Ingests from /events (which carries tags -> category, plus nested binary markets),
so the browser gets Polymarket-like categories + multi-outcome grouping in one pass.
refresh_market() hits /markets/{id} for price/resolution updates (poller).

We only READ public market data (PRD §3): no orders, wallets, or payment.
Binary (Yes/No) legs only. YES implied prob = outcomePrices[0]. closed + price~1/0
-> resolved; closed-but-ambiguous -> void. Any API failure -> empty (never faked).
"""
import json
from typing import Optional

import httpx

GAMMA = "https://gamma-api.polymarket.com"

# "polymarket" if the last list call hit the live API, "none" if it failed.
last_source = "unknown"

# Map Polymarket event tag labels -> a broad category (first match wins).
_CATEGORY_RULES: list[tuple[str, set[str]]] = [
    ("加密", {"Crypto", "Bitcoin", "Ethereum", "Solana", "Crypto Prices"}),
    ("体育", {"Sports", "Soccer", "Games", "Football", "NBA", "NFL", "MLB", "NHL",
             "Tennis", "FIFA World Cup", "UFC", "Boxing", "Esports", "Cricket"}),
    ("选举", {"Elections", "Global Elections"}),
    ("地缘政治", {"Geopolitics", "War", "Iran", "Israel", "Ukraine", "Russia", "Middle East"}),
    ("政治", {"Politics", "Trump", "Congress", "US politics"}),
    ("经济", {"Economy", "Economics", "Fed", "Inflation", "Finance", "Macro",
             "Commodities", "Oil", "Gas", "Gold"}),
    ("科技", {"Tech", "Technology", "AI", "Science", "Space"}),
    ("文化", {"Culture", "Pop Culture", "Entertainment", "Movies", "Music", "Awards"}),
    ("天气", {"Weather", "Climate"}),
]


def _derive_category(tags: Optional[list]) -> str:
    labels = {t.get("label") for t in (tags or []) if isinstance(t, dict)}
    for cat, keys in _CATEGORY_RULES:
        if labels & keys:
            return cat
    return "其他"


def _price_status(m: dict):
    """-> (yes_prob, status, resolution, resolved_at) for a binary Yes/No market, else None."""
    outcomes = m.get("outcomes")
    if isinstance(outcomes, str):
        try:
            outcomes = json.loads(outcomes)
        except json.JSONDecodeError:
            return None
    if not outcomes or [str(o).lower() for o in outcomes] != ["yes", "no"]:
        return None
    prices = m.get("outcomePrices")
    if isinstance(prices, str):
        try:
            prices = json.loads(prices)
        except json.JSONDecodeError:
            prices = None
    try:
        yes = float(prices[0]) if prices else None
    except (TypeError, ValueError):
        yes = None
    closed = bool(m.get("closed"))
    status, resolution, resolved_at = "open", None, None
    if closed:
        if yes is None:
            return None
        if yes >= 0.99:
            status, resolution = "resolved", 1
        elif yes <= 0.01:
            status, resolution = "resolved", 0
        else:
            status = "void"
        resolved_at = m.get("endDate") or m.get("endDateIso")
    return yes, status, resolution, resolved_at


def _public_url(m: dict) -> Optional[str]:
    events = m.get("events") or []
    event_slug = events[0].get("slug") if events and isinstance(events[0], dict) else None
    if event_slug:
        return f"https://polymarket.com/event/{event_slug}"
    if m.get("slug"):
        return f"https://polymarket.com/market/{m['slug']}"
    return "https://polymarket.com/"


def _leg(m: dict, *, event_id, event_title, event_url, category) -> Optional[dict]:
    """Build a Market dict from a nested event-market (leg) + its event context."""
    ps = _price_status(m)
    if ps is None:
        return None
    yes, status, resolution, resolved_at = ps
    desc = (m.get("description") or "").strip()
    return {
        "id": str(m.get("id")),
        "question": (m.get("question") or "").strip(),
        "description": desc[:1500] or None,
        "category": category,
        "opened_at": m.get("startDate") or m.get("startDateIso"),
        "close_at": m.get("endDate") or m.get("endDateIso"),
        "status": status,
        "current_prob": yes,
        "resolution": resolution,
        "resolved_at": resolved_at,
        "url": event_url,
        "event_id": event_id,
        "event_title": event_title,
        "outcome_name": m.get("groupItemTitle") or None,
    }


def _parse(m: dict) -> Optional[dict]:
    """Parse a top-level /markets object (used by refresh_market)."""
    ps = _price_status(m)
    if ps is None:
        return None
    yes, status, resolution, resolved_at = ps
    events = m.get("events") or []
    ev = events[0] if events and isinstance(events[0], dict) else {}
    desc = (m.get("description") or "").strip()
    return {
        "id": str(m.get("id")),
        "question": (m.get("question") or "").strip(),
        "description": desc[:1500] or None,
        "category": m.get("category"),
        "opened_at": m.get("startDate") or m.get("startDateIso"),
        "close_at": m.get("endDate") or m.get("endDateIso"),
        "status": status,
        "current_prob": yes,
        "resolution": resolution,
        "resolved_at": resolved_at,
        "url": _public_url(m),
        "event_id": str(ev["id"]) if ev.get("id") is not None else None,
        "event_title": (ev.get("title") or "").strip() or None,
        "outcome_name": m.get("groupItemTitle") or None,
    }


def list_open_markets(limit: int = 50) -> list[dict]:
    """Fetch top events by volume; return their open, non-decided binary legs with
    category + grouping. `limit` ~ number of events scanned."""
    global last_source
    try:
        r = httpx.get(f"{GAMMA}/events", timeout=25, params={
            "closed": "false", "active": "true",
            "limit": str(limit), "order": "volume24hr", "ascending": "false",
        })
        r.raise_for_status()
        out: list[dict] = []
        for ev in r.json():
            category = _derive_category(ev.get("tags"))
            eid = str(ev["id"]) if ev.get("id") is not None else None
            etitle = (ev.get("title") or "").strip() or None
            eurl = (f"https://polymarket.com/event/{ev['slug']}" if ev.get("slug")
                    else "https://polymarket.com/")
            for m in (ev.get("markets") or []):
                leg = _leg(m, event_id=eid, event_title=etitle, event_url=eurl, category=category)
                # skip decided legs (price ~0/1 = outcome already known)
                if (leg and leg["status"] == "open" and leg["current_prob"] is not None
                        and 0.02 < leg["current_prob"] < 0.98):
                    out.append(leg)
            if len(out) >= limit * 8:   # safety cap on total legs stored
                break
        last_source = "polymarket"
        return out
    except (httpx.HTTPError, ValueError):
        last_source = "none"
        return []


def refresh_market(market_id: str) -> Optional[dict]:
    """Latest price + resolution status for one market (used by the poller)."""
    try:
        r = httpx.get(f"{GAMMA}/markets/{market_id}", timeout=20)
        r.raise_for_status()
        body = r.json()
        return _parse(body[0] if isinstance(body, list) else body)
    except (httpx.HTTPError, ValueError):
        return None
