"""Search provider — real only (Tavily / Serper).

No mock results. On a transient API error returns [] (honest: no evidence, not
fake evidence). get_search() raises if search isn't configured with a key.
Results are cached on disk.
"""
import httpx

from ..config import settings
from ..lib import cache


class HttpSearch:
    def __init__(self, provider: str) -> None:
        self.mode = provider

    def search(self, query: str, k: int = 5) -> list[dict]:
        hit = cache.get_cached("search", self.mode, query, k)
        if hit is not None:
            return hit
        try:
            results = self._tavily(query, k) if self.mode == "tavily" else self._serper(query, k)
        except (httpx.HTTPError, KeyError, ValueError):
            return []  # transient failure -> no evidence (never fabricated)
        cache.set_cached(results, "search", self.mode, query, k)
        return results

    def _tavily(self, query: str, k: int) -> list[dict]:
        r = httpx.post("https://api.tavily.com/search", timeout=20, json={
            "api_key": settings.search_api_key, "query": query, "max_results": k,
        })
        r.raise_for_status()
        return [{"title": x.get("title", ""), "url": x.get("url", ""),
                 "snippet": x.get("content", "")} for x in r.json().get("results", [])]

    def _serper(self, query: str, k: int) -> list[dict]:
        r = httpx.post("https://google.serper.dev/search", timeout=20,
                       headers={"X-API-KEY": settings.search_api_key},
                       json={"q": query, "num": k})
        r.raise_for_status()
        return [{"title": x.get("title", ""), "url": x.get("link", ""),
                 "snippet": x.get("snippet", "")} for x in r.json().get("organic", [])[:k]]


_search = None


def get_search():
    global _search
    if _search is None:
        if not settings.search_ready:
            raise RuntimeError(
                "Search not configured — set SEARCH_PROVIDER=tavily|serper + SEARCH_API_KEY in .env.")
        _search = HttpSearch(settings.search_mode)
    return _search
