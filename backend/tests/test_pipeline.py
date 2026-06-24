"""Evidence pipeline — concurrent gather_evidence (search/fetch/assess fan-out).

External deps (get_llm / get_search / fetch_text) are mocked, so these are
offline and deterministic. retrieve_lessons runs against the empty test KB → [].
"""
import re

import pytest

from app.lib.cost_tracker import BudgetExceeded
from app.research import pipeline

_GENQ = "为下面的预测问题生成"  # marker that distinguishes the gen_queries prompt from assess


# rel encoded in each url's fetched body; assess parses it back out of the prompt
RELS = {"u0": 0.9, "u1": 0.7, "u2": 0.5, "u3": 0.3, "u4": 0.1}


class _FakeLLM:
    def __init__(self):
        self.assess_calls = 0

    def complete(self, prompt, **kw):
        if _GENQ in prompt:
            return '{"queries":["q1","q2"]}'
        self.assess_calls += 1
        m = re.search(r"REL=([0-9.]+)", prompt)
        return '{"relevance": ' + (m.group(1) if m else "0.5") + ', "summary": "s"}'


class _FakeSearch:
    def search(self, query, k):
        return [{"url": u, "title": f"t-{u}", "snippet": ""} for u in RELS]


@pytest.fixture
def fake_llm(monkeypatch):
    llm = _FakeLLM()
    monkeypatch.setattr(pipeline, "get_llm", lambda: llm)
    monkeypatch.setattr(pipeline, "get_search", lambda: _FakeSearch())
    monkeypatch.setattr(pipeline, "fetch_text", lambda url, *a, **k: f"REL={RELS.get(url, 0.5)} body")
    return llm


def test_ranks_filters_caps_and_one_call_per_article(fake_llm):
    market = {"id": "m1", "question": "Q?", "description": "", "category": "加密"}
    evidence, lessons = pipeline.gather_evidence(market, k_per_query=5,
                                                 min_relevance=0.4, max_articles=3)
    assert [e.relevance for e in evidence] == [0.9, 0.7, 0.5]  # <0.4 dropped, sorted desc, capped
    assert [e.url for e in evidence] == ["u0", "u1", "u2"]
    assert fake_llm.assess_calls == 5      # one combined call per candidate (not two)
    assert lessons == []                   # empty KB


def test_failed_article_dropped_others_stand(monkeypatch):
    class _S:
        def search(self, q, k):
            return [{"url": "ok", "title": "t", "snippet": ""},
                    {"url": "boom", "title": "t", "snippet": ""}]

    class _L:
        def complete(self, prompt, **kw):
            if _GENQ in prompt:
                return '{"queries":["q"]}'
            if "boom-body" in prompt:
                raise RuntimeError("llm down")
            return '{"relevance":0.9,"summary":"s"}'

    monkeypatch.setattr(pipeline, "get_search", lambda: _S())
    monkeypatch.setattr(pipeline, "get_llm", lambda: _L())
    monkeypatch.setattr(pipeline, "fetch_text", lambda url, *a, **k: f"{url}-body")
    market = {"id": "m", "question": "Q", "description": "", "category": None}

    evidence, _ = pipeline.gather_evidence(market, max_articles=5, min_relevance=0.4)
    assert [e.url for e in evidence] == ["ok"]  # boom raised → dropped; ok stands


def test_budget_exceeded_propagates(monkeypatch):
    class _S:
        def search(self, q, k):
            return [{"url": "u", "title": "t", "snippet": ""}]

    class _L:
        def complete(self, prompt, **kw):
            if _GENQ in prompt:
                return '{"queries":["q"]}'
            raise BudgetExceeded("cap")

    monkeypatch.setattr(pipeline, "get_search", lambda: _S())
    monkeypatch.setattr(pipeline, "get_llm", lambda: _L())
    monkeypatch.setattr(pipeline, "fetch_text", lambda url, *a, **k: "body")
    market = {"id": "m", "question": "Q", "description": "", "category": None}

    with pytest.raises(BudgetExceeded):  # must NOT be swallowed as a dropped article
        pipeline.gather_evidence(market)
