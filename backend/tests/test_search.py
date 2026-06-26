"""HttpSearch: a failure (quota/auth/rate-limit/network) must raise
SearchUnavailable, never masquerade as an empty result set — otherwise a Tavily
quota outage (HTTP 432) becomes a confidently wrong "NO" forecast. A genuine
200 + empty array is the ONLY thing that legitimately returns [].
"""
import httpx
import pytest

from app.forecast import agents
from app.providers import search as search_mod
from app.providers.search import FallbackSearch, HttpSearch, SearchUnavailable


@pytest.fixture(autouse=True)
def _tmp_cache(tmp_path, monkeypatch):
    # isolate the on-disk search cache so tests don't read/write the real one
    monkeypatch.setattr(search_mod.settings, "cache_dir", tmp_path)


def _resp(status, json_body):
    return httpx.Response(status, request=httpx.Request("POST", "https://x"), json=json_body)


def test_quota_432_raises_with_provider_message(monkeypatch):
    monkeypatch.setattr(search_mod.httpx, "post", lambda *a, **k: _resp(
        432, {"detail": {"error": "This request exceeds your plan's set usage limit."}}))
    with pytest.raises(SearchUnavailable) as e:
        HttpSearch("tavily", "k").search("q", 4)
    assert "432" in str(e.value) and "usage limit" in str(e.value)


@pytest.mark.parametrize("status", [401, 403, 429])
def test_auth_and_ratelimit_raise(monkeypatch, status):
    monkeypatch.setattr(search_mod.httpx, "post", lambda *a, **k: _resp(status, {"detail": "nope"}))
    with pytest.raises(SearchUnavailable):
        HttpSearch("tavily", "k").search("q", 4)


def test_network_error_raises(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("connection refused")
    monkeypatch.setattr(search_mod.httpx, "post", boom)
    with pytest.raises(SearchUnavailable):
        HttpSearch("tavily", "k").search("q", 4)


def test_genuine_empty_returns_empty_list(monkeypatch):
    monkeypatch.setattr(search_mod.httpx, "post", lambda *a, **k: _resp(200, {"results": []}))
    assert HttpSearch("tavily", "k").search("q", 4) == []  # 200 + empty IS the only legit []


def test_success_maps_results(monkeypatch):
    monkeypatch.setattr(search_mod.httpx, "post", lambda *a, **k: _resp(
        200, {"results": [{"title": "T", "url": "u", "content": "c"}]}))
    assert HttpSearch("tavily", "k").search("q", 4) == [{"title": "T", "url": "u", "snippet": "c"}]


def _serper_hit(url, *a, **k):
    """Route a fake httpx.post by URL: tavily vs serper, each with its own schema."""
    if "tavily" in url:
        return _resp(432, {"detail": {"error": "exceeds your plan's set usage limit"}})
    return _resp(200, {"organic": [{"title": "S", "link": "u", "snippet": "c"}]})


def test_fallback_primary_down_uses_secondary(monkeypatch):
    """Tavily down (432) → Serper result is used. One provider being down no longer
    means no evidence (the fragility the user flagged)."""
    monkeypatch.setattr(search_mod.httpx, "post", _serper_hit)
    out = FallbackSearch([("tavily", "kt"), ("serper", "ks")]).search("q", 4)
    assert out == [{"title": "S", "url": "u", "snippet": "c"}]


def test_fallback_primary_empty_uses_secondary(monkeypatch):
    """Tavily online but 0 hits → try Serper for recall (the 证据(0) case)."""
    def post(url, *a, **k):
        if "tavily" in url:
            return _resp(200, {"results": []})
        return _resp(200, {"organic": [{"title": "S", "link": "u", "snippet": "c"}]})
    monkeypatch.setattr(search_mod.httpx, "post", post)
    out = FallbackSearch([("tavily", "kt"), ("serper", "ks")]).search("q", 4)
    assert out and out[0]["title"] == "S"


def test_fallback_all_down_raises(monkeypatch):
    monkeypatch.setattr(search_mod.httpx, "post", lambda *a, **k: _resp(429, {"detail": "rate"}))
    with pytest.raises(SearchUnavailable):
        FallbackSearch([("tavily", "kt"), ("serper", "ks")]).search("q", 4)


def test_fallback_all_empty_returns_empty(monkeypatch):
    def post(url, *a, **k):
        return _resp(200, {"results": []} if "tavily" in url else {"organic": []})
    monkeypatch.setattr(search_mod.httpx, "post", post)
    assert FallbackSearch([("tavily", "kt"), ("serper", "ks")]).search("q", 4) == []


def test_web_search_tool_reports_outage_not_no_results(monkeypatch):
    """The agent-facing tool must surface the outage, never return "(无结果)" —
    that string is exactly what made the agent infer a false NO."""
    class _Down:
        def search(self, q, k):
            raise SearchUnavailable("tavily HTTP 432: exceeds your plan's set usage limit")

    monkeypatch.setattr(agents, "get_search", lambda: _Down())
    out = agents.web_search.func("q")
    assert "不可用" in out
    assert "(无结果)" not in out
    assert not out.startswith("检索失败")  # took the SearchUnavailable branch, not the generic one
