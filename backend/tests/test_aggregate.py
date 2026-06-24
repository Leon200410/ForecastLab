"""Ensemble aggregation: log-odds mean with clipping (PRD §7-M4)."""
import pytest

from app.forecast.aggregate import aggregate
from app.lib.models import ForecastRun


def _run(p):
    return ForecastRun(probability=p, confidence="med", rationale="r", key_factors=[])


def test_aggregate_within_range_and_median():
    runs = [_run(0.4), _run(0.5), _run(0.6)]
    out = aggregate(runs)
    assert 0.4 <= out["agent_prob"] <= 0.6
    assert out["median"] == pytest.approx(0.5)


def test_aggregate_clips_extremes_no_inf():
    # probs at 0 and 1 must be clipped so log-odds doesn't blow up
    out = aggregate([_run(0.0), _run(1.0)])
    assert 0.0 < out["agent_prob"] < 1.0


def test_confidence_low_on_disagreement():
    out = aggregate([_run(0.1), _run(0.9)])
    assert out["confidence"] == "low"
