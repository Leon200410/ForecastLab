"""Aggregate N ensemble runs into one forecast (PRD §7-M4).

Log-odds mean (clipped to avoid infinities) as the point estimate; confidence
from ensemble agreement + distance from 0.5; rationale/key_factors taken from
the run closest to the aggregate.
"""
import math
import statistics

from ..lib.models import ForecastRun
from ..lib.util import clamp


def aggregate(runs: list[ForecastRun]) -> dict:
    probs = [clamp(r.probability, 0.01, 0.99) for r in runs]
    logits = [math.log(p / (1 - p)) for p in probs]
    agg = 1 / (1 + math.exp(-sum(logits) / len(logits)))
    spread = max(probs) - min(probs)

    if abs(agg - 0.5) > 0.3 and spread < 0.15:
        confidence = "high"
    elif spread > 0.3:
        confidence = "low"
    else:
        confidence = "med"

    closest = min(runs, key=lambda r: abs(r.probability - agg))
    return {
        "agent_prob": round(agg, 4),
        "median": round(statistics.median(probs), 4),
        "confidence": confidence,
        "rationale": closest.rationale,
        "key_factors": closest.key_factors,
    }
