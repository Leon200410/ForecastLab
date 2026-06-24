"""Evidence research pipeline (PRD §7-M2).

query-gen → (parallel) search → (parallel) fetch → (parallel) assess → Evidence[]
Each per-article `assess` is ONE cheap-model call returning relevance + summary.
Also retrieves relevant past-review lessons from the RAG KB to inject downstream.
Everything cached; the per-stage fan-out keeps wall-clock ≈ the slowest item per
wave instead of the sum of every call.
"""
from concurrent.futures import ThreadPoolExecutor

from ..config import settings
from ..kb import review as kb_review
from ..lib.cost_tracker import BudgetExceeded
from ..lib.models import Evidence
from ..lib.util import clamp, extract_json, today_str
from ..providers.fetch import fetch_text
from ..providers.llm import get_llm
from ..providers.search import get_search
from ..forecast import prompts


def gen_queries(question: str, description: str | None) -> list[str]:
    prompt = prompts.QUERY_GEN_TMPL.format(
        today=today_str(), question=question, description=(description or "")[:400])
    raw = get_llm().complete(prompt, purpose="query_gen", model=settings.cheap_model,
                             temperature=0.3, max_tokens=300)
    data = extract_json(raw) or {}
    queries = [q for q in (data.get("queries") or []) if isinstance(q, str) and q.strip()]
    return queries[:5] or [question]


def assess(question: str, title: str, text: str) -> tuple[float, str]:
    """One cheap-model call → (relevance 0..1, summary). Replaces the old
    separate score_relevance + summarize, halving per-article LLM calls."""
    prompt = prompts.ASSESS_TMPL.format(question=question, title=title, text=text[:1500])
    raw = get_llm().complete(prompt, purpose="assess", model=settings.cheap_model,
                             temperature=0.2, max_tokens=260)
    data = extract_json(raw) or {}
    try:
        rel = clamp(float(data.get("relevance")), 0.0, 1.0)
    except (TypeError, ValueError):
        rel = 0.5  # mirror old score_relevance fallback: unparseable → neutral, don't silently drop
    return rel, str(data.get("summary", "")).strip()


def _safe_search(search, query: str, k: int) -> list[dict]:
    try:
        return search.search(query, k)
    except Exception:
        return []


def _safe_fetch(hit: dict) -> str:
    try:
        return fetch_text(hit.get("url", "")) or hit.get("snippet", "")
    except Exception:
        return ""


def _assess_one(market: dict, question: str, hit: dict, text: str,
                min_relevance: float) -> Evidence | None:
    try:
        rel, summary = assess(question, hit.get("title", ""), text)
    except BudgetExceeded:
        raise            # hard cap must propagate — never mask it as a dropped article
    except Exception:
        return None      # transient LLM/parse error → drop just this article
    if rel < min_relevance or not summary:
        return None
    return Evidence(market_id=market["id"], url=hit.get("url", ""), title=hit.get("title", ""),
                    summary=summary, relevance=round(rel, 3))


def gather_evidence(market: dict, k_per_query: int = 3, min_relevance: float = 0.4,
                    max_articles: int = 8) -> tuple[list[Evidence], list[str]]:
    question = market["question"]
    queries = gen_queries(question, market.get("description"))   # serial seed (1 LLM call)
    search = get_search()                                        # init singleton single-threaded

    # A — search every query concurrently
    with ThreadPoolExecutor(max_workers=min(len(queries), 5)) as ex:
        per_query = list(ex.map(lambda q: _safe_search(search, q, k_per_query), queries))

    # B — dedup by URL (single-threaded → `seen` needs no lock) then cap the candidate pool
    seen: set[str] = set()
    candidates: list[dict] = []
    for hits in per_query:
        for hit in hits:
            url = hit.get("url", "")
            if url and url not in seen:
                seen.add(url)
                candidates.append(hit)
    candidates = candidates[:max_articles + 4]   # light over-fetch to survive the relevance filter

    # C — fetch article bodies concurrently (fall back to snippet; drop empties)
    with ThreadPoolExecutor(max_workers=min(8, len(candidates) or 1)) as ex:
        texts = list(ex.map(_safe_fetch, candidates))
    pairs = [(hit, text) for hit, text in zip(candidates, texts) if text]

    # E — combined relevance+summary, one LLM call per article, concurrently
    with ThreadPoolExecutor(max_workers=min(8, len(pairs) or 1)) as ex:
        results = list(ex.map(
            lambda pt: _assess_one(market, question, pt[0], pt[1], min_relevance), pairs))

    evidence = [e for e in results if e is not None]
    evidence.sort(key=lambda e: e.relevance, reverse=True)   # deterministic, most-relevant first
    evidence = evidence[:max_articles]

    lessons = kb_review.retrieve_lessons(question, k=3, category=market.get("category"),
                                         exclude_market_id=market.get("id"))
    return evidence, lessons
