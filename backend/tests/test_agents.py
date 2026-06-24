"""LangChain agent governance (P3): disk-cache short-circuit + budget callback.

No network: create_agent is stubbed and the LLMResult is faked, so these cover
the new cost-control wiring without a live LLM call.
"""
from app.forecast import agents
from app.lib import cache
from app.lib.cost_tracker import tracker


def test_agent_run_caches_and_short_circuits(monkeypatch, tmp_path):
    monkeypatch.setattr(agents.settings, "cache_dir", tmp_path)
    monkeypatch.setattr(cache.settings, "cache_dir", tmp_path)
    monkeypatch.setattr(agents.settings, "deepseek_api_key", "x")
    calls = {"n": 0}

    class _Stub:
        def invoke(self, inp, config=None):
            calls["n"] += 1
            assert "recursion_limit" in (config or {})      # cap passed through
            assert (config or {}).get("callbacks")          # budget guard attached

            class _M:
                content = '{"probability":0.5}'
            return {"messages": [_M()]}

    monkeypatch.setattr(agents, "create_agent", lambda *a, **k: _Stub())
    market = {"question": "Q?", "description": "d", "close_at": "", "category": "其他"}

    out1, _ = agents.run_category_agent(market, "EV", "LE", temperature=0.3)
    out2, _ = agents.run_category_agent(market, "EV", "LE", temperature=0.3)
    assert out1 == out2 == '{"probability":0.5}'
    assert calls["n"] == 1  # second call served from disk cache — LLM not re-invoked


def test_recursion_error_falls_back_to_direct_call(monkeypatch, tmp_path):
    """When the tool-loop hits the recursion limit, run_category_agent must still
    return an answer via a direct (no-tools) LLM call instead of raising."""
    from langgraph.errors import GraphRecursionError
    monkeypatch.setattr(agents.settings, "cache_dir", tmp_path)
    monkeypatch.setattr(cache.settings, "cache_dir", tmp_path)
    monkeypatch.setattr(agents.settings, "deepseek_api_key", "x")

    class _Boom:
        def invoke(self, inp, config=None):
            raise GraphRecursionError("Recursion limit reached")

    class _LLM:
        def complete(self, prompt, **kw):
            return '{"probability":0.42,"confidence":"med"}'

    monkeypatch.setattr(agents, "create_agent", lambda *a, **k: _Boom())
    monkeypatch.setattr(agents, "get_llm", lambda: _LLM())
    market = {"question": "Q?", "description": "d", "close_at": "", "category": "其他"}
    out, _ = agents.run_category_agent(market, "EV", "LE", temperature=0.3)
    assert out == '{"probability":0.42,"confidence":"med"}'  # fallback answer, no raise


def test_budget_guard_records_and_enforces(monkeypatch):
    rec, checked = {}, {"n": 0}
    monkeypatch.setattr(tracker, "record",
                        lambda m, i, o, kind="llm": rec.update(m=m, i=i, o=o, kind=kind))
    monkeypatch.setattr(tracker, "check", lambda: checked.update(n=checked["n"] + 1))

    class _Msg:
        usage_metadata = {"input_tokens": 10, "output_tokens": 5}

    class _Gen:
        message = _Msg()

    class _Res:
        generations = [[_Gen()]]

    agents._BudgetGuard("deepseek-x").on_llm_end(_Res())
    assert rec == {"m": "deepseek-x", "i": 10, "o": 5, "kind": "agent"}  # recorded + attributed
    assert checked["n"] == 1                            # cap checked mid-run
