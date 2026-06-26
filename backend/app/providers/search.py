"""Search provider — real only (Tavily / Serper).

No mock results. A genuine empty result set (provider returned 200 with no hits)
comes back as []. Any *failure* — quota/rate-limit/auth (HTTP 4xx), server or
network error, malformed response — raises SearchUnavailable, so callers can tell
"search is down" apart from "nothing found". The latter must never be inferred
from the former: that is how a quota outage turns into a confidently wrong "NO".
Results are cached on disk. get_search() raises if search isn't configured.
"""
import httpx

from ..config import settings
from ..lib import cache


class SearchUnavailable(RuntimeError):
    """Search could not be performed (quota/auth/rate-limit/network/malformed),
    as opposed to a successful search that genuinely returned zero results."""


def _provider_error(resp: httpx.Response) -> str:
    """Best-effort human-readable provider error (Tavily: detail.error; Serper: message)."""
    try:
        body = resp.json()
        detail = body.get("detail", body) if isinstance(body, dict) else body
        if isinstance(detail, dict):
            return str(detail.get("error") or detail.get("message") or detail)
        return str(detail)
    except (ValueError, AttributeError):
        return resp.text[:200]


class HttpSearch:
    def __init__(self, provider: str, api_key: str) -> None:
        self.mode = provider
        self.api_key = api_key

    def search(self, query: str, k: int = 5) -> list[dict]:
        hit = cache.get_cached("search", self.mode, query, k)
        if hit is not None:
            return hit
        try:
            results = self._tavily(query, k) if self.mode == "tavily" else self._serper(query, k)
        except httpx.HTTPStatusError as e:
            # provider rejected us — quota (432) / rate-limit (429) / auth (401,403) / bad-request.
            # NONE of these mean "no results" (that is a 200 with an empty array).
            raise SearchUnavailable(
                f"{self.mode} HTTP {e.response.status_code}: {_provider_error(e.response)}") from e
        except (httpx.HTTPError, KeyError, ValueError) as e:
            # network/timeout/malformed response — outcome unknown, NOT "no evidence".
            raise SearchUnavailable(f"{self.mode}: {type(e).__name__}: {e}") from e
        cache.set_cached(results, "search", self.mode, query, k)
        return results

    def _tavily(self, query: str, k: int) -> list[dict]:
        r = httpx.post("https://api.tavily.com/search", timeout=20, json={
            "api_key": self.api_key, "query": query, "max_results": k,
        })
        r.raise_for_status()
        return [{"title": x.get("title", ""), "url": x.get("url", ""),
                 "snippet": x.get("content", "")} for x in r.json().get("results", [])]

    def _serper(self, query: str, k: int) -> list[dict]:
        r = httpx.post("https://google.serper.dev/search", timeout=20,
                       headers={"X-API-KEY": self.api_key},
                       json={"q": query, "num": k})
        r.raise_for_status()
        return [{"title": x.get("title", ""), "url": x.get("link", ""),
                 "snippet": x.get("snippet", "")} for x in r.json().get("organic", [])[:k]]


class FallbackSearch:
    """Try each provider in order; the first non-empty result wins. A provider that is
    unavailable (quota/auth/network) is skipped and the next is tried, so one provider
    being down no longer means no evidence. Only when EVERY provider is unavailable do we
    raise SearchUnavailable; if some responded but none had hits, that's a genuine []."""

    def __init__(self, chain: list[tuple[str, str]]) -> None:
        self.engines = [HttpSearch(provider, key) for provider, key in chain]

    def search(self, query: str, k: int = 5) -> list[dict]:
        errors: list[str] = []
        responded = False
        for eng in self.engines:
            try:
                results = eng.search(query, k)
            except SearchUnavailable as e:
                errors.append(str(e))
                continue
            responded = True
            if results:
                return results
        if not responded:           # every provider was unavailable — surface the outage
            raise SearchUnavailable(" / ".join(errors) or "no search providers configured")
        return []                   # at least one responded, nothing found → genuine empty


_search = None


def get_search():
    global _search
    if _search is None:
        chain = settings.search_chain
        if not chain:
            raise RuntimeError(
                "Search not configured — set SEARCH_PROVIDER + a key "
                "(TAVILY_API_KEY / SERPER_API_KEY, or SEARCH_API_KEY) in .env.")
        _search = FallbackSearch(chain)
    return _search
