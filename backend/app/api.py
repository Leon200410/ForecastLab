"""FastAPI app (PRD §7-M6). Read-mostly REST; a few trigger POSTs.

Endpoints:
  GET  /api/health
  GET  /api/markets?status=open
  POST /api/markets/ingest
  POST /api/forecasts {market_id}            -> run Agent analysis (no betting)
  GET  /api/forecasts[?market_id=] , /api/forecasts/{id}
  GET  /api/positions                        -> unified list (forecast + bet + market)
  POST /api/bets {forecast_id, side, stake, entry_prob, note?}  -> user manual paper bet
  GET  /api/bets
  GET  /api/account , GET /api/holdings
  POST /api/forecasts/{id}/review            -> generate review + write KB
  GET  /api/eval/summary , GET /api/kb , GET /api/cost
  POST /api/poll                             -> run one poll tick now (mark + settle)
"""
import json
import logging
import queue
import threading
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from .config import settings
from .data import ingest, poller, polymarket
from .eval import metrics
from .forecast import forecaster
from .kb import review as kb_review
from .kb import store as kb_store
from .lib import audit, cache, db
from .lib.cost_tracker import tracker
from .lib.models import Bet, Forecast
from .portfolio import account
from .providers import embedding

_log = logging.getLogger("forecastlab.api")
_poller_stop = threading.Event()
_poller_thread: Optional[threading.Thread] = None


def _start_poller() -> None:
    global _poller_thread
    if _poller_thread and _poller_thread.is_alive():
        return
    _poller_stop.clear()

    def loop() -> None:
        # wait() returns True when stop is signalled (-> exit), False on timeout (-> poll);
        # this makes the sleep interruptible so shutdown doesn't kill a tick mid-flight.
        while not _poller_stop.wait(max(1, settings.poll_interval_min) * 60):
            try:
                poller.poll_once()
            except Exception:
                pass

    _poller_thread = threading.Thread(target=loop, daemon=True)
    _poller_thread.start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    db.purge_legacy_mock()  # clean any leftover sample-/demo- rows on startup
    account.get_or_init_account()
    tracker.restore()  # restore cumulative spend + today's cap so a restart doesn't lose it
    try:
        embedding.warmup()  # load the embedder now so download/init fails loudly at boot
    except Exception:
        pass  # never block startup on the (non-critical) KB embedder
    if settings.auto_ingest and not db.list_all("markets"):
        try:
            ingest.ingest_open(50)
        except Exception:
            pass
    if settings.poll_interval_min > 0:
        _start_poller()
    yield
    # graceful shutdown: signal the poller and let the current tick drain
    _poller_stop.set()
    if _poller_thread:
        _poller_thread.join(timeout=10)


app = FastAPI(title="ForecastLab API", version="0.7", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_origins,
    allow_methods=["*"], allow_headers=["*"],
)


def _token_from(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    # query param fallback so EventSource (which can't set headers) can authenticate
    return (request.headers.get("x-api-token", "")
            or request.query_params.get("token", "")).strip()


@app.middleware("http")
async def _identity(request: Request, call_next):
    """Per-request: assign a request id, resolve the caller's identity (for
    attribution; X-User from a reverse proxy or 'local' when auth is off), gate
    /api behind a valid token when API_TOKENS is set, and emit a structured
    access log. Every response carries X-Request-ID for cross-log correlation."""
    rid = uuid.uuid4().hex[:12]
    request.state.request_id = rid
    t0 = time.perf_counter()
    user = request.headers.get("x-user", "").strip() or "local"

    if (settings.api_tokens and request.method != "OPTIONS"
            and request.url.path.startswith("/api/") and request.url.path != "/api/health"):
        mapped = settings.api_tokens.get(_token_from(request))
        if mapped is None:
            _log.info("%s %s 401 user=- rid=%s", request.method, request.url.path, rid)
            resp = JSONResponse({"detail": "invalid or missing API token"}, status_code=401)
            resp.headers["X-Request-ID"] = rid
            return resp
        user = mapped

    request.state.user = user
    resp = await call_next(request)
    resp.headers["X-Request-ID"] = rid
    _log.info("%s %s %s %.1fms user=%s rid=%s", request.method, request.url.path,
              resp.status_code, (time.perf_counter() - t0) * 1000, user, rid)
    return resp


def current_user(request: Request) -> str:
    return getattr(request.state, "user", "local")


# ---- request bodies ---------------------------------------------------------
class ForecastReq(BaseModel):
    market_id: str


class BetReq(BaseModel):
    forecast_id: str
    side: str
    stake: float
    entry_prob: float
    note: Optional[str] = None


# ---- markets ----------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"ok": True,
            "llm": settings.llm_mode, "llm_ready": settings.llm_ready,
            "search": settings.search_mode, "search_ready": settings.search_ready,
            "embedding": embedding.active_info(), "data_source": polymarket.last_source}


@app.get("/api/markets")
def list_markets(status: Optional[str] = Query(default=None)):
    return db.list_all("markets", status=status)


def _group_markets(markets: list[dict]) -> list[dict]:
    """Standalone binaries stay single; legs of a multi-outcome event (negRisk,
    e.g. 'World Cup Winner') collapse into one event with an outcomes[] array."""
    events: dict[str, dict] = {}
    items: list = []
    for m in markets:
        if m.get("outcome_name") and m.get("event_id"):
            eid = m["event_id"]
            if eid not in events:
                events[eid] = {"kind": "event", "event_id": eid,
                               "event_title": (m.get("event_title") or "").strip(),
                               "url": m.get("url"), "category": m.get("category"), "outcomes": []}
                items.append(("event", eid))
            events[eid]["outcomes"].append({"market_id": m["id"], "name": m["outcome_name"],
                                            "prob": m.get("current_prob"), "url": m.get("url")})
        else:
            items.append(("single", m))
    out = []
    for kind, val in items:
        if kind == "event":
            ev = events[val]
            ev["outcomes"].sort(key=lambda o: (o["prob"] or 0), reverse=True)
            out.append(ev)
        else:
            out.append({"kind": "single", "market": val})
    return out


@app.get("/api/markets/grouped")
def list_markets_grouped():
    """Open markets for the browser; multi-outcome events grouped into outcome
    arrays so the user can pick a specific outcome to analyze."""
    return _group_markets(db.list_all("markets", status="open"))


@app.post("/api/markets/ingest")
def ingest_markets(limit: int = 50):
    return ingest.ingest_open(limit)


# ---- forecasts (Agent analysis) --------------------------------------------
@app.post("/api/forecasts")
def create_forecast(req: ForecastReq, user: str = Depends(current_user)):
    market = db.get("markets", req.market_id)
    if market is None:
        # allow analyzing a market we can still fetch live
        market = polymarket.refresh_market(req.market_id)
        if market is None:
            raise HTTPException(404, "market not found")
        db.put("markets", market)
    if market.get("status") != "open":
        raise HTTPException(400, "market is not open")
    try:
        fc = forecaster.run_forecast(market)
    except Exception as e:  # surface the underlying cause as-is (no double prefix)
        raise HTTPException(500, str(e))
    audit.record(user, "forecast", req.market_id)
    return fc.model_dump()


@app.get("/api/forecasts/stream")
def stream_forecast(market_id: str, request: Request):
    """Server-Sent Events: run the agent analysis and push stage events
    (evidence → each ensemble run → aggregate → done) so the UI shows live
    progress instead of blocking on the full ~30s–2min run."""
    market = db.get("markets", market_id)
    if market is None:
        market = polymarket.refresh_market(market_id)
        if market is None:
            raise HTTPException(404, "market not found")
        db.put("markets", market)
    if market.get("status") != "open":
        raise HTTPException(400, "market is not open")
    user = current_user(request)
    events: "queue.Queue" = queue.Queue()

    def worker() -> None:
        try:
            fc = forecaster.run_forecast(market, on_event=lambda k, d: events.put((k, d)))
            audit.record(user, "forecast", market_id)
            events.put(("done", fc.model_dump()))
        except Exception as e:  # surface the underlying cause as-is (no double prefix)
            events.put(("failed", {"message": str(e)}))
        finally:
            events.put((None, None))  # sentinel: end of stream

    threading.Thread(target=worker, daemon=True).start()

    def gen():
        while True:
            kind, data = events.get()
            if kind is None:
                break
            yield f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/forecasts")
def list_forecasts(market_id: Optional[str] = Query(default=None)):
    return db.list_all("forecasts", market_id=market_id)


@app.get("/api/forecasts/{forecast_id}")
def get_forecast(forecast_id: str):
    fc = db.get("forecasts", forecast_id)
    if fc is None:
        raise HTTPException(404, "forecast not found")
    bets = db.list_all("bets", forecast_id=forecast_id)
    review = db.get("reviews", forecast_id)
    market = db.get("markets", fc["market_id"]) or {}
    return {**fc, "bet": bets[0] if bets else None, "review": review,
            "question": market.get("question"), "url": market.get("url"),
            "opened_at": market.get("opened_at"), "close_at": market.get("close_at")}


@app.get("/api/positions")
def list_positions():
    """Unified list keyed by analysis: forecast + its bet + market context (PRD §7-M6)."""
    bets_by_fc = {b["forecast_id"]: b for b in db.list_all("bets")}
    markets = {m["id"]: m for m in db.list_all("markets")}
    out = []
    for f in db.list_all("forecasts"):
        m = markets.get(f["market_id"], {})
        out.append({
            "id": f["id"], "market_id": f["market_id"], "question": m.get("question"),
            "url": m.get("url"), "opened_at": m.get("opened_at"), "close_at": m.get("close_at"),
            "category": m.get("category"), "created_at": f["created_at"],
            "agent_prob": f["agent_prob"], "market_prob_at_analysis": f["market_prob_at_analysis"],
            "confidence": f["confidence"], "status": f["status"], "outcome": f.get("outcome"),
            "brier": f.get("brier"), "market_brier": f.get("market_brier"),
            "reviewed": f.get("reviewed", False),
            "market_status": m.get("status"), "market_current_prob": m.get("current_prob"),
            "bet": bets_by_fc.get(f["id"]),
        })
    return out


# ---- bets (user manual paper positions) ------------------------------------
@app.post("/api/bets")
def create_bet(req: BetReq, user: str = Depends(current_user)):
    if req.side not in ("YES", "NO"):
        raise HTTPException(400, "side must be YES or NO")
    try:
        bet = account.place_bet(req.forecast_id, req.side, req.stake, req.entry_prob, req.note)
    except account.BetError as e:
        raise HTTPException(400, str(e))
    audit.record(user, "bet", f"{req.forecast_id}:{req.side}:{req.stake}")
    return bet.model_dump()


@app.get("/api/bets")
def list_bets():
    return db.list_all("bets")


# ---- virtual portfolio ------------------------------------------------------
@app.get("/api/account")
def get_account():
    return account.summary()


@app.get("/api/holdings")
def get_holdings():
    out = []
    for b in db.list_all("bets", status="pending"):
        m = db.get("markets", b["market_id"]) or {}
        out.append({
            "id": b["id"], "market_id": b["market_id"], "forecast_id": b["forecast_id"],
            "question": m.get("question"), "url": m.get("url"),
            "opened_at": m.get("opened_at"), "close_at": m.get("close_at"),
            "side": b["side"], "stake": b["stake"], "entry_prob": b["entry_prob"],
            "shares": b["shares"], "current_price": b.get("current_price"),
            "unrealized_pnl": b.get("unrealized_pnl"), "created_at": b["created_at"],
        })
    return out


# ---- review / KB / eval -----------------------------------------------------
@app.post("/api/forecasts/{forecast_id}/review")
def review_forecast(forecast_id: str, user: str = Depends(current_user)):
    try:
        rv = kb_review.generate_review(forecast_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    audit.record(user, "review", forecast_id)
    return rv.model_dump()


@app.get("/api/eval/summary")
def eval_summary():
    resolved = [
        {"agent_prob": f["agent_prob"], "market_prob": f["market_prob_at_analysis"],
         "outcome": f["outcome"], "agent_prob_cal": f.get("agent_prob_calibrated"),
         "prompt_version": f.get("prompt_version")}
        for f in db.list_all("forecasts", status="resolved")
        if f.get("outcome") is not None
    ]
    return {
        "forecasts": metrics.summarize_forecasts(resolved),
        "points": [{"a": r["agent_prob"], "m": r["market_prob"], "o": r["outcome"]}
                   for r in resolved][:200],  # agent-vs-market scatter (capped)
        "portfolio": account.summary(),
        "kb_size": kb_store.count(),
        "cost": tracker.summary(),
        "cache": cache.stats(),
        "llm_mode": settings.llm_mode,
        "data_source": polymarket.last_source,
    }


@app.get("/api/kb")
def list_kb():
    return [p for _, p in db.kb_all()]


@app.get("/api/cost")
def get_cost():
    return {**tracker.summary(), "cache": cache.stats()}


@app.get("/api/audit")
def get_audit(limit: int = Query(default=100, le=1000)):
    """Recent user actions (forecast / bet / review), newest first — team accountability."""
    return audit.recent(limit)


# ---- ops --------------------------------------------------------------------
@app.post("/api/poll")
def run_poll():
    """Run one real poll tick now: mark-to-market open positions + settle any
    markets Polymarket has resolved. Resolution comes only from Polymarket."""
    return poller.poll_once()
