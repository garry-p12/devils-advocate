"""
Data models for DATSS: inputs, per-challenger results, aggregated results,
and the closed enumerations for decisions, bias classes, and failure reasons.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List


class GateDecision(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


class BiasClass(str, Enum):
    """
    Closed enumeration of adversarial challenge dimensions.

    The set is intentionally closed — adding a new class requires a code change
    and a re-evaluation pass. Runtime extension is prohibited because the
    coverage check (and therefore the gate) is defined relative to len(BiasClass).

    Eight classes were chosen to cover the principal attack angles on
    longevity-research claims without over-fragmenting the score signal.
    """

    EVIDENCE_QUALITY       = "evidence_quality"
    METHODOLOGY            = "methodology"
    ALTERNATIVE_HYPOTHESIS = "alternative_hypothesis"
    SCOPE_GENERALIZABILITY = "scope_generalizability"
    PROVENANCE_COI         = "provenance_coi"
    INTERNAL_CONSISTENCY   = "internal_consistency"
    PRIOR_ART_CONFLICT     = "prior_art_conflict"
    SAFETY_ETHICS          = "safety_ethics"


@dataclass
class ChallengeInput:
    claim: str
    evidence: Dict[str, Any]
    component_id: str


@dataclass
class ChallengerResult:
    challenger_id: int
    bias_class: BiasClass
    seed: int
    score: float
    critique: str
    latency_ms: float


@dataclass
class ChallengeResult:
    decision: GateDecision
    das: float
    subscores: List[ChallengerResult]
    coverage: float
    challenger_seeds: List[int]
    reason: str
    component_id: str
    latency_ms: float
    cache_hit: bool = False


class GateFailureReason(str, Enum):
    """All reasons a gate can fail. Used in ChallengeResult.reason."""

    INSUFFICIENT_CHALLENGERS = "insufficient_challengers"
    COVERAGE_BELOW_FLOOR     = "coverage_below_floor"
    SEED_COLLISION           = "seed_collision"
    DAS_BELOW_THRESHOLD      = "das_below_threshold"
    LATENCY_BUDGET_BREACHED  = "latency_budget_breached"
    CHALLENGER_POOL_ERROR    = "challenger_pool_error"
    DAS_ABOVE_THRESHOLD      = "das_above_threshold"
