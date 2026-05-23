# Task: Build DATSS — Adversarial Challenger Orchestration Layer

You are building a complete Python library called `datss` (Devil's-Advocate Testing
Substrate System) that stress-tests high-stakes research outputs by running them through
a pool of independent challenger agents and returning a gated verdict.

Work through the steps below **in order**. Complete and verify each step before moving
to the next. After each step, confirm what was built and run sanity checks.

---

## Context

CureForge AI is a longevity-research platform. Before any high-stakes claim or output
is allowed through a governance gate, it must be stress-tested by a pool of independent
"challenger" agents who argue against it. This library is that stress-test layer.

The challenger agents themselves can be simple — deterministic scoring functions or
rule-based critics. **The intelligence of individual challengers is not being evaluated.**
What matters: independence of seeding, bias-class coverage, score aggregation, gating
logic, failure-closed behavior, and evaluation methodology.

---

## Package Structure to Create

```
datss/
├── __init__.py
├── models.py              # ChallengeInput, ChallengeResult, GateDecision, BiasClass
├── thresholds.py          # ALL named thresholds — no bare numeric literals elsewhere
├── gate.py                # run_challenge() public entry point
├── pool/
│   ├── __init__.py
│   ├── seeder.py          # Independent seed allocation and collision detection
│   ├── challenger.py      # Base challenger interface + concrete implementations
│   └── coverage.py        # Bias-class coverage checker
├── aggregator.py          # DAS aggregation function
├── cache.py               # Challenge result cache with validity model
├── config/
│   └── defaults.yaml      # Default challenger count, coverage floor, etc.
├── evaluation/
│   ├── test_cases.csv     # Your authored test material (PASS/FAIL/BORDERLINE)
│   ├── build_cases.py     # Documents how cases were constructed
│   ├── run_cases.py       # Runs gate over all test cases, prints results
│   └── evaluate.py        # Threshold tuning on val, final eval on test
├── tests/
│   └── test_datss.py      # pytest suite covering all acceptance criteria
├── requirements.txt
└── README.md
```

---

## Step 1 — Thresholds Module (`thresholds.py`)

**This is the most important structural requirement. Build it first.**

Every threshold in the system lives here. No numeric literals in policy code — ever.
Each threshold is a named constant with a docstring.

```python
# thresholds.py

TAU_GATE_DAS: float = 0.92
"""
Gates the final Devil's-Advocate Score for any component.
Naming convention: tau_<component>_<purpose>.
A challenge result with DAS >= TAU_GATE_DAS is blocked (FAIL).
A challenge result with DAS < TAU_GATE_DAS passes (PASS).
Default 0.92 per spec. Tune offline on val split; never re-fit at runtime.
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
```

Add any additional thresholds you need (e.g. score clipping bounds) here,
never inline.

---

## Step 2 — Models (`models.py`)

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any

class GateDecision(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"

class BiasClass(str, Enum):
    """
    Closed enumeration of adversarial challenge dimensions.
    Must NOT be extensible at runtime — new classes require a code change.
    
    Choose a sensible set of 6-8 classes covering distinct attack angles.
    Document the rationale for each in the docstring below.
    """
    EVIDENCE_QUALITY      = "evidence_quality"
    # Attacks the strength, sample size, reproducibility of cited evidence.

    METHODOLOGY           = "methodology"
    # Attacks experimental design, controls, confounders, statistical approach.

    ALTERNATIVE_HYPOTHESIS = "alternative_hypothesis"
    # Argues an alternative explanation fits the evidence equally or better.

    SCOPE_GENERALIZABILITY = "scope_generalizability"
    # Attacks whether the claim generalizes beyond the specific conditions studied.

    PROVENANCE_COI        = "provenance_coi"
    # Scrutinizes source, funding, conflict of interest, prior retractions.

    INTERNAL_CONSISTENCY  = "internal_consistency"
    # Checks for contradictions within the claim or between claim and evidence.

    PRIOR_ART_CONFLICT    = "prior_art_conflict"
    # Identifies conflicts with established literature or prior findings.

    SAFETY_ETHICS         = "safety_ethics"
    # Flags potential harms, ethical concerns, or regulatory issues.

@dataclass
class ChallengeInput:
    claim: str                           # The output being stress-tested
    evidence: Dict[str, Any]             # Supporting evidence / provenance
    component_id: str                    # Which institute/component is requesting

@dataclass 
class ChallengerResult:
    challenger_id: int
    bias_class: BiasClass
    seed: int
    score: float                         # DAS contribution in [0, 1]; 1 = maximally adversarial
    critique: str                        # Human-readable explanation
    latency_ms: float

@dataclass
class ChallengeResult:
    decision: GateDecision
    das: float                           # Aggregated Devil's Advocate Score in [0, 1]
    subscores: List[ChallengerResult]
    coverage: float                      # Fraction of BiasClass values represented
    challenger_seeds: List[int]
    reason: str                          # Why this decision was reached
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
    DAS_ABOVE_THRESHOLD      = "das_above_threshold"   # Normal FAIL
```

---

## Step 3 — Seed Allocator (`pool/seeder.py`)

The independence property must be **verifiable by inspecting the seed-allocation
logic**, not just asserted at runtime.

```python
class SeedAllocator:
    """
    Allocates disjoint seeds to challengers from a deterministic stream.
    
    Strategy: derive seeds as SHA-256(master_seed || challenger_index),
    truncated to uint32. Disjointness is guaranteed by construction
    (different indices produce different hash inputs), but collision
    is still checked explicitly because:
    (a) the spec requires collision to be detectable, and
    (b) truncation from 256 to 32 bits creates birthday-paradox risk
        at large pool sizes.
    
    The allocated seeds are returned alongside a collision report so
    the caller can fail-close if any collision is detected.
    """
    def allocate(
        self,
        master_seed: int,
        n: int,
    ) -> tuple[list[int], bool]:
        """
        Returns (seeds, collision_detected).
        seeds: list of n integers, one per challenger.
        collision_detected: True if any two seeds are identical.
        
        Implementation: hash-derive each seed, then check
        len(set(seeds)) == len(seeds). If False, collision_detected=True.
        """
        ...

    @staticmethod
    def verify_disjoint(seeds: list[int]) -> bool:
        """
        Standalone verifier. Can be called by external auditors
        without access to the allocator instance.
        """
        return len(set(seeds)) == len(seeds)
```

Use `hashlib.sha256`. Encode as `sha256(f"{master_seed}:{index}".encode()).digest()[:4]`
interpreted as big-endian uint32.

---

## Step 4 — Bias-Class Coverage Checker (`pool/coverage.py`)

```python
from datss.models import BiasClass, ChallengerResult

def compute_coverage(results: list[ChallengerResult]) -> float:
    """
    Returns fraction of BiasClass members represented in results.
    BiasClass is a closed enum — total possible = len(BiasClass).
    """
    represented = {r.bias_class for r in results}
    return len(represented) / len(BiasClass)

def coverage_passes(results: list[ChallengerResult], floor: float) -> bool:
    return compute_coverage(results) >= floor
```

---

## Step 5 — Challenger Implementations (`pool/challenger.py`)

Define an abstract base and at least one concrete challenger per BiasClass.

```python
from abc import ABC, abstractmethod
import random
from datss.models import BiasClass, ChallengerResult

class BaseChallenger(ABC):
    bias_class: BiasClass  # Must be set on each concrete subclass

    @abstractmethod
    def challenge(
        self,
        claim: str,
        evidence: dict,
        seed: int,
        challenger_id: int,
    ) -> ChallengerResult:
        """
        Returns a ChallengerResult. Score in [0,1]:
        1.0 = maximally adversarial (strong objection found)
        0.0 = no objection (claim survives this challenge)
        """
        ...
```

**Implement one concrete challenger per BiasClass.** They can be simple — here
are the implementation patterns to use:

- **Scoring logic**: use a seeded `random.Random(seed)` plus weighted keyword/
  pattern matching against `claim` and `evidence`. The seed governs any
  stochastic element; keyword hits are deterministic.
- **Score construction**: start from a base score (e.g. 0.3), add penalty
  weights for each weakness indicator found, clamp to [0.0, 1.0].
- **Critique**: generate a human-readable string describing what was found.

Example skeleton for `EvidenceQualityChallenger`:

```python
class EvidenceQualityChallenger(BaseChallenger):
    bias_class = BiasClass.EVIDENCE_QUALITY

    # Weakness indicators (claim/evidence patterns that raise the score)
    WEAK_SIGNALS = [
        ("n=", -0.05),          # small sample sizes mentioned
        ("preliminary", +0.15),
        ("pilot", +0.10),
        ("not peer-reviewed", +0.25),
        ("unpublished", +0.20),
        ("anecdotal", +0.30),
    ]
    STRONG_SIGNALS = [
        ("randomized controlled", -0.20),
        ("meta-analysis", -0.25),
        ("n > 1000", -0.15),
        ("peer-reviewed", -0.10),
        ("replicated", -0.15),
    ]

    def challenge(self, claim, evidence, seed, challenger_id):
        rng = random.Random(seed)
        score = 0.30 + rng.uniform(-0.05, 0.05)  # seeded jitter
        
        text = claim.lower() + " " + str(evidence).lower()
        triggers = []
        for pattern, weight in self.WEAK_SIGNALS + self.STRONG_SIGNALS:
            if pattern in text:
                score += weight
                triggers.append(pattern)
        
        score = max(0.0, min(1.0, score))
        critique = f"Evidence quality score {score:.2f}. Triggers: {triggers or ['none']}"
        return ChallengerResult(...)
```

Write a similar concrete class for each of the 8 BiasClass members.

**Register all challengers in a `CHALLENGER_REGISTRY` dict keyed by BiasClass.**

---

## Step 6 — Aggregator (`aggregator.py`)

```python
def aggregate_das(scores: list[float]) -> float:
    """
    Aggregates per-challenger scores into a single DAS in [0, 1].
    
    Choice: trimmed mean, dropping the top and bottom 10% of scores.
    
    Rationale (must be documented):
    - Simple mean: a single malicious or broken challenger with score=1.0
      can meaningfully shift the aggregate even with 11 challengers (~9pp).
      A single lenient challenger at 0.0 has the same effect in the other
      direction. Not robust enough for a safety gate.
    - Min: too lenient — one permissive challenger clears the gate regardless
      of what the other 10 found.
    - Max: too strict — one hostile challenger blocks everything.
    - Trimmed mean (10% each side): with 11 challengers, drops 1 from each
      tail (floor(0.10 * 11) = 1), leaving 9 interior scores. This limits
      the influence of a single outlier while preserving sensitivity to the
      bulk of the challenger pool. At pool size >= 11 this is well-defined.
    
    Tradeoff: trimming reduces sensitivity when the pool is barely at
    minimum size. Document that the 10% trim is calibrated for pools of
    11-20 challengers; revisit if pool grows substantially.
    """
    ...
```

---

## Step 7 — Cache (`cache.py`)

```python
class ChallengeCache:
    """
    Caches ChallengeResult by a content-hash key derived from
    (claim, evidence, component_id).
    
    Validity model — a cached result is VALID to return iff:
    1. The claim text is byte-identical to the cached entry.
    2. The evidence dict serializes identically (json.dumps, sorted keys).
    3. The component_id is identical.
    4. The threshold configuration has not changed since caching
       (store the TAU_GATE_DAS value alongside the result).
    
    A cached result is INVALID (must re-run) if:
    - Any of the above differ.
    - The challenger pool composition changed (new or removed challenger class).
    - Cache entry age exceeds TTL (default: no TTL, configurable).
    
    NEVER cache a FAIL result that was caused by a system error
    (INSUFFICIENT_CHALLENGERS, SEED_COLLISION, LATENCY_BUDGET_BREACHED,
    CHALLENGER_POOL_ERROR). Only cache results where the gate ran to
    completion — PASS or content-driven FAIL (DAS_ABOVE/BELOW_THRESHOLD,
    COVERAGE_BELOW_FLOOR).
    
    Implementation: in-memory dict keyed by SHA-256 of the canonical
    serialization. Provide clear() and invalidate(key) methods.
    """
    ...
```

---

## Step 8 — Gate (`gate.py`)

```python
import time
from datss.models import ChallengeInput, ChallengeResult, GateDecision, GateFailureReason
from datss.thresholds import (
    TAU_GATE_DAS,
    TAU_GATE_LATENCY_P99_MS,
    TAU_POOL_MIN_CHALLENGERS,
    TAU_POOL_COVERAGE_FLOOR,
)

def run_challenge(
    inp: ChallengeInput,
    *,
    master_seed: int = 42,
    use_cache: bool = True,
    das_threshold: float = TAU_GATE_DAS,
    latency_budget_ms: float = TAU_GATE_LATENCY_P99_MS,
) -> ChallengeResult:
    """
    Public entry point. Runs the full adversarial challenge.
    
    Failure-closed contract:
    - Returns GateDecision.FAIL on ANY of:
        * Seed collision detected
        * Fewer than TAU_POOL_MIN_CHALLENGERS completed
        * Bias-class coverage < TAU_POOL_COVERAGE_FLOOR
        * DAS >= das_threshold  (high DAS = high adversarial pressure = FAIL)
        * Wall-clock time > latency_budget_ms
        * Any unhandled exception (catch-all → FAIL with reason=CHALLENGER_POOL_ERROR)
    - There is NO bypass path, override flag, or force-proceed mechanism.
    - A cached result is returned only if valid per ChallengeCache validity model.
    
    Gate passes (PASS) only when ALL of:
        * No seed collision
        * >= TAU_POOL_MIN_CHALLENGERS completed
        * Coverage >= TAU_POOL_COVERAGE_FLOOR
        * DAS < das_threshold
        * Wall-clock within budget
    """
    t0 = time.perf_counter()
    
    # 1. Check cache
    # 2. Allocate seeds — fail closed on collision
    # 3. Run challenger pool — fail closed if < MIN_CHALLENGERS complete
    # 4. Check coverage — fail closed if below floor
    # 5. Aggregate DAS
    # 6. Apply threshold — fail closed if DAS >= threshold
    # 7. Check latency — fail closed if over budget
    # 8. Cache result (only if gate ran to completion)
    # 9. Return fully populated ChallengeResult
    ...
```

**There must be no code path that returns GateDecision.PASS without passing
all checks. Verify this by inspection — write a comment at each check noting
what happens on failure.**

---

## Step 9 — Test Cases (`evaluation/test_cases.csv`)

Author test cases manually. Required columns:

```
id,label,component_id,claim,evidence_json,notes
```

- `label`: `PASS`, `FAIL`, or `BORDERLINE`
- Build at least **10 PASS cases**, **10 FAIL cases**, **5 BORDERLINE cases**
- Cases must be distinct — no near-duplicates
- Cover all 8 bias classes across the FAIL cases
- PASS cases should be well-supported, specific, defensible
- FAIL cases should be overreaching, poorly evidenced, internally contradictory,
  or conflict-of-interest-tainted — varied, not all the same failure mode
- BORDERLINE cases are genuinely ambiguous — the gate result will depend on
  threshold tuning

**Example PASS case:**
```
1,PASS,cardiovascular,"Rapamycin at 2mg/kg weekly reduces all-cause mortality by 23% in aged C57BL/6 mice over 18 months","{""source"": ""Harrison et al. 2009 Nature"", ""n"": 1901, ""design"": ""RCT"", ""replicated_by"": [""Miller 2011"", ""Neff 2013""]}","Well-supported, replicated RCT with large n"
```

**Example FAIL case:**
```
11,FAIL,frontier,"NAD+ supplementation reverses aging in humans by 40% within 6 months","{""source"": ""internal pilot"", ""n"": 12, ""design"": ""uncontrolled"", ""peer_reviewed"": false}","Overreaching claim, tiny uncontrolled pilot, not peer-reviewed"
```

---

## Step 10 — Evaluation Script (`evaluation/evaluate.py`)

This script:
1. Loads `test_cases.csv`
2. Splits 70% train / 10% val / 20% test — **stratified by label**, `random_state=42`
3. Sweeps `das_threshold` over [0.80, 0.82, 0.84, 0.86, 0.88, 0.90, 0.92, 0.94]
   on **val only**, picking the threshold that maximises F1 (FAIL=positive class)
   subject to FP rate ≤ 10% on val
4. Records the chosen threshold — does NOT re-examine test during tuning
5. Runs the gate with the chosen threshold on **test set exactly once**
6. Reports:

```
==============================
  DATSS — EVALUATION REPORT
==============================
Corpus: XX total (XX PASS, XX FAIL, XX BORDERLINE)
Splits: train=XX, val=XX, test=XX (stratified, seed=42, zero leakage confirmed)

Threshold tuning (val only):
  Swept: [0.80 ... 0.94]
  Selected: tau_gate_das = X.XX  (F1=X.XX on val, FP=X.XX%)

Test set results (touched once):
  Accuracy:  XX.XX%
  Precision: XX.XX%
  Recall:    XX.XX%
  F1:        XX.XX%
  FP rate:   XX.XX%   [PASS cases incorrectly blocked]
  FN rate:   XX.XX%   [FAIL cases incorrectly allowed]

Latency (ms) — 1000 calls on test cases:
  p50:  XXX.X
  p95:  XXX.X
  p99:  XXX.X  [budget: TAU_GATE_LATENCY_P99_MS = XXXX]

Bootstrap 95% CI (1000 resamples, seed=42):
  Recall:    [XX.XX%, XX.XX%]
  FP rate:   [XX.XX%, XX.XX%]
==============================
```

Save full results to `evaluation/report.json`.

---

## Step 11 — Test Suite (`tests/test_datss.py`)

Write `pytest` tests covering every acceptance criterion:

```python
# 1. Challenger pool has >= 11 challengers
def test_pool_size(): ...

# 2. All seeds are unique — verify via SeedAllocator.verify_disjoint
def test_seed_independence(): ...

# 3. Seed collision triggers FAIL
def test_seed_collision_fails_closed():
    # Monkeypatch SeedAllocator.allocate to return a colliding seed list
    # Assert result.decision == GateDecision.FAIL
    # Assert "collision" in result.reason.lower()
    ...

# 4. Coverage >= 80% on a normal run
def test_coverage_floor_met(): ...

# 5. Dropping challengers below MIN triggers FAIL (not PASS)
def test_insufficient_challengers_fails_closed():
    # Monkeypatch pool to return only 5 results
    # Assert FAIL
    ...

# 6. Coverage below 80% triggers FAIL
def test_coverage_below_floor_fails_closed():
    # Monkeypatch pool to return challengers all from 1 bias class
    # Assert FAIL
    ...

# 7. A clearly PASS case returns PASS
def test_clear_pass_case(): ...

# 8. A clearly FAIL case returns FAIL
def test_clear_fail_case(): ...

# 9. DAS is in [0, 1] on all test cases
def test_das_range(): ...

# 10. All subscores are in [0, 1]
def test_subscores_range(): ...

# 11. result object is fully populated (no None fields)
def test_result_fully_populated(): ...

# 12. Same input produces same decision (determinism)
def test_determinism():
    result1 = run_challenge(inp, master_seed=42)
    result2 = run_challenge(inp, master_seed=42, use_cache=False)
    assert result1.decision == result2.decision
    assert result1.das == result2.das
    ...

# 13. Cache returns same result on second call
def test_cache_hit():
    r1 = run_challenge(inp)
    r2 = run_challenge(inp)
    assert r2.cache_hit == True
    assert r1.das == r2.das
    ...

# 14. Cache invalidates when claim changes
def test_cache_invalidation(): ...

# 15. Latency budget breach fails closed
def test_latency_breach_fails_closed():
    # Set TAU_GATE_LATENCY_P99_MS = 0.001ms
    # Assert FAIL with reason LATENCY_BUDGET_BREACHED
    ...

# 16. ADVERSARIAL TEST — attempt to bypass the gate
def test_no_bypass_path():
    """
    Construct a run_challenge call that tries to proceed without satisfying
    the gate: inject a high-quality claim but patch DAS to return 0.99.
    Assert the system still returns FAIL and there is no keyword/flag
    that can force PASS.
    """
    ...

# 17. Thresholds live in thresholds.py — no bare literals in gate.py
def test_no_bare_literals_in_gate():
    import ast, inspect, datss.gate
    source = inspect.getsource(datss.gate)
    tree = ast.parse(source)
    # Walk AST, assert no float/int constants that look like thresholds
    # (0.92, 11, 0.80, 2000) appear as bare literals
    ...

# 18. BiasClass enum is closed (cannot add at runtime)
def test_bias_class_is_closed():
    with pytest.raises((AttributeError, TypeError)):
        BiasClass.NEW_CLASS = "new_class"
    ...
```

---

## Step 12 — Run Script (`evaluation/run_cases.py`)

A script that:
1. Loads all cases from `test_cases.csv`
2. Runs `run_challenge()` on each
3. Prints a formatted table:

```
ID  | Label      | Decision | DAS   | Coverage | Seeds | Reason
----|------------|----------|-------|----------|-------|-------
1   | PASS       | PASS     | 0.31  | 1.00     | OK    | das_below_threshold
2   | FAIL       | FAIL     | 0.94  | 1.00     | OK    | das_above_threshold
...
```

4. Prints summary: accuracy, breakdown by label.

Run as: `python -m evaluation.run_cases`

---

## Step 13 — README.md

Document:

1. **Bias-class enumeration** — list all 8 classes, one sentence each on why
   this angle matters for longevity-research claims. Explain why the set is
   closed and how to add a class (code change + retrain, not runtime extension).

2. **Aggregation function** — trimmed mean at 10%. Document the exact tradeoff:
   what a single hostile challenger at score=1.0 contributes to the aggregate
   at pool sizes 11, 15, 20. Show the math.

3. **Threshold defaults** — `tau_gate_das = 0.92`, `tau_pool_min_challengers = 11`,
   `tau_pool_coverage_floor = 0.80`, `tau_gate_latency_p99_ms = 2000`. For any
   you tune offline, document the val F1 and the held-out test F1, even if worse.

4. **Failure-closed paths** — list every code path that returns FAIL and what
   triggers it. Confirm there is no bypass.

5. **Caching strategy** — what is cached, what key, what invalidates it,
   what is never cached.

6. **Latency numbers** — p50/p95/p99 from a real run on your hardware.

7. **Known limitations** — be honest about what the challenger implementations
   do not cover. The same discipline as the Institute Perimeter DOCS.md §9.

---

## Step 14 — Requirements (`requirements.txt`)

```
pytest>=7.0.0
pandas>=2.0.0
numpy>=1.24.0
pyyaml>=6.0
scikit-learn>=1.3.0   # for stratified split in evaluate.py
```

No sentence-transformers, no external model calls. All challengers must run
offline deterministically.

---

## Step 15 — Final Run Order

```bash
# 1. Install
pip install -r requirements.txt

# 2. Run test material through the gate
python -m evaluation.run_cases

# 3. Run threshold tuning + evaluation
python -m evaluation.evaluate

# 4. Run test suite
pytest tests/ -v

# Confirm:
# - All pytest tests pass
# - Evaluation report shows chosen threshold and test-set metrics
# - p99 latency < TAU_GATE_LATENCY_P99_MS
# - No FAIL case returns PASS in run_cases output
```

---

## Critical Implementation Notes

### On Failure-Closed Behavior
Every check in `gate.py` must have a comment: "FAIL PATH: returns FAIL with
reason X if condition Y." Write a comment at the top of `gate.py` listing all
FAIL paths. The adversarial pytest test (test #16) will try to bypass this —
make it impossible.

### On Threshold Discipline (carry forward from Institute Perimeter)
- Tune `tau_gate_das` on val only. Touch test exactly once.
- If the test number is worse than val, report it honestly.
- Do not re-tune after seeing test results.
- Bootstrap CIs are required — they expose whether the test set is large enough
  to trust the point estimate.
- A val F1 of 1.0 with a 31-row val set is not evidence of a good threshold —
  acknowledge this. (Lesson from Institute Perimeter round 4.)

### On the Anomaly-Detector Lesson (applied here)
Do not oversell the challengers. If a challenger's score distribution doesn't
separate PASS from FAIL cases well, say so. Document per-challenger score
distributions on the test set. If a challenger effectively contributes nothing
(its scores are nearly identical across PASS and FAIL cases), flag it as a
weak signal rather than claiming it is "contributing real adversarial pressure."

### On Seeding
The seed independence property is verifiable by reading `seeder.py` alone —
the hash-derive construction makes disjointness provable. The collision check
is belt-and-suspenders. Document both levels in the README.

### On Caching Validity
The validity model in `cache.py` must be documented, not implicit. The README
must explain what "safe to cache" means. Hint: a challenge result is safe to
return from cache if and only if the inputs are identical AND the policy hasn't
changed. A policy change means `tau_gate_das` changed — store it in the cache
entry and invalidate on mismatch.

### No Vendor Names
Keep all challenger implementations, schemas, and public interface vendor-neutral.
No named cloud services, no named model-vendor SKUs, no GPU stack names anywhere
in the library. If a challenger uses a model, it must be behind a neutral
`BaseScorer` interface with a deterministic offline default.

---

## Definition of Done

- [ ] `python -m evaluation.run_cases` — prints all cases, no FAIL labeled as PASS
- [ ] `python -m evaluation.evaluate` — prints report with threshold, val metrics, test metrics, CIs, latency
- [ ] `pytest tests/ -v` — all 18 tests pass including adversarial bypass test
- [ ] All thresholds live in `thresholds.py` — confirmed by AST test (#17)
- [ ] `BiasClass` is a closed enum — confirmed by test (#18)
- [ ] No bare numeric literals in `gate.py` — confirmed by test (#17)
- [ ] Cache validity model documented in README and tested (#13, #14)
- [ ] README has: bias classes + rationale, aggregation math, threshold documentation, failure paths, latency numbers, known limitations
- [ ] Evaluation methodology: 3-way split, val-only tuning, test touched once, bootstrap CIs, honest delta reported
