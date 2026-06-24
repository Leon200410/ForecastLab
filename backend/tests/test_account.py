"""Virtual account: open (debit), mark-to-market, settle (credit), guards."""
import pytest

from app.lib import db
from app.lib.models import Bet
from app.lib.util import now_iso
from app.portfolio import account


def _seed_forecast(market_id="m1", forecast_id="f1", price=0.5):
    db.put("markets", {"id": market_id, "question": "q?", "status": "open",
                       "current_prob": price, "created_at": now_iso()})
    db.put("forecasts", {"id": forecast_id, "market_id": market_id, "agent_prob": 0.6,
                         "market_prob_at_analysis": price, "confidence": "med", "rationale": "",
                         "key_factors": [], "runs": [], "retrieved_lessons": [], "evidence": [],
                         "created_at": now_iso(), "status": "pending"})
    return forecast_id


def test_account_starts_at_balance():
    acc = account.get_or_init_account()
    assert acc.cash_balance == acc.starting_balance


def test_place_bet_debits_and_sets_shares():
    fid = _seed_forecast(price=0.5)
    start = account.get_or_init_account().cash_balance
    bet = account.place_bet(fid, "YES", 100.0, 0.5)
    assert bet.shares == pytest.approx(200.0)
    assert account.get_or_init_account().cash_balance == pytest.approx(start - 100.0)


def test_one_bet_per_forecast():
    fid = _seed_forecast()
    account.place_bet(fid, "YES", 100.0, 0.5)
    with pytest.raises(account.BetError):
        account.place_bet(fid, "NO", 50.0, 0.5)


def test_insufficient_balance_rejected():
    fid = _seed_forecast()
    with pytest.raises(account.BetError):
        account.place_bet(fid, "YES", 1_000_000.0, 0.5)


def test_settle_credits_and_realizes_pnl():
    fid = _seed_forecast(price=0.5)
    bet = account.place_bet(fid, "YES", 100.0, 0.5)
    account.settle_bet(bet, outcome=1)
    acc = account.get_or_init_account()
    # debited 100, credited 200 -> net +100, realized +100, back above starting
    assert acc.realized_pnl == pytest.approx(100.0)
    assert acc.cash_balance == pytest.approx(acc.starting_balance + 100.0)
    summ = account.summary()
    assert summ["return_pct"] == pytest.approx(1.0)  # +100 on 10000


def test_mark_to_market_updates_unrealized():
    fid = _seed_forecast(price=0.5)
    bet = account.place_bet(fid, "YES", 100.0, 0.5)
    account.mark_bet(bet, yes_prob=0.6)
    refreshed = Bet(**db.get("bets", bet.id))
    assert refreshed.unrealized_pnl == pytest.approx(20.0)
    assert account.summary()["unrealized_pnl"] == pytest.approx(20.0)
