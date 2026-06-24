"""Forecast engine (PRD §7-M3 + per-category agents).

Gathers evidence (M2) + RAG lessons, then runs the domain LangChain agent
(forecast/agents.py — routed by market.category) N times as an ensemble and
aggregates. The agent only analyses; betting stays the user's manual action.
"""
from ..config import settings
from ..lib import db
from ..lib.models import Forecast, ForecastRun
from ..lib.util import clamp, extract_json, new_id, now_iso
from ..research import pipeline
from . import aggregate, agents


def _valid_conf(v) -> str:
    return v if v in ("low", "med", "high") else "med"


def run_forecast(market: dict) -> Forecast:
    evidence, lessons = pipeline.gather_evidence(market)
    ev_text = "\n".join(f"- [{e.relevance}] {e.summary} (来源: {e.url})" for e in evidence) \
        or "(暂无检索到的证据)"
    le_text = "\n".join(f"- {l}" for l in lessons) or "(暂无过往复盘)"

    runs: list[ForecastRun] = []
    for i in range(max(1, settings.ensemble_n)):
        try:
            final, _cat = agents.run_category_agent(
                market, ev_text, le_text, temperature=round(0.3 + 0.25 * i, 2))
        except Exception:
            continue  # transient agent/provider error on one run — try the rest
        data = extract_json(final)
        if not data or "probability" not in data:
            continue
        try:
            runs.append(ForecastRun(
                probability=clamp(float(data["probability"]), 0.0, 1.0),
                confidence=_valid_conf(data.get("confidence")),
                rationale=str(data.get("rationale", ""))[:2000],
                key_factors=[str(x) for x in (data.get("key_factors") or [])][:8],
            ))
        except (ValueError, TypeError):
            continue

    if not runs:
        raise RuntimeError("forecast failed: no ensemble run returned parseable JSON "
                           "from the agent (check provider/key/quota).")

    agg = aggregate.aggregate(runs)
    fc = Forecast(
        id=new_id("fc"),
        market_id=market["id"],
        agent_prob=agg["agent_prob"],
        market_prob_at_analysis=float(market.get("current_prob") or 0.5),
        confidence=agg["confidence"],
        rationale=agg["rationale"],
        key_factors=agg["key_factors"],
        runs=runs,
        retrieved_lessons=lessons,
        evidence=evidence,
        created_at=now_iso(),
        status="pending",
    )
    db.put("forecasts", fc.model_dump())
    return fc
