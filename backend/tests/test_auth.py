"""Light auth + audit trail (D1 + C5). Auth is OFF unless API_TOKENS is set;
every forecast/bet/review is recorded with the acting user."""
from fastapi.testclient import TestClient

from app.api import app
from app.config import settings
from app.lib import db
from app.lib.util import now_iso


def _seed():
    db.put("markets", {"id": "m1", "question": "Q?", "status": "open", "current_prob": 0.6,
                       "created_at": now_iso()})
    db.put("forecasts", {"id": "f1", "market_id": "m1", "agent_prob": 0.7,
                         "market_prob_at_analysis": 0.6, "confidence": "med", "rationale": "r",
                         "key_factors": [], "runs": [], "retrieved_lessons": [], "evidence": [],
                         "created_at": now_iso(), "status": "pending"})


def test_auth_off_by_default_and_audits_bet(monkeypatch):
    monkeypatch.setattr(settings, "api_tokens", {})
    _seed()
    with TestClient(app) as c:
        r = c.post("/api/bets", json={"forecast_id": "f1", "side": "YES",
                                      "stake": 50, "entry_prob": 0.6})
        assert r.status_code == 200
        a = c.get("/api/audit").json()
        assert any(e["action"] == "bet" and e["user"] == "local" for e in a)


def test_token_gate_blocks_and_allows(monkeypatch):
    monkeypatch.setattr(settings, "api_tokens", {"secret": "alice"})
    with TestClient(app) as c:
        assert c.get("/api/health").status_code == 200        # health always open
        assert c.get("/api/markets").status_code == 401        # gated without a token
        ok = c.get("/api/markets", headers={"Authorization": "Bearer secret"})
        assert ok.status_code == 200                            # valid token passes


def test_response_carries_request_id(monkeypatch):
    monkeypatch.setattr(settings, "api_tokens", {})
    with TestClient(app) as c:
        r = c.get("/api/health")
        assert r.status_code == 200 and r.headers.get("x-request-id")


def test_audit_attributes_action_to_token_user(monkeypatch):
    monkeypatch.setattr(settings, "api_tokens", {"secret": "alice"})
    _seed()
    with TestClient(app) as c:
        h = {"Authorization": "Bearer secret"}
        r = c.post("/api/bets", json={"forecast_id": "f1", "side": "YES",
                                      "stake": 50, "entry_prob": 0.6}, headers=h)
        assert r.status_code == 200
        a = c.get("/api/audit", headers=h).json()
        assert a[0]["user"] == "alice" and a[0]["action"] == "bet"  # newest first
