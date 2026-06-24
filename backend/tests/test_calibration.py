"""Post-hoc calibration (A3): fit on resolved history, apply to new probs."""
from app.eval import calibration


def test_too_few_samples_returns_none():
    assert calibration.fit([(0.5, 1), (0.5, 0)]) is None


def test_apply_is_identity_without_calibrator():
    assert calibration.apply(0.73, None) == 0.73


def test_overconfident_model_is_pulled_toward_observed():
    # model says 0.8 / 0.2 but each only happens ~50% of the time (overconfident)
    pts = [(0.8, 1)] * 10 + [(0.8, 0)] * 10 + [(0.2, 1)] * 10 + [(0.2, 0)] * 10
    cal = calibration.fit(pts)
    assert cal is not None
    assert calibration.apply(0.8, cal) < 0.8   # high end pulled down toward 0.5
    assert calibration.apply(0.2, cal) > 0.2   # low end pulled up toward 0.5
    assert 0.0 <= calibration.apply(0.99, cal) <= 1.0
