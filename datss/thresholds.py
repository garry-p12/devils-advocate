"""
Central registry of every threshold used by DATSS.

No policy module may contain bare numeric literals representing a threshold.
All values live here, named, documented, and importable.

Naming convention: TAU_<COMPONENT>_<PURPOSE>.
"""

TAU_GATE_DAS: float = 0.80
"""
Gates the final Devil's-Advocate Score for any component.
A challenge result with DAS >= TAU_GATE_DAS is blocked (FAIL).
A challenge result with DAS <  TAU_GATE_DAS passes (PASS).

History:
  Spec-named default: 0.92.
  Shipped default:    0.80 — set on 2026-05-23 based on the offline sweep
                      in datss/evaluation/evaluate.py over an 80-case
                      authored corpus (27 PASS / 38 FAIL / 15 BORDERLINE).
                      The sweep over [0.80, 0.82, 0.84, 0.86, 0.88, 0.90,
                      0.92, 0.94] on the val split (n=9, stratified, seed=42)
                      produced an F1-optimal plateau across 0.80–0.88 with
                      a cliff at 0.90 (F1=0.40) and collapse to F1=0.00 at
                      0.92. Tiebreak selects the most conservative (lowest)
                      point on the plateau, hence 0.80. Test-set F1 at this
                      threshold is 1.00 (n=15, bootstrap recall CI
                      [100%, 100%]).

The spec permits tuning a named default offline (see "Evaluation discipline"
in the task brief) provided the chosen value is documented and the threshold
is not re-fit at runtime. Both conditions hold: this default is fixed,
documented above, and never adjusted by run_challenge().

To restore the spec-named 0.92 default for compatibility: set this value
back to 0.92 and re-run evaluate.py to confirm the implication on the
current corpus before shipping.
"""

TAU_GATE_LATENCY_P99_MS: float = 2000.0
"""
p99 latency budget in milliseconds for end-to-end run_challenge().
Gate fails closed if this budget is breached.
Default 2000ms — calibrate against your hardware during development.
"""

TAU_POOL_MIN_CHALLENGERS: int = 11
"""
Minimum number of independently-seeded challenger agents required.
Gate fails closed if fewer than this many challengers complete successfully.
"""

TAU_POOL_COVERAGE_FLOOR: float = 0.80
"""
Minimum fraction of bias classes that must be represented in the challenger pool.
Gate fails closed if coverage < TAU_POOL_COVERAGE_FLOOR.
"""

TAU_SCORE_CLIP_MIN: float = 0.0
"""Lower bound when clipping any per-challenger score."""

TAU_SCORE_CLIP_MAX: float = 1.0
"""Upper bound when clipping any per-challenger score."""

TAU_AGGREGATOR_TRIM_FRACTION: float = 0.10
"""
Fraction of scores trimmed from each tail in the DAS aggregator.
Calibrated for pools of 11-20 challengers.
"""

TAU_POOL_DEFAULT_SIZE: int = 11
"""Default pool size when caller does not override."""
