"""
Public entry point: run_challenge().

FAIL paths (all enumerated, all must remain in this file):
  1. Seed collision detected         -> FAIL / SEED_COLLISION
  2. < TAU_POOL_MIN_CHALLENGERS done -> FAIL / INSUFFICIENT_CHALLENGERS
  3. Coverage < floor                -> FAIL / COVERAGE_BELOW_FLOOR
  4. DAS >= das_threshold            -> FAIL / DAS_ABOVE_THRESHOLD
  5. Wall-clock > latency budget     -> FAIL / LATENCY_BUDGET_BREACHED
  6. Any unhandled exception         -> FAIL / CHALLENGER_POOL_ERROR

There is no override, no force-proceed flag, no bypass path. Tests in
test_datss.py adversarially probe this contract.
"""

from __future__ import annotations

import hashlib
import time
from typing import List, Optional

from datss.aggregator import aggregate_das
from datss.cache import ChallengeCache
from datss.models import (
    ChallengeInput,
    ChallengeResult,
    ChallengerResult,
    GateDecision,
    GateFailureReason,
)
from datss.pool.challenger import CHALLENGER_REGISTRY, build_default_pool
from datss.pool.coverage import compute_coverage
from datss.pool.seeder import SeedAllocator
from datss.thresholds import (
    TAU_GATE_DAS,
    TAU_GATE_LATENCY_P99_MS,
    TAU_POOL_COVERAGE_FLOOR,
    TAU_POOL_DEFAULT_SIZE,
    TAU_POOL_MIN_CHALLENGERS,
)

# Process-wide default cache. Callers can also pass a custom cache.
_DEFAULT_CACHE = ChallengeCache()


def _pool_signature() -> str:
    """Stable signature of registered BiasClass set — invalidates cache on change."""
    keys = sorted(bc.value for bc in CHALLENGER_REGISTRY.keys())
    return hashlib.sha256(",".join(keys).encode("utf-8")).hexdigest()


def _fail(
    *,
    reason: GateFailureReason,
    inp: ChallengeInput,
    das: float,
    subscores: List[ChallengerResult],
    seeds: List[int],
    t0: float,
) -> ChallengeResult:
    coverage = compute_coverage(subscores) if subscores else 0.0
    return ChallengeResult(
        decision=GateDecision.FAIL,
        das=das,
        subscores=subscores,
        coverage=coverage,
        challenger_seeds=seeds,
        reason=reason.value,
        component_id=inp.component_id,
        latency_ms=(time.perf_counter() - t0) * 1000.0,
        cache_hit=False,
    )


def run_challenge(
    inp: ChallengeInput,
    *,
    master_seed: int = 42,
    use_cache: bool = True,
    das_threshold: float = TAU_GATE_DAS,
    latency_budget_ms: float = TAU_GATE_LATENCY_P99_MS,
    pool_size: int = TAU_POOL_DEFAULT_SIZE,
    cache: Optional[ChallengeCache] = None,
) -> ChallengeResult:
    """
    Run the adversarial gate.

    See module docstring for the full failure-closed contract. There is NO
    keyword argument that forces a PASS, nor any code path below that
    returns GateDecision.PASS without satisfying all checks.
    """
    t0 = time.perf_counter()
    active_cache = cache if cache is not None else _DEFAULT_CACHE
    pool_sig = _pool_signature()

    try:
        # --- 1. Cache lookup -------------------------------------------------
        if use_cache:
            cached = active_cache.get(inp, das_threshold, pool_sig)
            if cached is not None:
                # Return a copy with cache_hit=True; preserve the cached
                # decision exactly — cache stores only completed gate results.
                return ChallengeResult(
                    decision=cached.decision,
                    das=cached.das,
                    subscores=cached.subscores,
                    coverage=cached.coverage,
                    challenger_seeds=cached.challenger_seeds,
                    reason=cached.reason,
                    component_id=cached.component_id,
                    latency_ms=cached.latency_ms,
                    cache_hit=True,
                )

        # --- 2. Seed allocation ---------------------------------------------
        # FAIL PATH: seed collision -> FAIL / SEED_COLLISION
        allocator = SeedAllocator()
        seeds, collision = allocator.allocate(master_seed, pool_size)
        if collision or not SeedAllocator.verify_disjoint(seeds):
            return _fail(
                reason=GateFailureReason.SEED_COLLISION,
                inp=inp,
                das=0.0,
                subscores=[],
                seeds=seeds,
                t0=t0,
            )

        # --- 3. Run pool ----------------------------------------------------
        # FAIL PATH: < TAU_POOL_MIN_CHALLENGERS complete -> INSUFFICIENT_CHALLENGERS
        pool = build_default_pool(pool_size)
        subscores: List[ChallengerResult] = []
        for idx, (challenger, seed) in enumerate(zip(pool, seeds)):
            try:
                r = challenger.challenge(inp.claim, inp.evidence, seed, idx)
                subscores.append(r)
            except Exception:  # noqa: BLE001 — individual challenger failure must not crash gate
                continue

        if len(subscores) < TAU_POOL_MIN_CHALLENGERS:
            return _fail(
                reason=GateFailureReason.INSUFFICIENT_CHALLENGERS,
                inp=inp,
                das=0.0,
                subscores=subscores,
                seeds=seeds,
                t0=t0,
            )

        # --- 4. Coverage check ----------------------------------------------
        # FAIL PATH: coverage < floor -> COVERAGE_BELOW_FLOOR
        coverage = compute_coverage(subscores)
        if coverage < TAU_POOL_COVERAGE_FLOOR:
            return _fail(
                reason=GateFailureReason.COVERAGE_BELOW_FLOOR,
                inp=inp,
                das=0.0,
                subscores=subscores,
                seeds=seeds,
                t0=t0,
            )

        # --- 5. Aggregate DAS -----------------------------------------------
        das = aggregate_das([s.score for s in subscores])

        # --- 6. Threshold check ---------------------------------------------
        # FAIL PATH: DAS >= das_threshold -> DAS_ABOVE_THRESHOLD
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        # --- 7. Latency check (checked before declaring PASS) ---------------
        # FAIL PATH: elapsed > budget -> LATENCY_BUDGET_BREACHED
        if elapsed_ms > latency_budget_ms:
            result = ChallengeResult(
                decision=GateDecision.FAIL,
                das=das,
                subscores=subscores,
                coverage=coverage,
                challenger_seeds=seeds,
                reason=GateFailureReason.LATENCY_BUDGET_BREACHED.value,
                component_id=inp.component_id,
                latency_ms=elapsed_ms,
                cache_hit=False,
            )
            # Do not cache — system-level FAIL.
            return result

        if das >= das_threshold:
            result = ChallengeResult(
                decision=GateDecision.FAIL,
                das=das,
                subscores=subscores,
                coverage=coverage,
                challenger_seeds=seeds,
                reason=GateFailureReason.DAS_ABOVE_THRESHOLD.value,
                component_id=inp.component_id,
                latency_ms=elapsed_ms,
                cache_hit=False,
            )
        else:
            # PASS — and only here. All checks above must have passed.
            result = ChallengeResult(
                decision=GateDecision.PASS,
                das=das,
                subscores=subscores,
                coverage=coverage,
                challenger_seeds=seeds,
                reason=GateFailureReason.DAS_BELOW_THRESHOLD.value,
                component_id=inp.component_id,
                latency_ms=elapsed_ms,
                cache_hit=False,
            )

        # --- 8. Cache (only on completed gate runs) -------------------------
        if use_cache:
            active_cache.put(inp, result, das_threshold, pool_sig)

        return result

    except Exception as exc:  # noqa: BLE001 — fail closed on any unexpected error
        # FAIL PATH: any unhandled exception -> CHALLENGER_POOL_ERROR
        return ChallengeResult(
            decision=GateDecision.FAIL,
            das=0.0,
            subscores=[],
            coverage=0.0,
            challenger_seeds=[],
            reason=f"{GateFailureReason.CHALLENGER_POOL_ERROR.value}: {type(exc).__name__}",
            component_id=inp.component_id,
            latency_ms=(time.perf_counter() - t0) * 1000.0,
            cache_hit=False,
        )


def clear_default_cache() -> None:
    """Test/admin helper — clears the module-level default cache."""
    _DEFAULT_CACHE.clear()
