"""Pure scoring math — no I/O, fully unit-tested (PRD §11). Stdlib only.

Two independent lines:
  - Agent analysis quality: Brier / log-loss / accuracy / calibration (vs market)
  - User betting: realized P&L and mark-to-market, for the virtual portfolio
"""
import math


# ---- forecast scoring -------------------------------------------------------
def brier(prob: float, outcome: int) -> float:
    """Brier score for one binary forecast. Lower is better."""
    return (prob - outcome) ** 2


def log_loss(prob: float, outcome: int, eps: float = 1e-15) -> float:
    p = min(1 - eps, max(eps, prob))
    return -(outcome * math.log(p) + (1 - outcome) * math.log(1 - p))


def accuracy(prob: float, outcome: int) -> int:
    return int((1 if prob >= 0.5 else 0) == outcome)


def calibration(points: list[tuple[float, int]], n_buckets: int = 10) -> list[dict]:
    """Bucket predictions into [0,1] bins → (mean predicted prob, observed freq, count)."""
    buckets: list[dict] = []
    for b in range(n_buckets):
        lo, hi = b / n_buckets, (b + 1) / n_buckets
        sel = [(p, o) for (p, o) in points if (lo <= p < hi or (b == n_buckets - 1 and p == 1.0))]
        if sel:
            buckets.append({
                "bucket": b,
                "lo": round(lo, 3), "hi": round(hi, 3),
                "mean_pred": round(sum(p for p, _ in sel) / len(sel), 4),
                "freq": round(sum(o for _, o in sel) / len(sel), 4),
                "count": len(sel),
            })
    return buckets


def _brier_mean(rows: list[dict], key: str) -> float:
    return round(sum(brier(r[key], r["outcome"]) for r in rows) / len(rows), 4)


def summarize_forecasts(resolved: list[dict]) -> dict:
    """`resolved`: list of {agent_prob, market_prob, outcome, [agent_prob_cal],
    [prompt_version]}. Returns agent vs market, plus calibrated Brier and a
    per-prompt-version breakdown when those extra fields are present."""
    n = len(resolved)
    if n == 0:
        return {"n": 0}
    ab = _brier_mean(resolved, "agent_prob")
    mb = _brier_mean(resolved, "market_prob")
    acc = sum(accuracy(r["agent_prob"], r["outcome"]) for r in resolved) / n
    ll = sum(log_loss(r["agent_prob"], r["outcome"]) for r in resolved) / n
    out = {
        "n": n,
        "agent_brier": ab,
        "market_brier": mb,
        "beats_market": ab < mb,
        "accuracy": round(acc, 4),
        "log_loss": round(ll, 4),
        "calibration": calibration([(r["agent_prob"], r["outcome"]) for r in resolved]),
    }
    # calibrated Brier over forecasts that carried a calibrated prob — does it help?
    cal = [r for r in resolved if r.get("agent_prob_cal") is not None]
    if cal:
        out["n_calibrated"] = len(cal)
        out["agent_brier_calibrated"] = _brier_mean(cal, "agent_prob_cal")
    # per-prompt-version breakdown so prompt iterations can be compared head-to-head
    versions: dict[str, list[dict]] = {}
    for r in resolved:
        versions.setdefault(r.get("prompt_version") or "?", []).append(r)
    if len(versions) > 1:
        out["by_version"] = {
            v: {"n": len(rs), "agent_brier": _brier_mean(rs, "agent_prob"),
                "market_brier": _brier_mean(rs, "market_prob")}
            for v, rs in sorted(versions.items())
        }
    return out


# ---- betting / portfolio math ----------------------------------------------
def side_price(side: str, yes_prob: float) -> float:
    """Market price of the held side given the YES implied prob."""
    return yes_prob if side == "YES" else 1.0 - yes_prob


def shares_for(stake: float, entry_prob: float) -> float:
    return stake / entry_prob if entry_prob > 0 else 0.0


def is_correct(side: str, outcome: int) -> bool:
    return (side == "YES" and outcome == 1) or (side == "NO" and outcome == 0)


def bet_pnl(side: str, stake: float, entry_prob: float, outcome: int) -> float:
    """Realized P&L. Win pays shares*$1 (= stake/entry_prob), so profit = stake*(1-p)/p."""
    if is_correct(side, outcome):
        return stake * (1.0 - entry_prob) / entry_prob
    return -stake


def settle_cash_return(side: str, stake: float, entry_prob: float, outcome: int) -> float:
    """Cash credited back to the account on resolution (stake was debited at open)."""
    return stake / entry_prob if is_correct(side, outcome) else 0.0


def mark_to_market(side: str, shares: float, stake: float, yes_prob: float) -> float:
    """Unrealized P&L for an open position at the current market price."""
    return shares * side_price(side, yes_prob) - stake
