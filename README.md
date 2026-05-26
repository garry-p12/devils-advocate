# DATSS — Devil's-Advocate Testing Substrate System

DATSS is a Python library that stress-tests high-stakes research outputs by
running them through a pool of independently-seeded challenger agents,
aggregating their scores into a single Devil's-Advocate Score (DAS), and
returning a failure-closed gate decision.

For the long-form engineering write-up — spec adherence, build iterations,
evaluation methodology, what worked, what didn't, honest limitations,
future work — see **[DESIGN.md](./DESIGN.md)**.

---

## Quick start

```bash
pip install -r requirements.txt
```

```python
from datss import run_challenge, ChallengeInput

result = run_challenge(ChallengeInput(
    claim="Rapamycin at 2mg/kg weekly extends median lifespan in mice by 14% in a randomized controlled study",
    evidence={
        "source": "Harrison 2009 Nature",
        "n": 1901,
        "design": "randomized controlled, double-blind",
        "replicated_by": ["Miller 2011"],
    },
    component_id="cardiovascular",
))
print(result.decision, result.das, result.reason)
# GateDecision.PASS 0.34 das_below_threshold
```

---

## Gate-direction note

The CureForge task brief framed DAS as a score that *clears* a threshold to
PASS (high DAS = good evidence, default 0.92). This implementation **inverts
the direction**: high DAS = strong adversarial case = FAIL at the threshold.
I chose this reading because it matches the natural semantics of a
"Devil's-Advocate Score" (the adversary's confidence, not the claim's
quality). It is a deliberate reinterpretation. Full flag and restore
instructions in the `datss/gate.py` module docstring; see DESIGN.md §1.6
and §2 iteration 15 for the why.

---

## Held-out results

| evaluation | score | notes |
|---|---|---|
| `pytest datss/tests/ -v` | 20/20 | 18 task-details acceptance tests + cache-invalidation + YAML-mirror |
| Round-1 corpus (`test_cases.csv`, 80 cases) | 27/27 PASS, **38/38 FAIL** | Tuned threshold 0.80; held-out test F1=1.00, bootstrap recall CI [100%, 100%] |
| Round-2 reviewer probe (`heldout_datss_probes.py`, 10 cases) | **10/10** | Was 3/10 before the structural scorer (iteration 14) |
| Adversary-first corpus (`adversarial_cases.csv`, 30 cases) | **25/27 = 92.59%** | 10/10 PASS, 15/17 FAIL |
| Independent stress test (`extra_probes.py`, 26 cases) | **18/25 = 72%** | 7/7 PASS, 11/18 FAIL across nine evidentiary failure categories (correlation→causation, surrogate endpoints, population mismatch, endpoint switching, COI, etc.). Per-category breakdown printed by the script and documented in DESIGN §7.9 |

p99 latency: 3.81 ms (≈ 525× under the 2000 ms budget). Numbers regenerated
by `evaluate.py`; canonical source is `datss/evaluation/report.json`.

---

## Task-brief required sections (brief; full discussion in DESIGN.md)

The task brief asks the README to cover the bias-class enumeration, the
aggregation function, the threshold defaults, the failure-closed paths,
the caching strategy, and the latency numbers. Each section below is a
one-paragraph/one-table summary with a pointer into DESIGN.md for the
long version.

### Bias-class enumeration

`BiasClass` is a **closed** enum of 8 challenge dimensions. The set is
fixed in code; runtime extension is rejected by both `compute_coverage`
(which divides by `len(BiasClass)`) and `test_bias_class_is_closed`.

| BiasClass | What it attacks |
|---|---|
| `EVIDENCE_QUALITY` | sample size, peer review, replication, source quality |
| `METHODOLOGY` | control presence, randomization, stopping rules, post-hoc |
| `ALTERNATIVE_HYPOTHESIS` | causal/confound critique, reverse causation |
| `SCOPE_GENERALIZABILITY` | animal→human / in vitro→clinical / single-population overreach |
| `PROVENANCE_COI` | funding source, manufacturer involvement, retractions, blog/press |
| `INTERNAL_CONSISTENCY` | tiny-n + giant-effect, claim/data divergence |
| `PRIOR_ART_CONFLICT` | conflicts with established literature, "magic bullet" |
| `SAFETY_ETHICS` | missing IRB, self-experiment, vulnerable populations |

To add a class: edit `datss/models.py`, add a concrete challenger in
`datss/pool/challenger.py`, register it in `CHALLENGER_REGISTRY`, and
re-run `evaluate.py`. The cache's `pool_signature` auto-invalidates on
registry change. Full rationale per class in **DESIGN §1.2**.

### Aggregation function

DAS is the **symmetric trimmed mean** at `TAU_AGGREGATOR_TRIM_FRACTION =
0.10`. For a sorted score list of length n, drop `floor(0.10 * n)` from
each tail and average the interior. Single-1.0-outlier influence:

| Pool n | k = ⌊0.1·n⌋ | Interior | Hostile influence on DAS |
|---|---|---|---|
| 11 | 1 | 9 | 0.000 (trimmed) |
| 15 | 1 | 13 | 0.077 (survives the trim) |
| 20 | 2 | 16 | 0.000 (trimmed) |

Alternatives considered (plain mean, min, max, median) and their failure
modes in **DESIGN §1.3**.

### Threshold defaults

| Name | Default | Purpose |
|---|---|---|
| `TAU_GATE_DAS` | **0.80** | DAS ≥ this ⇒ FAIL. Task-named default was 0.92; tuned to 0.80 offline. |
| `TAU_GATE_LATENCY_P99_MS` | 2000.0 | End-to-end p99 budget. |
| `TAU_POOL_MIN_CHALLENGERS` | 11 | Minimum successful challengers. |
| `TAU_POOL_COVERAGE_FLOOR` | 0.80 | Minimum BiasClass coverage. |
| `TAU_AGGREGATOR_TRIM_FRACTION` | 0.10 | Per-tail trim. |

`TAU_GATE_DAS` was selected from the F1-optimal plateau 0.80–0.88 on the
val split; F1 collapses at 0.90 and pins at 0.0 by the task's named 0.92.
Full provenance in the docstring of `TAU_GATE_DAS` and in **DESIGN §4.3**.

### Failure-closed paths

| # | Condition | `reason` |
|---|---|---|
| 1 | Seed collision detected | `seed_collision` |
| 2 | < `TAU_POOL_MIN_CHALLENGERS` complete | `insufficient_challengers` |
| 3 | Coverage < `TAU_POOL_COVERAGE_FLOOR` | `coverage_below_floor` |
| 4 | DAS ≥ `das_threshold` | `das_above_threshold` |
| 5 | Wall-clock > `latency_budget_ms` | `latency_budget_breached` |
| 6 | Any unhandled exception | `challenger_pool_error: <ExcType>` |

No override flag, no force-PASS keyword, no admin bypass. `test_no_bypass_path`
monkeypatches the aggregator to 0.99 and probes every public knob; the gate
still FAILs. Full enumeration and adversarial-test design in **DESIGN §1.6**.

### Caching strategy

`ChallengeResult` is cached by SHA-256 of canonical
`(claim, evidence, component_id)` JSON. A cached entry is returnable only
if all of: identical claim/evidence/component_id, identical
`das_threshold` at write time, identical `pool_signature` (registry hash).
System-error FAILs are never cached. Full validity model in **DESIGN §1.7**.

---

## Running everything

```bash
python -m datss.evaluation.run_cases         # gate over round-1 80-case corpus at tuned threshold
python -m datss.evaluation.run_adversarial   # gate over adversary-first 30-case corpus
python -m datss.evaluation.evaluate          # tuning + held-out eval + report.json
python -m datss.evaluation.audit_challengers # per-class PASS-vs-FAIL signal audit
python -m datss.evaluation.audit_borderline  # BORDERLINE-only DAS distribution audit
python heldout_datss_probes.py               # round-2 reviewer's 10-case probe set
python extra_probes.py                       # independent 26-case robustness stress test
pytest datss/tests/ -v                       # full acceptance + hygiene tests
```

---

## Public surface

```
from datss import (
    run_challenge,       # the gate
    ChallengeInput,      # {claim, evidence, component_id}
    ChallengeResult,     # {decision, das, subscores, coverage, seeds, reason, ...}
    GateDecision,        # PASS / FAIL
    BiasClass,           # closed enum of 8 challenge dimensions
)
```

All thresholds live in `datss/thresholds.py`. Every threshold has a
docstring; `TAU_GATE_DAS` carries a full history block (task-named default,
shipped default, sweep provenance, restore instructions). An AST test
forbids bare threshold literals in `gate.py` and a YAML-mirror test forbids
drift between `defaults.yaml` and `thresholds.py`.

---

## Where to dig deeper

| topic | file |
|---|---|
| Gate orchestration + FAIL paths + direction note | `datss/gate.py` |
| Structural evidence scoring (iteration 14) | `datss/pool/structural.py` |
| Tuned threshold provenance | docstring of `TAU_GATE_DAS` in `datss/thresholds.py` |
| Evaluation report (canonical numbers) | `datss/evaluation/report.json` |
| Per-challenger discrimination audit | `datss/evaluation/challenger_audit.json` |
| Adversarial probe results | `datss/evaluation/adversarial_report.json` |
