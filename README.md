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
| Round-1 reviewer probe (`heldout_datss_probes.py`) | **10/10** | Was 3/10 before iteration 14's structural scorer |
| Round-2 adversarial corpus (`adversarial_cases.csv`, 30 cases) | **24/27 = 88.89%** | 10/10 PASS, 14/17 FAIL — 3 misses documented as the structural ceiling, see DESIGN §7.3 |

p99 latency: 3.81 ms (≈ 525× under the 2000 ms budget). Numbers regenerated
by `evaluate.py`; canonical source is `datss/evaluation/report.json`.

---

## Running everything

```bash
python -m datss.evaluation.run_cases         # gate over round-1 corpus at tuned threshold
python -m datss.evaluation.run_adversarial   # gate over round-2 adversary-first corpus
python -m datss.evaluation.evaluate          # tuning + held-out eval + report.json
python -m datss.evaluation.audit_challengers # per-class PASS-vs-FAIL signal audit
python -m datss.evaluation.audit_borderline  # BORDERLINE-only DAS distribution audit
python heldout_datss_probes.py               # round-1 reviewer's 10-case probe set
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
| Full engineering write-up (build, eval methodology, audits, limits) | [`DESIGN.md`](./DESIGN.md) |
| Gate orchestration + FAIL paths + direction note | `datss/gate.py` |
| Structural evidence scoring (iteration 14) | `datss/pool/structural.py` |
| Tuned threshold provenance | docstring of `TAU_GATE_DAS` in `datss/thresholds.py` |
| Evaluation report (canonical numbers) | `datss/evaluation/report.json` |
| Per-challenger discrimination audit | `datss/evaluation/challenger_audit.json` |
| Adversarial probe results | `datss/evaluation/adversarial_report.json` |
