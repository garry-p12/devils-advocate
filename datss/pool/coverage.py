"""
Bias-class coverage check.

The coverage fraction is defined against the closed BiasClass enumeration.
Because BiasClass cannot be extended at runtime, len(BiasClass) is a stable
denominator and the coverage check is well-defined across all pools.
"""

from typing import List

from datss.models import BiasClass, ChallengerResult


def compute_coverage(results: List[ChallengerResult]) -> float:
    """Fraction of BiasClass members represented in results."""
    if not results:
        return 0.0
    represented = {r.bias_class for r in results}
    return len(represented) / len(BiasClass)


def coverage_passes(results: List[ChallengerResult], floor: float) -> bool:
    return compute_coverage(results) >= floor
