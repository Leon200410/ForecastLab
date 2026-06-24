"""Background poller (PRD §7-M1). Two jobs per tick:

  (a) mark-to-market: refresh current price of open positions → unrealized P&L
  (b) resolution: when a market resolves, score the Forecast (Brier vs market)
      and settle the Bet (credit cash, realize P&L). Void → refund stake.

Pure data/bookkeeping — never places real orders.
"""
from ..eval import metrics
from ..lib import db
from ..lib.models import Bet, Forecast
from ..portfolio import account
from . import polymarket


def _resolve_market(mid: str, outcome: int) -> tuple[int, int]:
    forecasts = scored = 0
    for f in db.list_all("forecasts", market_id=mid, status="pending"):
        fc = Forecast(**f)
        fc.status = "resolved"
        fc.outcome = outcome  # type: ignore[assignment]
        fc.brier = metrics.brier(fc.agent_prob, outcome)
        fc.market_brier = metrics.brier(fc.market_prob_at_analysis, outcome)
        db.put("forecasts", fc.model_dump())
        forecasts += 1
    for b in db.list_all("bets", market_id=mid, status="pending"):
        account.settle_bet(Bet(**b), outcome)
        scored += 1
    return forecasts, scored


def _void_market(mid: str) -> int:
    """Refund stakes for open bets; close out forecasts without a score."""
    refunded = 0
    acc = account.get_or_init_account()
    for b in db.list_all("bets", market_id=mid, status="pending"):
        bet = Bet(**b)
        acc.cash_balance += bet.stake
        bet.status = "resolved"
        bet.pnl = 0.0
        bet.unrealized_pnl = None
        db.put("bets", bet.model_dump())
        refunded += 1
    db.put_account(acc.model_dump())
    for f in db.list_all("forecasts", market_id=mid, status="pending"):
        fc = Forecast(**f)
        fc.status = "resolved"  # outcome stays None → excluded from Brier eval
        db.put("forecasts", fc.model_dump())
    return refunded


def poll_once() -> dict:
    pending_fc = db.list_all("forecasts", status="pending")
    pending_bets = db.list_all("bets", status="pending")
    market_ids = {f["market_id"] for f in pending_fc} | {b["market_id"] for b in pending_bets}

    marked = resolved = settled = voided = 0
    for mid in market_ids:
        fresh = polymarket.refresh_market(mid)
        if not fresh:
            continue
        prev = db.get("markets", mid)
        if prev:  # update only dynamic fields; keep category/event/url/timing
            prev.update({"current_prob": fresh.get("current_prob"), "status": fresh["status"],
                         "resolution": fresh.get("resolution"), "resolved_at": fresh.get("resolved_at")})
            record = prev
        else:
            record = fresh
        db.put("markets", record)
        yes = record.get("current_prob")

        if record["status"] == "open" and yes is not None:
            for b in db.list_all("bets", market_id=mid, status="pending"):
                account.mark_bet(Bet(**b), yes)
                marked += 1
        elif record["status"] == "resolved" and record.get("resolution") is not None:
            _f, _s = _resolve_market(mid, int(record["resolution"]))
            resolved += 1
            settled += _s
        elif record["status"] == "void":
            voided += _void_market(mid)

    return {"markets_checked": len(market_ids), "marked_to_market": marked,
            "markets_resolved": resolved, "bets_settled": settled, "bets_refunded": voided}
