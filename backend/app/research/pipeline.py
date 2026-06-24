"""Evidence research pipeline (PRD §7-M2).

query-gen → search → fetch → relevance-filter → summarize → Evidence[]
Also retrieves relevant past-review lessons from the RAG KB to inject downstream.
Cheap model (Haiku) for filter/summarize; everything cached.
"""
import re

from ..config import settings
from ..kb import review as kb_review
from ..lib.models import Evidence
from ..lib.util import clamp, extract_json, today_str
from ..providers.fetch import fetch_text
from ..providers.llm import get_llm
from ..providers.search import get_search


def gen_queries(question: str, description: str | None) -> list[str]:
    prompt = (
        f"今天是 {today_str()}。为下面的预测问题生成 3-5 个用于检索**最新**证据的搜索查询"
        "(尽量带上年份/时间以命中近期信息,避免拉到过时内容)。只输出 JSON "
        '{"queries":["...","..."]}。\n'
        f"问题:{question}\n背景:{(description or '')[:400]}"
    )
    raw = get_llm().complete(prompt, purpose="query_gen", model=settings.cheap_model,
                             temperature=0.3, max_tokens=300)
    data = extract_json(raw) or {}
    queries = [q for q in (data.get("queries") or []) if isinstance(q, str) and q.strip()]
    return queries[:5] or [question]


def score_relevance(question: str, text: str) -> float:
    prompt = (f"问题:{question}\n文章片段:{text[:800]}\n"
              "这篇与问题的相关性打分(0 到 1 的小数),只输出数字:")
    raw = get_llm().complete(prompt, purpose="relevance", model=settings.cheap_model,
                             temperature=0.0, max_tokens=32)
    m = re.search(r"[0-9]*\.?[0-9]+", raw or "")
    return clamp(float(m.group()), 0.0, 1.0) if m else 0.5


def summarize(question: str, title: str, text: str) -> str:
    prompt = (f"用一段话总结这篇与「{question}」相关的要点(尽量含时间与来源指向):\n"
              f"标题:{title}\n正文:{text[:1500]}")
    return get_llm().complete(prompt, purpose="summarize", model=settings.cheap_model,
                              temperature=0.2, max_tokens=220).strip()


def gather_evidence(market: dict, k_per_query: int = 3, min_relevance: float = 0.4,
                    max_articles: int = 8) -> tuple[list[Evidence], list[str]]:
    question = market["question"]
    queries = gen_queries(question, market.get("description"))
    search = get_search()
    seen: set[str] = set()
    evidence: list[Evidence] = []

    for q in queries:
        for hit in search.search(q, k_per_query):
            url = hit.get("url", "")
            if not url or url in seen:
                continue
            seen.add(url)
            text = fetch_text(url) or hit.get("snippet", "")
            if not text:
                continue
            rel = score_relevance(question, text)
            if rel < min_relevance:
                continue
            evidence.append(Evidence(
                market_id=market["id"], url=url, title=hit.get("title", ""),
                summary=summarize(question, hit.get("title", ""), text), relevance=round(rel, 3),
            ))
            if len(evidence) >= max_articles:
                break
        if len(evidence) >= max_articles:
            break

    lessons = kb_review.retrieve_lessons(question, k=3)
    return evidence, lessons
