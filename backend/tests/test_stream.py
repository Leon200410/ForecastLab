"""Streaming forecast SSE endpoint (B1). Offline: forecaster.run_forecast is
stubbed so we test the SSE plumbing (stage events / done / failed) deterministically
without any LLM or network call."""
from fastapi.testclient import TestClient

from app.api import app
from app.config import settings
from app.data import polymarket
from app.forecast import forecaster
from app.lib import db
from app.lib.util import now_iso


def _seed_open():
    db.put("markets", {"id": "m1", "question": "Q?", "status": "open",
                       "current_prob": 0.6, "created_at": now_iso()})


class _FakeForecast:
    def model_dump(self):
        return {"id": "fc1", "agent_prob": 0.62}


def test_stream_emits_stage_events_then_done(monkeypatch):
    monkeypatch.setattr(settings, "api_tokens", {})
    _seed_open()

    def fake_run(market, on_event=None, fresh=False):
        on_event("evidence", {"count": 3, "lessons": 1})
        on_event("run", {"i": 0, "probability": 0.6, "confidence": "med"})
        on_event("aggregate", {"agent_prob": 0.62, "confidence": "med"})
        return _FakeForecast()

    monkeypatch.setattr(forecaster, "run_forecast", fake_run)
    with TestClient(app) as c:
        r = c.get("/api/forecasts/stream?market_id=m1")
        assert r.status_code == 200
        assert "text/event-stream" in r.headers.get("content-type", "")
        for ev in ("event: evidence", "event: run", "event: aggregate", "event: done"):
            assert ev in r.text


def test_stream_emits_failed_on_error(monkeypatch):
    monkeypatch.setattr(settings, "api_tokens", {})
    _seed_open()

    def boom(market, on_event=None, fresh=False):
        raise RuntimeError("provider down")

    monkeypatch.setattr(forecaster, "run_forecast", boom)
    with TestClient(app) as c:
        r = c.get("/api/forecasts/stream?market_id=m1")
        assert r.status_code == 200 and "event: failed" in r.text


def test_stream_404_for_unknown_market(monkeypatch):
    monkeypatch.setattr(settings, "api_tokens", {})
    monkeypatch.setattr(polymarket, "refresh_market", lambda mid: None)  # stay offline
    with TestClient(app) as c:
        assert c.get("/api/forecasts/stream?market_id=nope").status_code == 404
