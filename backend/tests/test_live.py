"""Opt-in live test — real Polymarket + DeepSeek/Anthropic + Tavily/Serper.

Skipped unless RUN_LIVE_TESTS=1 AND real keys are configured. This is the
real-environment end-to-end check; it spends a small amount of API credit.

  RUN_LIVE_TESTS=1 python -m pytest tests/test_live.py -q
"""
import os

import pytest

from app.config import settings

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_TESTS") != "1" or not (settings.llm_ready and settings.search_ready),
    reason="live test: set RUN_LIVE_TESTS=1 and configure real LLM + search keys in .env",
)


def test_live_real_market_ingest():
    from app.data import polymarket
    markets = polymarket.list_open_markets(5)
    assert polymarket.last_source == "polymarket"
    assert markets and all(m["url"].startswith("https://polymarket.com/") for m in markets)


def test_live_real_forecast():
    from app.data import polymarket
    from app.forecast import forecaster
    markets = polymarket.list_open_markets(8)
    m = next(x for x in markets if 0.1 < (x.get("current_prob") or 0) < 0.9)
    fc = forecaster.run_forecast(m)
    assert 0.0 <= fc.agent_prob <= 1.0
    assert fc.runs, "expected at least one parsed ensemble run from the real LLM"
    assert not fc.rationale.startswith("解析失败")
