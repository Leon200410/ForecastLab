"""Forecaster error surfacing: when every ensemble run fails, the raised error
carries the real underlying cause (model/quota/recursion/parse) — not a generic
'no parseable JSON' that hides what actually went wrong."""
import pytest

from app.forecast import agents, forecaster
from app.research import pipeline


def test_surfaces_underlying_agent_error(monkeypatch):
    monkeypatch.setattr(pipeline, "gather_evidence", lambda m: ([], []))  # offline

    def boom(*a, **k):
        raise RuntimeError("DeepSeek 401 unauthorized")

    monkeypatch.setattr(agents, "run_category_agent", boom)
    with pytest.raises(RuntimeError) as ei:
        forecaster.run_forecast({"id": "m1", "question": "Q", "category": "其他",
                                 "current_prob": 0.5})
    msg = str(ei.value)
    assert "401" in msg                 # real cause surfaced
    assert msg.count("集成分析失败") == 1  # single prefix, not doubled
