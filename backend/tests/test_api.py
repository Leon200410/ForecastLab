"""API + virtual-account plumbing, provider-free (no LLM/search/network).

A Forecast is seeded directly into the DB (test setup), then the real bet /
account / settlement / eval endpoints are exercised. Resolution uses the real
settlement path (poller._resolve_market) — the same code a real Polymarket
resolution triggers — without any simulated-resolution endpoint.
"""
from fastapi.testclient import TestClient

from app.api import app
from app.data import poller
from app.lib import db
from app.lib.util import now_iso


def _seed_market_and_forecast(mid="m1", fid="f1", price=0.6):
    db.put("markets", {"id": mid, "question": "Will X happen?", "status": "open",
                       "current_prob": price, "url": "https://polymarket.com/event/x",
                       "created_at": now_iso()})
    db.put("forecasts", {"id": fid, "market_id": mid, "agent_prob": 0.7,
                         "market_prob_at_analysis": price, "confidence": "med", "rationale": "r",
                         "key_factors": [], "runs": [], "retrieved_lessons": [], "evidence": [],
                         "created_at": now_iso(), "status": "pending"})
    return mid, fid


def test_bet_account_resolve_flow():
    mid, fid = _seed_market_and_forecast(price=0.6)
    with TestClient(app) as c:
        h = c.get("/api/health").json()
        assert h["ok"] is True and "llm_ready" in h

        # market carries a click-through url
        assert c.get("/api/markets").json()[0]["url"].startswith("https://polymarket.com/")

        # manual paper bet debits the virtual account
        r = c.post("/api/bets", json={"forecast_id": fid, "side": "YES",
                                      "stake": 100, "entry_prob": 0.6})
        assert r.status_code == 200
        assert c.get("/api/account").json()["cash_balance"] == 1e4 - 100
        assert len(c.get("/api/holdings").json()) == 1

        # one bet per forecast
        assert c.post("/api/bets", json={"forecast_id": fid, "side": "NO",
                                         "stake": 10, "entry_prob": 0.4}).status_code == 400

        # resolve via the real settlement path (as a Polymarket resolution would)
        market = db.get("markets", mid)
        market.update({"status": "resolved", "resolution": 1, "current_prob": 1.0})
        db.put("markets", market)
        poller._resolve_market(mid, 1)

        pos = c.get("/api/positions").json()[0]
        assert pos["status"] == "resolved" and pos["outcome"] == 1
        assert pos["bet"]["pnl"] > 0  # YES @ 0.6 won

        summary = c.get("/api/eval/summary").json()
        assert summary["forecasts"]["n"] >= 1
        assert "beats_market" in summary["forecasts"]
        assert c.get("/api/account").json()["realized_pnl"] > 0


def test_bet_requires_existing_forecast():
    with TestClient(app) as c:
        assert c.post("/api/bets", json={"forecast_id": "nope", "side": "YES",
                                         "stake": 10, "entry_prob": 0.5}).status_code == 400


def test_health_reports_real_providers():
    with TestClient(app) as c:
        h = c.get("/api/health").json()
        assert h["llm"] in ("deepseek", "anthropic")  # never "mock"
        assert h["search"] in ("tavily", "serper")


def test_agent_routing_crypto_gets_price_tool():
    from app.forecast.agents import DEFAULT_TOOLS, PERSONAS, TOOLS_BY_CAT, get_crypto_price
    assert get_crypto_price in TOOLS_BY_CAT["加密"]      # crypto agent has the live-price tool
    assert get_crypto_price not in DEFAULT_TOOLS          # other categories don't
    assert "现价" in PERSONAS["加密"]                      # crypto persona prioritizes current price


def test_derive_category_from_tags():
    from app.data.polymarket import _derive_category
    assert _derive_category([{"label": "Soccer"}, {"label": "Sports"}]) == "体育"
    assert _derive_category([{"label": "Bitcoin"}, {"label": "Crypto"}]) == "加密"
    assert _derive_category([{"label": "Elections"}, {"label": "Politics"}]) == "选举"  # elections first
    assert _derive_category([{"label": "Iran"}]) == "地缘政治"
    assert _derive_category([{"label": "Oil"}, {"label": "Commodities"}]) == "经济"
    assert _derive_category([]) == "其他"


def test_ingest_prunes_stale_open_markets(monkeypatch):
    from app.data import ingest, polymarket
    # existing DB: a stale open market (no position) + one referenced by a forecast
    db.put("markets", {"id": "STALE", "question": "old", "status": "open",
                       "current_prob": 0.5, "created_at": now_iso()})
    db.put("markets", {"id": "KEEP", "question": "kept", "status": "open",
                       "current_prob": 0.5, "created_at": now_iso()})
    db.put("forecasts", {"id": "fK", "market_id": "KEEP", "status": "pending", "created_at": now_iso()})
    # fresh feed returns only a brand-new market
    monkeypatch.setattr(polymarket, "last_source", "polymarket")
    monkeypatch.setattr(polymarket, "list_open_markets", lambda limit=50: [
        {"id": "NEW", "question": "new", "status": "open", "current_prob": 0.5, "created_at": now_iso()}])
    ingest.ingest_open()
    ids = {m["id"] for m in db.list_all("markets")}
    assert "STALE" not in ids   # pruned (not in feed, no position)
    assert "KEEP" in ids        # referenced by a forecast -> kept
    assert "NEW" in ids         # freshly ingested


def test_grouped_markets_buckets_multi_outcome():
    # one standalone binary + two legs of a multi-outcome event
    db.put("markets", {"id": "s1", "question": "Single?", "status": "open",
                       "current_prob": 0.5, "created_at": now_iso()})
    for lid, name, p in [("L1", "France", 0.20), ("L2", "Argentina", 0.14)]:
        db.put("markets", {"id": lid, "question": f"Will {name} win?", "status": "open",
                           "current_prob": p, "created_at": now_iso(),
                           "event_id": "30615", "event_title": "World Cup Winner",
                           "outcome_name": name})
    with TestClient(app) as c:
        items = c.get("/api/markets/grouped").json()
        assert {i["kind"] for i in items} == {"single", "event"}
        ev = next(i for i in items if i["kind"] == "event")
        assert ev["event_title"] == "World Cup Winner"
        assert [o["name"] for o in ev["outcomes"]] == ["France", "Argentina"]  # sorted by prob
        assert next(i for i in items if i["kind"] == "single")["market"]["id"] == "s1"
