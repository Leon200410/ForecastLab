"""Virtual account & holdings (PRD §7-M5(d)). Paper bookkeeping only — no payment.

Mechanics:
  open  : debit stake from cash; shares = stake / entry_prob
  mark  : open positions valued at current side price → unrealized P&L
  settle: on resolution, credit stake/entry_prob if correct (else 0); realize P&L
  equity: cash + sum(open position current value); return% vs starting balance
"""
from typing import Optional

from ..config import settings
from ..eval import metrics
from ..lib import db
from ..lib.models import Account, Bet, Forecast
from ..lib.util import new_id, now_iso


class BetError(ValueError):
    """User-facing bet placement error (insufficient funds / duplicate / closed)."""


def get_or_init_account() -> Account:
    raw = db.get_account()
    if raw is None:
        acc = Account(
            starting_balance=settings.starting_balance_usd,
            cash_balance=settings.starting_balance_usd,
            realized_pnl=0.0,
        )
        db.put_account(acc.model_dump())
        return acc
    return Account(**raw)


def _save(acc: Account) -> None:
    db.put_account(acc.model_dump())


def place_bet(forecast_id: str, side: str, stake: float, entry_prob: float,
              note: Optional[str] = None) -> Bet:
    fc_raw = db.get("forecasts", forecast_id)
    if fc_raw is None:
        raise BetError("forecast not found")
    forecast = Forecast(**fc_raw)

    market = db.get("markets", forecast.market_id)
    if market and market.get("status") != "open":
        raise BetError("market is not open")
    if not (0.0 < entry_prob < 1.0):
        raise BetError("entry_prob must be in (0,1)")
    if stake <= 0:
        raise BetError("stake must be positive")
    if db.list_all("bets", forecast_id=forecast_id):
        raise BetError("this analysis already has a bet (one bet per forecast)")

    acc = get_or_init_account()
    if stake > acc.cash_balance + 1e-9:
        raise BetError(f"insufficient balance: stake {stake} > cash {acc.cash_balance:.2f}")

    bet = Bet(
        id=new_id("bet"),
        market_id=forecast.market_id,
        forecast_id=forecast_id,
        side=side,  # type: ignore[arg-type]
        stake=stake,
        entry_prob=entry_prob,
        shares=metrics.shares_for(stake, entry_prob),
        note=note,
        created_at=now_iso(),
        status="pending",
        current_price=entry_prob,
        unrealized_pnl=0.0,
    )
    acc.cash_balance -= stake
    db.put("bets", bet.model_dump())
    _save(acc)
    return bet


def mark_bet(bet: Bet, yes_prob: float) -> Bet:
    """Refresh an open position's mark-to-market fields (does not touch cash)."""
    if bet.status != "pending":
        return bet
    bet.current_price = metrics.side_price(bet.side, yes_prob)
    bet.unrealized_pnl = metrics.mark_to_market(bet.side, bet.shares, bet.stake, yes_prob)
    db.put("bets", bet.model_dump())
    return bet


def settle_bet(bet: Bet, outcome: int) -> Bet:
    """Resolve a position: credit cash, realize P&L, mark resolved."""
    if bet.status == "resolved":
        return bet
    pnl = metrics.bet_pnl(bet.side, bet.stake, bet.entry_prob, outcome)
    credit = metrics.settle_cash_return(bet.side, bet.stake, bet.entry_prob, outcome)
    acc = get_or_init_account()
    acc.cash_balance += credit
    acc.realized_pnl += pnl
    bet.status = "resolved"
    bet.outcome = outcome  # type: ignore[assignment]
    bet.pnl = pnl
    bet.unrealized_pnl = None
    db.put("bets", bet.model_dump())
    _save(acc)
    return bet


def summary() -> dict:
    """Account + holdings overview for /api/account and the portfolio page."""
    acc = get_or_init_account()
    open_bets = [Bet(**b) for b in db.list_all("bets", status="pending")]
    open_value = 0.0
    for b in open_bets:
        price = b.current_price if b.current_price is not None else b.entry_prob
        open_value += b.shares * price
    equity = acc.cash_balance + open_value
    unrealized = sum((b.unrealized_pnl or 0.0) for b in open_bets)
    return {
        "starting_balance": round(acc.starting_balance, 2),
        "cash_balance": round(acc.cash_balance, 2),
        "open_positions_value": round(open_value, 2),
        "equity": round(equity, 2),
        "realized_pnl": round(acc.realized_pnl, 2),
        "unrealized_pnl": round(unrealized, 2),
        "return_pct": round((equity - acc.starting_balance) / acc.starting_balance * 100, 2),
        "open_count": len(open_bets),
    }
