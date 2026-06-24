"""Review generation + retrieval — the 'evolution' loop (PRD §7-M5 b/c).

generate_review(): on a resolved forecast, the Agent writes a post-mortem
(what happened / why / transferable lesson), stored and embedded into the KB.
retrieve_lessons(): pulled into the next forecast's prompt (M2 → M3).
"""
from typing import Optional

from ..config import settings
from ..lib import db
from ..lib.models import Forecast, Review
from ..lib.util import extract_json, now_iso
from ..providers.llm import get_llm
from . import store


def retrieve_lessons(question: str, k: int = 3, *, category: Optional[str] = None,
                     exclude_market_id: Optional[str] = None,
                     min_score: Optional[float] = None) -> list[str]:
    """Past-review lessons most similar to `question`, gated by a relevance floor
    and optionally restricted to the same category / excluding the market's own
    prior reviews (avoids feeding a market its own past lesson back to itself)."""
    floor = settings.kb_min_score if min_score is None else min_score
    out: list[str] = []
    for p in store.search(question, k=k * 4, min_score=floor):
        if exclude_market_id and p.get("market_id") == exclude_market_id:
            continue
        if category and p.get("category") and p.get("category") != category:
            continue
        if p.get("lesson"):
            out.append(p["lesson"])
        if len(out) >= k:
            break
    return out


def generate_review(forecast_id: str) -> Review:
    raw = db.get("forecasts", forecast_id)
    if raw is None:
        raise ValueError("forecast not found")
    fc = Forecast(**raw)
    if fc.status != "resolved" or fc.outcome is None:
        raise ValueError("forecast is not resolved yet")

    market = db.get("markets", fc.market_id) or {}
    bets = db.list_all("bets", forecast_id=forecast_id)
    bet_pnl: Optional[float] = bets[0].get("pnl") if bets else None

    evidence_txt = "\n".join(f"- {e.summary}" for e in fc.evidence[:6]) or "(无)"
    outcome_label = "YES (1)" if fc.outcome == 1 else "NO (0)"
    prompt = (
        "对一次已揭晓的预测做复盘,提炼可迁移的教训。只输出 JSON:"
        '{"what_happened":"...","why":"...","lesson":"..."}\n\n'
        f"问题:{fc.market_id} — {market.get('question', '')}\n"
        f"Agent 当时的 YES 概率:{fc.agent_prob}\n"
        f"分析时市场价:{fc.market_prob_at_analysis}\n"
        f"实际结果:{outcome_label}\n"
        f"Agent Brier:{fc.brier} / 市场 Brier:{fc.market_brier}\n"
        f"当时证据:\n{evidence_txt}\n"
    )
    raw_txt = get_llm().complete(prompt, purpose="review", model=settings.forecaster_model,
                                 temperature=0.4, max_tokens=500)
    data = extract_json(raw_txt) or {}

    review = Review(
        forecast_id=forecast_id,
        market_id=fc.market_id,
        question=market.get("question", ""),
        agent_prob=fc.agent_prob,
        outcome=fc.outcome,
        agent_brier=fc.brier if fc.brier is not None else 0.0,
        market_brier=fc.market_brier if fc.market_brier is not None else 0.0,
        bet_pnl=bet_pnl,
        what_happened=str(data.get("what_happened", ""))[:1000],
        why=str(data.get("why", ""))[:1000],
        lesson=str(data.get("lesson", "(无)"))[:600],
        created_at=now_iso(),
    )

    record = review.model_dump()
    record.update({"id": forecast_id})  # one review per forecast
    db.put("reviews", record)

    fc.reviewed = True
    db.put("forecasts", fc.model_dump())

    # embed the question only — the retrieval query is also a question, so this
    # keeps key/query symmetric (the lesson text lives in the payload, not the vector).
    store.add(review.question,
              {"lesson": review.lesson, "question": review.question, "forecast_id": forecast_id,
               "market_id": fc.market_id, "category": market.get("category"),
               "created_at": review.created_at})
    return review
