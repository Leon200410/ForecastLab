"""KB vector store + embedding provider — the RAG retrieval path.

These were previously uncovered, which is why the fastembed wiring bug (provider
configured but never instantiated) was invisible. Tests run on the offline
deterministic `local` embedder (conftest forces EMBEDDING_PROVIDER=local).
"""
import pytest

from app.config import settings
from app.kb import review as kb_review
from app.kb import store
from app.lib import db
from app.providers import embedding


@pytest.fixture(autouse=True)
def reset_embedder():
    embedding._embedder = None
    embedding._active = None
    yield
    embedding._embedder = None
    embedding._active = None


def test_local_embedder_deterministic_and_normalized():
    e = embedding.LocalHashingEmbedding()
    v1 = e.embed(["bitcoin above 100k"])[0]
    v2 = e.embed(["bitcoin above 100k"])[0]
    assert v1 == v2 and len(v1) == 256
    assert sum(x * x for x in v1) ** 0.5 == pytest.approx(1.0, abs=1e-6)


def test_get_embedder_honors_provider(monkeypatch):
    monkeypatch.setattr(settings, "embedding_provider", "local")
    assert embedding.get_embedder().mode == "local"


def test_get_embedder_falls_back_loudly_when_init_fails(monkeypatch, caplog):
    class Boom:
        mode = "fastembed"

        def __init__(self):
            raise RuntimeError("model download blocked")

    monkeypatch.setattr(settings, "embedding_provider", "fastembed")
    monkeypatch.setitem(embedding._PROVIDERS, "fastembed", Boom)
    with caplog.at_level("WARNING"):
        emb = embedding.get_embedder()
    assert emb.mode == "local"              # graceful fallback
    assert "failed to init" in caplog.text  # but loud, not silent


def test_search_ranks_more_similar_first():
    store.add("bitcoin crypto price prediction", {"lesson": "crypto", "tag": "btc"})
    store.add("election polling forecast politics", {"lesson": "election", "tag": "vote"})
    hits = store.search("bitcoin crypto price", k=1)
    assert hits and hits[0]["tag"] == "btc"


def test_search_dim_guard_skips_mismatched_vectors():
    # a vector stored by a different-dim model must not crash or pollute results
    db.kb_add("bad", [0.1] * 999, {"lesson": "wrong-dim", "tag": "bad"})
    store.add("bitcoin crypto price", {"lesson": "ok", "tag": "good"})
    tags = [h["tag"] for h in store.search("bitcoin crypto price", k=5)]
    assert "good" in tags and "bad" not in tags


def test_warmup_reports_active_embedder(monkeypatch):
    monkeypatch.setattr(settings, "embedding_provider", "local")
    info = embedding.warmup()
    assert info["mode"] == "local" and info["dim"] == 256


def test_search_min_score_filters_unrelated():
    store.add("bitcoin crypto price prediction", {"lesson": "x", "tag": "btc"})
    assert store.search("zzz totally unrelated topic", k=5, min_score=0.99) == []
    assert store.search("bitcoin crypto price", k=5, min_score=0.0)


def test_retrieve_lessons_category_filter():
    store.add("bitcoin crypto", {"lesson": "crypto-lesson", "category": "加密", "market_id": "m1"})
    store.add("us election", {"lesson": "vote-lesson", "category": "选举", "market_id": "m2"})
    got = kb_review.retrieve_lessons("anything", k=5, category="加密", min_score=0.0)
    assert "crypto-lesson" in got and "vote-lesson" not in got


def test_retrieve_lessons_excludes_own_market():
    store.add("bitcoin crypto", {"lesson": "self", "category": "加密", "market_id": "m1"})
    store.add("ethereum crypto", {"lesson": "other", "category": "加密", "market_id": "m2"})
    got = kb_review.retrieve_lessons("crypto", k=5, exclude_market_id="m1", min_score=0.0)
    assert "self" not in got and "other" in got
