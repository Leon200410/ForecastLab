"""Forecast engine (PRD §7-M3 + per-category agents).

Gathers evidence (M2) + RAG lessons, then runs the domain LangChain agent
(forecast/agents.py — routed by market.category) N times as an ensemble and
aggregates. The agent only analyses; betting stays the user's manual action.
"""
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from ..config import settings
from ..eval import calibration
from ..lib import db
from ..lib.cost_tracker import BudgetExceeded
from ..lib.models import Forecast, ForecastRun
from ..lib.util import clamp, extract_json, new_id, now_iso
from ..research import pipeline
from . import aggregate, agents, prompts


def _fit_calibrator():
    """Fit on already-resolved forecasts only (no leakage — they resolved before now)."""
    pts = [(f["agent_prob"], f["outcome"]) for f in db.list_all("forecasts", status="resolved")
           if f.get("outcome") is not None and f.get("agent_prob") is not None]
    return calibration.fit(pts)


def _valid_conf(v) -> str:
    return v if v in ("low", "med", "high") else "med"


def _repair_json(raw: str) -> Optional[dict]:
    """Last resort when an agent reply won't parse: ask a cheap model to reformat
    it into the required JSON. Cached + budget-checked like any other LLM call."""
    try:
        from ..providers.llm import get_llm
        fixed = get_llm().complete(
            "把下面内容改写成严格的 JSON(只输出一个 JSON 对象,无多余文字),键为 "
            "probability(0-1 浮点)、confidence(low|med|high)、rationale(字符串)、"
            "key_factors(字符串数组):\n\n" + raw[:4000],
            system="你是 JSON 格式化器,只输出一个合法 JSON 对象。",
            model=settings.cheap_model, temperature=0.0, max_tokens=800, purpose="json_repair")
        return extract_json(fixed)
    except BudgetExceeded:
        raise
    except Exception:
        return None


def _run_once(market: dict, ev_text: str, le_text: str, i: int,
              fresh: bool = False) -> Optional[ForecastRun]:
    final, _cat = agents.run_category_agent(
        market, ev_text, le_text, temperature=round(0.3 + 0.25 * i, 2), use_cache=not fresh)
    data = extract_json(final)
    if not data or "probability" not in data:
        data = _repair_json(final)
    if not data or "probability" not in data:
        return None
    try:
        return ForecastRun(
            probability=clamp(float(data["probability"]), 0.0, 1.0),
            confidence=_valid_conf(data.get("confidence")),
            rationale=str(data.get("rationale", ""))[:2000],
            key_factors=[str(x) for x in (data.get("key_factors") or [])][:8],
        )
    except (ValueError, TypeError):
        return None


def run_forecast(market: dict, on_event=None, fresh: bool = False) -> Forecast:
    """on_event(kind, data): optional progress callback (evidence/run/aggregate)
    for streaming. Called from worker threads too, so it must be thread-safe.
    fresh=True bypasses the agent-run cache so a re-analysis genuinely re-runs
    (evidence is still reused from cache to avoid re-paying for search)."""
    emit = on_event or (lambda *a, **k: None)
    evidence, lessons = pipeline.gather_evidence(market)
    emit("evidence", {"count": len(evidence), "lessons": len(lessons)})
    ev_text = "\n".join(f"- [{e.relevance}] {e.summary} (来源: {e.url})" for e in evidence) \
        or "(暂无检索到的证据)"
    le_text = "\n".join(f"- {l}" for l in lessons) or "(暂无过往复盘)"

    n = max(1, settings.ensemble_n)
    errors: list[str] = []
    err_lock = threading.Lock()

    def _task(i: int) -> Optional[ForecastRun]:
        try:
            r = _run_once(market, ev_text, le_text, i, fresh)
        except BudgetExceeded:
            raise            # hard cap — never mask it as a failed run
        except Exception as e:  # capture the REAL cause instead of silently dropping it
            with err_lock:
                errors.append(f"{type(e).__name__}: {e}")
            return None
        if r is None:
            with err_lock:
                errors.append("代理返回内容无法解析为 JSON")
        else:
            emit("run", {"i": i, "probability": r.probability, "confidence": r.confidence})
        return r

    # ensemble members are independent → run them concurrently (each is I/O-bound on the LLM API)
    with ThreadPoolExecutor(max_workers=n) as ex:
        runs: list[ForecastRun] = [r for r in ex.map(_task, range(n)) if r is not None]

    if not runs:
        # surface the first real underlying error (model/quota/recursion-limit/parse),
        # not a generic message — so the UI tells the user what actually went wrong.
        detail = errors[0] if errors else "代理未返回可解析的 JSON"
        raise RuntimeError(
            f"集成分析失败:{detail}(请检查 provider/key/quota,或调高 AGENT_RECURSION_LIMIT)")

    agg = aggregate.aggregate(runs)
    emit("aggregate", {"agent_prob": agg["agent_prob"], "confidence": agg["confidence"]})
    cal = _fit_calibrator()
    fc = Forecast(
        id=new_id("fc"),
        market_id=market["id"],
        agent_prob=agg["agent_prob"],
        agent_prob_calibrated=round(calibration.apply(agg["agent_prob"], cal), 4) if cal else None,
        market_prob_at_analysis=float(market.get("current_prob") or 0.5),
        confidence=agg["confidence"],
        rationale=agg["rationale"],
        key_factors=agg["key_factors"],
        runs=runs,
        prompt_version=prompts.PROMPT_VERSION,
        retrieved_lessons=lessons,
        evidence=evidence,
        created_at=now_iso(),
        status="pending",
    )
    db.put("forecasts", fc.model_dump())
    return fc
