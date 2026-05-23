"""
Concrete challenger implementations.

Each BiasClass has exactly one concrete challenger registered in
CHALLENGER_REGISTRY. Challengers are intentionally simple — deterministic
keyword/pattern scorers with a small seeded stochastic jitter. The point of
this library is the orchestration and gating logic, not challenger smarts.

Score semantics:
  - 0.0 = no objection (claim survives this challenge).
  - 1.0 = maximally adversarial.
  - BASE_SCORE is the prior: with no evidence either way, the challenger
    reports moderate suspicion. Strong positive evidence drives the score
    DOWN (negative signals); weak/contradictory/poor-quality evidence drives
    it UP (positive signals).

Scores are clipped to [TAU_SCORE_CLIP_MIN, TAU_SCORE_CLIP_MAX].
"""

from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Tuple

from datss.models import BiasClass, ChallengerResult
from datss.thresholds import TAU_SCORE_CLIP_MAX, TAU_SCORE_CLIP_MIN


def _flatten_text(claim: str, evidence: Dict[str, Any]) -> str:
    return (claim + " " + str(evidence)).lower()


def _apply_signals(text: str, signals: List[Tuple[str, float]]) -> Tuple[float, List[str]]:
    delta = 0.0
    triggers: List[str] = []
    for pattern, weight in signals:
        if pattern in text:
            delta += weight
            triggers.append(pattern)
    return delta, triggers


def _clip(score: float) -> float:
    return max(TAU_SCORE_CLIP_MIN, min(TAU_SCORE_CLIP_MAX, score))


class BaseChallenger(ABC):
    bias_class: BiasClass = None  # type: ignore[assignment]

    # (substring, weight). Positive weight RAISES adversarial pressure;
    # negative weight LOWERS it (claim survives this angle).
    SIGNALS: List[Tuple[str, float]] = []
    BASE_SCORE: float = 0.78  # prior: high suspicion until evidence exonerates

    @abstractmethod
    def challenge(
        self,
        claim: str,
        evidence: Dict[str, Any],
        seed: int,
        challenger_id: int,
    ) -> ChallengerResult:
        ...


class _PatternChallenger(BaseChallenger):
    """Shared scoring/critique skeleton driven by SIGNALS."""

    def challenge(
        self,
        claim: str,
        evidence: Dict[str, Any],
        seed: int,
        challenger_id: int,
    ) -> ChallengerResult:
        t0 = time.perf_counter()
        rng = random.Random(seed)
        text = _flatten_text(claim, evidence)
        delta, triggers = _apply_signals(text, self.SIGNALS)
        jitter = rng.uniform(-0.03, 0.03)
        score = _clip(self.BASE_SCORE + delta + jitter)
        critique = (
            f"[{self.bias_class.value}] score={score:.3f} "
            f"triggers={triggers or ['none']}"
        )
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return ChallengerResult(
            challenger_id=challenger_id,
            bias_class=self.bias_class,
            seed=seed,
            score=score,
            critique=critique,
            latency_ms=latency_ms,
        )


class EvidenceQualityChallenger(_PatternChallenger):
    bias_class = BiasClass.EVIDENCE_QUALITY
    BASE_SCORE = 0.80
    SIGNALS = [
        ("preliminary",            +0.22),
        ("pilot",                  +0.20),
        ("not peer-reviewed",      +0.30),
        ("not peer reviewed",      +0.30),
        ("unpublished",            +0.25),
        ("anecdotal",              +0.35),
        ("uncontrolled",           +0.25),
        ("self-reported",          +0.20),
        ("case report",            +0.20),
        ("case series",            +0.15),
        ("randomized controlled",  -0.50),
        ("rct",                    -0.40),
        ("meta-analysis",          -0.55),
        ("systematic review",      -0.45),
        ("peer-reviewed",          -0.35),
        ("replicated",             -0.40),
        ("double-blind",           -0.35),
        ("large cohort",           -0.25),
        ("preregistered",          -0.25),
    ]


class MethodologyChallenger(_PatternChallenger):
    bias_class = BiasClass.METHODOLOGY
    BASE_SCORE = 0.78
    SIGNALS = [
        ("uncontrolled",           +0.30),
        ("no control",             +0.30),
        ("open-label",             +0.18),
        ("retrospective",          +0.20),
        ("observational",          +0.18),
        ("confounder",             +0.20),
        ("selection bias",         +0.28),
        ("post-hoc",               +0.25),
        ("p-hack",                 +0.30),
        ("multiple comparisons",   +0.18),
        ("cherry-pick",            +0.30),
        ("randomized",             -0.40),
        ("placebo-controlled",     -0.40),
        ("double-blind",           -0.35),
        ("blinded",                -0.25),
        ("prospective",            -0.20),
        ("pre-registered",         -0.30),
        ("intent-to-treat",        -0.20),
        ("controlled",             -0.15),
    ]


class AlternativeHypothesisChallenger(_PatternChallenger):
    bias_class = BiasClass.ALTERNATIVE_HYPOTHESIS
    BASE_SCORE = 0.75
    SIGNALS = [
        ("correlation",            +0.25),
        ("associated with",        +0.18),
        ("linked to",              +0.18),
        ("may cause",              +0.10),
        ("could explain",          +0.15),
        ("alternative explanation",+0.25),
        ("reverse causation",      +0.28),
        ("confounding",            +0.22),
        ("hidden variable",        +0.25),
        ("causal",                 -0.30),
        ("mechanism established",  -0.35),
        ("mechanism elucidated",   -0.30),
        ("randomized controlled",  -0.40),
        ("dose-response",          -0.25),
        ("interventional",         -0.20),
        ("knockout",               -0.20),
    ]


class ScopeGeneralizabilityChallenger(_PatternChallenger):
    bias_class = BiasClass.SCOPE_GENERALIZABILITY
    BASE_SCORE = 0.78
    SIGNALS = [
        ("mice",                   +0.28),
        ("rats",                   +0.28),
        ("c. elegans",             +0.32),
        ("worms",                  +0.25),
        ("yeast",                  +0.32),
        ("in vitro",               +0.25),
        ("cell line",              +0.22),
        ("animal model",           +0.22),
        ("single population",      +0.20),
        ("single center",          +0.18),
        ("small cohort",           +0.20),
        ("japanese cohort only",   +0.20),
        ("c57bl/6",                +0.18),
        ("humans",                 -0.30),
        ("multi-center",           -0.25),
        ("diverse cohort",         -0.30),
        ("multiple species",       -0.25),
        ("translated to humans",   -0.30),
        ("global cohort",          -0.25),
    ]


class ProvenanceCOIChallenger(_PatternChallenger):
    bias_class = BiasClass.PROVENANCE_COI
    BASE_SCORE = 0.75
    SIGNALS = [
        ("industry funded",        +0.28),
        ("industry-funded",        +0.28),
        ("manufacturer",           +0.25),
        ("sponsored by",           +0.22),
        ("conflict of interest",   +0.30),
        ("undisclosed coi",        +0.35),
        ("retracted",              +0.50),
        ("predatory journal",      +0.40),
        ("blog post",              +0.35),
        ("press release",          +0.30),
        ("internal pilot",         +0.25),
        ("preprint",               +0.10),
        ("nih funded",             -0.25),
        ("government funded",      -0.25),
        ("nih r01",                -0.25),
        ("publicly funded",        -0.22),
        ("nature",                 -0.20),
        ("cell ",                  -0.18),
        ("nejm",                   -0.25),
        (" science ",              -0.15),
        ("lancet",                 -0.22),
        ("no conflicts",           -0.25),
        ("no competing interests", -0.25),
    ]


class InternalConsistencyChallenger(_PatternChallenger):
    bias_class = BiasClass.INTERNAL_CONSISTENCY
    BASE_SCORE = 0.72
    SIGNALS = [
        ("contradicts",            +0.30),
        ("inconsistent",           +0.28),
        ("does not match",         +0.25),
        ("does not support",       +0.25),
        ("at odds",                +0.25),
        ("paradox",                +0.18),
        ("but also fails",         +0.20),
        ("however the data",       +0.15),
        ("consistent with",        -0.25),
        ("aligns with",            -0.22),
        ("matches prior",          -0.22),
        ("matches the data",       -0.20),
    ]

    def challenge(self, claim, evidence, seed, challenger_id):
        # Numeric mismatch heuristic: tiny n + giant effect = internal red flag.
        t0 = time.perf_counter()
        rng = random.Random(seed)
        text = _flatten_text(claim, evidence)
        delta, triggers = _apply_signals(text, self.SIGNALS)

        n = evidence.get("n") if isinstance(evidence, dict) else None
        if isinstance(n, int) and n < 30 and any(
            s in text for s in ["40%", "50%", "60%", "70%", "reverses", "cures", "doubles"]
        ):
            delta += 0.35
            triggers.append("tiny-n vs giant-effect")
        if isinstance(n, int) and n >= 1000:
            delta -= 0.15
            triggers.append("large-n stabilizes")

        score = _clip(self.BASE_SCORE + delta + rng.uniform(-0.03, 0.03))
        critique = (
            f"[{self.bias_class.value}] score={score:.3f} "
            f"triggers={triggers or ['none']}"
        )
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return ChallengerResult(
            challenger_id=challenger_id,
            bias_class=self.bias_class,
            seed=seed,
            score=score,
            critique=critique,
            latency_ms=latency_ms,
        )


class PriorArtConflictChallenger(_PatternChallenger):
    bias_class = BiasClass.PRIOR_ART_CONFLICT
    BASE_SCORE = 0.75
    SIGNALS = [
        ("contradicts prior",      +0.30),
        ("conflicts with",         +0.25),
        ("overturns",              +0.25),
        ("unprecedented",          +0.25),
        ("never before",           +0.25),
        ("first to show",          +0.10),
        ("revolutionary",          +0.20),
        ("paradigm shift",         +0.22),
        ("magic bullet",           +0.30),
        ("cure-all",               +0.30),
        ("replicated by",          -0.35),
        ("consistent with",        -0.30),
        ("extends prior",          -0.22),
        ("prior literature",       -0.15),
        ("meta-analysis",          -0.30),
        ("matches prior findings", -0.30),
    ]


class SafetyEthicsChallenger(_PatternChallenger):
    bias_class = BiasClass.SAFETY_ETHICS
    BASE_SCORE = 0.72
    SIGNALS = [
        ("off-label",              +0.20),
        ("no irb",                 +0.40),
        ("without irb",            +0.40),
        ("self-experiment",        +0.32),
        ("self experiment",        +0.32),
        ("vulnerable population",  +0.28),
        ("informed consent waived",+0.32),
        ("serious adverse",        +0.30),
        ("death",                  +0.28),
        ("toxicity",               +0.20),
        ("unregulated",            +0.22),
        ("biohacker",              +0.28),
        ("diy",                    +0.22),
        ("irb approved",           -0.30),
        ("irb-approved",           -0.30),
        ("ethics approved",        -0.25),
        ("informed consent",       -0.22),
        ("safety profile",         -0.18),
        ("no adverse events",      -0.22),
        ("fda approved",           -0.30),
        ("regulatory approval",    -0.25),
    ]


CHALLENGER_REGISTRY: Dict[BiasClass, type] = {
    BiasClass.EVIDENCE_QUALITY:       EvidenceQualityChallenger,
    BiasClass.METHODOLOGY:            MethodologyChallenger,
    BiasClass.ALTERNATIVE_HYPOTHESIS: AlternativeHypothesisChallenger,
    BiasClass.SCOPE_GENERALIZABILITY: ScopeGeneralizabilityChallenger,
    BiasClass.PROVENANCE_COI:         ProvenanceCOIChallenger,
    BiasClass.INTERNAL_CONSISTENCY:   InternalConsistencyChallenger,
    BiasClass.PRIOR_ART_CONFLICT:     PriorArtConflictChallenger,
    BiasClass.SAFETY_ETHICS:          SafetyEthicsChallenger,
}


def build_default_pool(n: int) -> List[BaseChallenger]:
    """
    Build a pool of n challengers, cycling through CHALLENGER_REGISTRY so the
    bias-class coverage is maximal at any pool size >= len(BiasClass).
    """
    classes = list(CHALLENGER_REGISTRY.keys())
    pool: List[BaseChallenger] = []
    for i in range(n):
        cls = CHALLENGER_REGISTRY[classes[i % len(classes)]]
        pool.append(cls())
    return pool
