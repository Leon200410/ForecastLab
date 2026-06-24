"""Pure scoring math (PRD §11): Brier, log-loss, accuracy, P&L, mark-to-market."""
import math

import pytest

from app.eval import metrics


def test_brier_basic():
    assert metrics.brier(0.0, 0) == 0.0
    assert metrics.brier(1.0, 1) == 0.0
    assert metrics.brier(0.5, 1) == pytest.approx(0.25)
    assert metrics.brier(0.8, 0) == pytest.approx(0.64)


def test_log_loss_and_accuracy():
    assert metrics.log_loss(0.5, 1) == pytest.approx(math.log(2), rel=1e-6)
    assert metrics.accuracy(0.7, 1) == 1
    assert metrics.accuracy(0.4, 1) == 0
    assert metrics.accuracy(0.5, 0) == 0  # >=0.5 predicts 1


def test_bet_pnl_yes_no():
    # YES correct: profit = stake*(1-p)/p
    assert metrics.bet_pnl("YES", 100, 0.5, 1) == pytest.approx(100.0)
    assert metrics.bet_pnl("YES", 100, 0.5, 0) == pytest.approx(-100.0)
    # NO correct at side price 0.4 -> 100*0.6/0.4 = 150
    assert metrics.bet_pnl("NO", 100, 0.4, 0) == pytest.approx(150.0)
    assert metrics.bet_pnl("NO", 100, 0.4, 1) == pytest.approx(-100.0)


def test_shares_side_price_settle():
    assert metrics.shares_for(100, 0.5) == pytest.approx(200.0)
    assert metrics.side_price("YES", 0.7) == pytest.approx(0.7)
    assert metrics.side_price("NO", 0.7) == pytest.approx(0.3)
    assert metrics.settle_cash_return("YES", 100, 0.5, 1) == pytest.approx(200.0)
    assert metrics.settle_cash_return("YES", 100, 0.5, 0) == 0.0


def test_mark_to_market():
    shares = metrics.shares_for(100, 0.5)  # 200
    # price moves to 0.6 in our favor -> unrealized = 200*0.6 - 100 = 20
    assert metrics.mark_to_market("YES", shares, 100, 0.6) == pytest.approx(20.0)
    # against us to 0.4 -> 200*0.4 - 100 = -20
    assert metrics.mark_to_market("YES", shares, 100, 0.4) == pytest.approx(-20.0)


def test_pnl_consistency_with_settlement():
    # realized pnl == cash credited minus stake originally debited
    for side, p, out in [("YES", 0.3, 1), ("YES", 0.3, 0), ("NO", 0.45, 0), ("NO", 0.45, 1)]:
        pnl = metrics.bet_pnl(side, 100, p, out)
        credited = metrics.settle_cash_return(side, 100, p, out)
        assert pnl == pytest.approx(credited - 100)


def test_summarize_forecasts_beats_market():
    # agent perfectly right, market at 0.5 -> agent brier 0 < market 0.25
    resolved = [
        {"agent_prob": 1.0, "market_prob": 0.5, "outcome": 1},
        {"agent_prob": 0.0, "market_prob": 0.5, "outcome": 0},
    ]
    s = metrics.summarize_forecasts(resolved)
    assert s["n"] == 2
    assert s["agent_brier"] == pytest.approx(0.0)
    assert s["market_brier"] == pytest.approx(0.25)
    assert s["beats_market"] is True
    assert s["accuracy"] == pytest.approx(1.0)


def test_calibration_buckets():
    points = [(0.05, 0), (0.95, 1), (0.95, 1), (0.55, 1)]
    buckets = metrics.calibration(points, n_buckets=10)
    assert sum(b["count"] for b in buckets) == 4
    top = [b for b in buckets if b["lo"] == 0.9][0]
    assert top["freq"] == pytest.approx(1.0)
