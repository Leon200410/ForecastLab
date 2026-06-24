"""Offline backtest / analysis harness (A4).

Reads already-resolved forecasts from the local DB and reports forecast quality
WITHOUT any network or LLM call: raw vs calibrated Brier, agent vs market, a
per-prompt-version breakdown, and the reliability table. This is the judge the
roadmap mandates — any prompt/orchestration change must not regress Brier here
before it ships.

Run from the backend/ directory:  python scripts/backtest.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make `app` importable

from app.eval import calibration, metrics  # noqa: E402
from app.lib import db  # noqa: E402


def load_resolved() -> list[dict]:
    rows: list[dict] = []
    for f in db.list_all("forecasts", status="resolved"):
        if f.get("outcome") is None or f.get("agent_prob") is None:
            continue
        rows.append({
            "agent_prob": f["agent_prob"],
            "market_prob": f["market_prob_at_analysis"],
            "outcome": f["outcome"],
            "agent_prob_cal": f.get("agent_prob_calibrated"),
            "prompt_version": f.get("prompt_version"),
        })
    return rows


def main() -> None:
    db.init_db()
    resolved = load_resolved()
    if not resolved:
        print("No resolved forecasts in the DB yet — nothing to backtest.")
        return

    s = metrics.summarize_forecasts(resolved)
    print(f"\n=== Backtest over {s['n']} resolved forecasts ===")
    print(f"  agent Brier  : {s['agent_brier']:.4f}")
    print(f"  market Brier : {s['market_brier']:.4f}   "
          f"({'agent beats market' if s['beats_market'] else 'market wins'})")
    print(f"  accuracy     : {s['accuracy'] * 100:.1f}%")
    print(f"  log loss     : {s['log_loss']:.4f}")
    if "agent_brier_calibrated" in s:
        delta = s["agent_brier"] - s["agent_brier_calibrated"]
        verb = "better" if delta > 0 else "worse"
        print(f"  calibrated Brier (n={s['n_calibrated']}): {s['agent_brier_calibrated']:.4f}  "
              f"({verb} by {abs(delta):.4f})")

    cal = calibration.fit([(r["agent_prob"], r["outcome"]) for r in resolved])
    print(f"  calibrator   : {'fitted' if cal else f'not fitted (need >= {calibration.MIN_SAMPLES})'}")

    if "by_version" in s:
        print("\n  by prompt_version:")
        for v, d in s["by_version"].items():
            print(f"    {v:>6}: n={d['n']:<4} agent {d['agent_brier']:.4f} vs market {d['market_brier']:.4f}")

    print("\n  reliability (predicted -> observed):")
    for b in s["calibration"]:
        print(f"    [{b['lo']:.1f},{b['hi']:.1f}) n={b['count']:<4} "
              f"pred {b['mean_pred']:.3f} -> obs {b['freq']:.3f}")
    print()


if __name__ == "__main__":
    main()
