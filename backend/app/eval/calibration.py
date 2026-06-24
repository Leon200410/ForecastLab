"""Post-hoc probability calibration (A3) — stdlib only, no sklearn.

`eval/metrics.py` already *measures* calibration (reliability buckets); this
*applies* it. We fit a piecewise-linear map from predicted prob -> observed
frequency on resolved forecasts, then remap new predictions through it. With too
little (or too flat) history the fit is untrustworthy, so we return None and the
caller keeps the raw probability — calibration should never make things worse.
"""
from typing import Optional

from .metrics import calibration as _bucketize

MIN_SAMPLES = 20        # below this, one bin swing dominates — don't calibrate
MIN_BUCKET_COUNT = 2    # ignore bins backed by a single point

Calibrator = list[tuple[float, float]]  # sorted (mean_pred, observed_freq) control points


def fit(points: list[tuple[float, int]]) -> Optional[Calibrator]:
    """points: (predicted_prob, outcome 0/1) from already-resolved forecasts."""
    if len(points) < MIN_SAMPLES:
        return None
    pts = sorted((b["mean_pred"], b["freq"]) for b in _bucketize(points, n_buckets=10)
                 if b["count"] >= MIN_BUCKET_COUNT)
    return pts if len(pts) >= 2 else None


def apply(p: float, calibrator: Optional[Calibrator]) -> float:
    """Map a raw prob through the calibrator (clamped to its endpoints)."""
    if not calibrator:
        return p
    xs = [x for x, _ in calibrator]
    ys = [y for _, y in calibrator]
    if p <= xs[0]:
        return ys[0]
    if p >= xs[-1]:
        return ys[-1]
    for i in range(1, len(xs)):
        if p <= xs[i]:
            x0, x1, y0, y1 = xs[i - 1], xs[i], ys[i - 1], ys[i]
            t = (p - x0) / (x1 - x0) if x1 > x0 else 0.0
            return max(0.0, min(1.0, y0 + t * (y1 - y0)))
    return p
