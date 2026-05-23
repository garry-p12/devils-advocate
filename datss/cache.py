"""
Challenge result cache.

Validity model (also documented in README):

A cached ChallengeResult is VALID to return if and only if ALL hold:
  1. claim text is byte-identical to the cached entry's claim.
  2. evidence dict serializes identically (json.dumps, sort_keys=True).
  3. component_id is identical.
  4. das_threshold matches the value stored with the cached entry
     (policy-change invalidation).
  5. pool_signature matches — the set of registered BiasClass values has
     not changed (composition-change invalidation).

A cached entry is NEVER written when the gate FAILed for a system reason:
  INSUFFICIENT_CHALLENGERS, SEED_COLLISION, LATENCY_BUDGET_BREACHED,
  CHALLENGER_POOL_ERROR.

Only content-driven outcomes are cached: PASS, DAS_ABOVE_THRESHOLD,
DAS_BELOW_THRESHOLD, COVERAGE_BELOW_FLOOR.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Dict, Optional

from datss.models import ChallengeInput, ChallengeResult, GateFailureReason

_UNSAFE_REASONS = {
    GateFailureReason.INSUFFICIENT_CHALLENGERS.value,
    GateFailureReason.SEED_COLLISION.value,
    GateFailureReason.LATENCY_BUDGET_BREACHED.value,
    GateFailureReason.CHALLENGER_POOL_ERROR.value,
}


def _canonical_key(inp: ChallengeInput) -> str:
    payload = json.dumps(
        {
            "claim": inp.claim,
            "evidence": inp.evidence,
            "component_id": inp.component_id,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class _CacheEntry:
    result: ChallengeResult
    das_threshold: float
    pool_signature: str


class ChallengeCache:
    """In-memory cache of completed, content-driven ChallengeResults."""

    def __init__(self) -> None:
        self._store: Dict[str, _CacheEntry] = {}

    @staticmethod
    def key_for(inp: ChallengeInput) -> str:
        return _canonical_key(inp)

    def get(
        self,
        inp: ChallengeInput,
        das_threshold: float,
        pool_signature: str,
    ) -> Optional[ChallengeResult]:
        key = _canonical_key(inp)
        entry = self._store.get(key)
        if entry is None:
            return None
        if entry.das_threshold != das_threshold:
            return None
        if entry.pool_signature != pool_signature:
            return None
        return entry.result

    def put(
        self,
        inp: ChallengeInput,
        result: ChallengeResult,
        das_threshold: float,
        pool_signature: str,
    ) -> None:
        # Never cache system-error FAILs.
        if result.reason in _UNSAFE_REASONS:
            return
        key = _canonical_key(inp)
        self._store[key] = _CacheEntry(
            result=result,
            das_threshold=das_threshold,
            pool_signature=pool_signature,
        )

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)
