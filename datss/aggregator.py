"""
DAS aggregation.

Trimmed mean at TAU_AGGREGATOR_TRIM_FRACTION on each tail.

Why trimmed mean rather than the alternatives:
  - Plain mean: a single broken/malicious challenger at 1.0 shifts the
    aggregate meaningfully (~1/n). For n=11 that is ~9 percentage points,
    enough to bias the gate. Not robust.
  - Min: too lenient — one permissive challenger clears the gate regardless
    of the rest of the pool.
  - Max: too strict — one hostile challenger blocks everything.
  - Median: robust but discards information about how broad the objection is.
  - Trimmed mean at 10%: drops the most extreme tails (floor(0.10*11)=1 each
    side at n=11), then averages the interior. Limits the influence of any
    single outlier while preserving sensitivity to the bulk of the pool.

Tradeoff: trimming reduces sensitivity at the minimum pool size. The 10%
trim is calibrated for pools of 11-20 challengers; revisit if pool grows.
"""

from typing import List

from datss.thresholds import (
    TAU_AGGREGATOR_TRIM_FRACTION,
    TAU_SCORE_CLIP_MAX,
    TAU_SCORE_CLIP_MIN,
)


def aggregate_das(scores: List[float]) -> float:
    """
    Aggregate per-challenger scores into DAS in [TAU_SCORE_CLIP_MIN,
    TAU_SCORE_CLIP_MAX]. Returns 0.0 on empty input (caller is expected to
    have already failed-closed on an empty pool, but we don't crash here).
    """
    if not scores:
        return TAU_SCORE_CLIP_MIN

    sorted_scores = sorted(scores)
    n = len(sorted_scores)
    k = int(TAU_AGGREGATOR_TRIM_FRACTION * n)  # floor

    if n - 2 * k <= 0:
        # Pool too small to trim; fall back to plain mean for safety.
        trimmed = sorted_scores
    else:
        trimmed = sorted_scores[k : n - k]

    das = sum(trimmed) / len(trimmed)
    return max(TAU_SCORE_CLIP_MIN, min(TAU_SCORE_CLIP_MAX, das))
