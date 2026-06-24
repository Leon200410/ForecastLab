"""Cost tracker (C1): per-day soft cap + snapshot that survives a restart."""
import pytest

from app.lib import cost_tracker
from app.lib.cost_tracker import BudgetExceeded, CostTracker


def test_per_day_cap_and_restore(monkeypatch, tmp_path):
    monkeypatch.setattr(cost_tracker.settings, "data_dir", tmp_path)
    monkeypatch.setattr(cost_tracker.settings, "max_spend_usd", 1.0)
    t = CostTracker()
    t.record("deepseek-v4-flash", 2_000_000, 2_000_000)  # ~ $1.6 today
    assert t.day_usd >= 1.0
    with pytest.raises(BudgetExceeded):
        t.check()

    # a fresh process restores the persisted snapshot (spend + cap not lost)
    restored = CostTracker()
    restored.restore()
    assert round(restored.day_usd, 4) == round(t.day_usd, 4)
    assert round(restored.total_usd, 4) == round(t.total_usd, 4)
    with pytest.raises(BudgetExceeded):
        restored.check()


def test_attribution_by_kind_persists(monkeypatch, tmp_path):
    monkeypatch.setattr(cost_tracker.settings, "data_dir", tmp_path)
    monkeypatch.setattr(cost_tracker.settings, "max_spend_usd", 1000.0)
    t = CostTracker()
    t.record("deepseek", 1_000, 1_000, kind="query_gen")
    t.record("deepseek", 1_000, 1_000, kind="assess")
    t.record("deepseek", 1_000, 1_000, kind="assess")
    s = t.summary()
    assert set(s["by_kind"]) == {"query_gen", "assess"}
    assert s["by_kind"]["assess"] > s["by_kind"]["query_gen"]  # two assess calls vs one

    restored = CostTracker()
    restored.restore()
    assert set(restored.by_kind) == {"query_gen", "assess"}


def test_daily_rollover_resets_day_but_keeps_total(monkeypatch, tmp_path):
    monkeypatch.setattr(cost_tracker.settings, "data_dir", tmp_path)
    monkeypatch.setattr(cost_tracker.settings, "max_spend_usd", 100.0)
    t = CostTracker()
    t.record("deepseek", 1_000, 1_000)
    total_before = t.total_usd
    t.day, t.day_usd = "2000-01-01", 999.0  # simulate a stale day over the cap
    t.check()  # rollover -> today's spend resets, so no raise
    assert t.day_usd == 0.0
    assert t.total_usd == total_before  # all-time cumulative is preserved
