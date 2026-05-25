# DATSS — Devil's-Advocate Testing Substrate System

DATSS is a Python library that stress-tests high-stakes research outputs by
running them through a pool of independent challenger agents and returning a
gated verdict. It is the layer that sits in front of any governance gate on a
longevity-research platform: if a claim cannot survive its own internal
devil's-advocate pool, it does not ship.

The challengers themselves are intentionally simple — deterministic, pattern-
based scorers. The point of this library is the orchestration: independent
seeding, bias-class coverage, robust aggregation, failure-closed gating, and
an evaluation methodology that doesn't lie to itself.

```python
from datss import run_challenge, ChallengeInput

result = run_challenge(ChallengeInput(
    claim="Rapamycin at 2mg/kg weekly extends median lifespan in mice by 14% in a randomized controlled study",
    evidence={"source": "Harrison 2009 Nature", "n": 1901, "design": "randomized controlled, double-blind", "replicated_by": ["Miller 2011"]},
    component_id="cardiovascular",
))
print(result.decision, result.das, result.reason)
# GateDecision.PASS 0.34 das_below_threshold
```

---

## 1. Bias-class enumeration

`BiasClass` is a **closed** enum of 8 challenge dimensions. Adding a member
requires a code change, a new concrete challenger, and an evaluation re-run —
there is no runtime extension path, because the coverage check divides by
`len(BiasClass)` and would silently degrade if the denominator could move.

| BiasClass | Why this angle matters for longevity-research claims |
|---|---|
| `EVIDENCE_QUALITY` | Distinguishes well-powered, peer-reviewed, replicated work from anecdote, preprints, and uncontrolled pilots. |
| `METHODOLOGY` | Catches design flaws: no controls, retrospective only, post-hoc, p-hacking, cherry-picked timepoints. |
| `ALTERNATIVE_HYPOTHESIS` | Argues that a correlation/confound or reverse causation fits the data as well as the stated mechanism. |
| `SCOPE_GENERALIZABILITY` | Flags overreach when in-vitro / animal / single-population findings are presented as human-general. |
| `PROVENANCE_COI` | Scrutinises funding source, manufacturer involvement, predatory journals, retractions, blog/press release sourcing. |
| `INTERNAL_CONSISTENCY` | Detects numeric mismatches (tiny n + giant effect), self-contradictions, claim/data divergence. |
| `PRIOR_ART_CONFLICT` | Surfaces conflicts with established literature; flags "unprecedented", "paradigm shift", "magic bullet" hype. |
| `SAFETY_ETHICS` | Identifies missing IRB approval, self-experimentation, vulnerable populations, serious adverse events. |

The set is closed. To add a class: edit `datss/models.py`, add a concrete
challenger in `datss/pool/challenger.py`, register it in `CHALLENGER_REGISTRY`,
and re-run `python -m datss.evaluation.evaluate`. The cache's `pool_signature`
key auto-invalidates on registry change.

---

## 2. Aggregation function

DAS is the **symmetric trimmed mean** at `TAU_AGGREGATOR_TRIM_FRACTION = 0.10`.
For a sorted score list of length n, we drop `floor(0.10 * n)` from each tail
and average the interior.

**Why not the alternatives:**

- *Plain mean*: a single broken or malicious challenger reporting 1.0 shifts
  the aggregate by `1/n`. At n=11 that is ~9 percentage points — enough to
  flip the gate. Symmetric for a lenient challenger at 0.0.
- *Min*: too lenient — one permissive challenger clears the gate regardless
  of the rest of the pool.
- *Max*: too strict — one hostile challenger blocks everything.
- *Median*: robust but discards information about the breadth of objection.
- *Trimmed mean at 10%*: drops the worst outlier in each direction (for
  n=11: 1 from each tail, leaving 9 interior scores). Caps single-outlier
  influence while preserving sensitivity to the bulk of the pool.

**What a single 1.0 hostile challenger contributes (the rest scoring 0):**

| Pool size n | k=floor(0.1n) | Interior size | Hostile influence on DAS |
|---|---|---|---|
| 11 | 1 | 9 | 0.000 (the 1.0 is trimmed) |
| 15 | 1 | 13 | 0.077 (1/13, the 1.0 survives the trim) |
| 20 | 2 | 16 | 0.000 (the 1.0 is trimmed) |

The trim is calibrated for pool sizes 11–20. Above ~25 the per-tail trim
grows and additional outlier shielding may be needed.

---

## 3. Threshold defaults

All thresholds live in `datss/thresholds.py`. Test #17 enforces that no bare
literal in `gate.py` matches any of them.

| Name | Default | Purpose |
|---|---|---|
| `TAU_GATE_DAS` | **0.80** | DAS ≥ this ⇒ FAIL. Task-details-named default was 0.92; shipped default tuned to 0.80 — see history block in `thresholds.py` and §3 tuning result below. |
| `TAU_GATE_LATENCY_P99_MS` | 2000.0 | End-to-end p99 budget. |
| `TAU_POOL_MIN_CHALLENGERS` | 11 | Minimum successful challengers. |
| `TAU_POOL_COVERAGE_FLOOR` | 0.80 | Minimum BiasClass coverage. |
| `TAU_AGGREGATOR_TRIM_FRACTION` | 0.10 | Per-tail trim. |

**Threshold tuning result.**

Corpus: 80 authored cases (27 PASS / 38 FAIL / 15 BORDERLINE).
Stratified split (manual, `random_state=42`): train=56, val=9, test=15.

Sweep `[0.80, 0.82, 0.84, 0.86, 0.88, 0.90, 0.92, 0.94]` on val only:

| `tau_gate_das` | Val F1 | Val FP |
|---|---|---|
| 0.80 | 1.00 | 0.00% |
| 0.82 | 1.00 | 0.00% |
| 0.84 | 1.00 | 0.00% |
| 0.86 | 1.00 | 0.00% |
| 0.88 | 1.00 | 0.00% |
| 0.90 | 0.40 | 0.00% |
| 0.92 | 0.00 | 0.00% |
| 0.94 | 0.00 | 0.00% |

Real signal exists now: the F1-optimal plateau spans **0.80–0.88**, then
recall collapses at 0.90 and pins at 0 by 0.92. Tiebreak across the plateau
selects **0.80** — the most conservative point at which val FP stays at 0%.

Note: the **task-details-named** default of 0.92 scores **F1=0.00 on val** with this
challenger calibration. Per the task brief's evaluation discipline ("If you
tune any default, tune it offline on a held-out split and document the chosen
value"), `TAU_GATE_DAS` is shipped at the tuned value **0.80** with full
provenance recorded in its docstring (`datss/thresholds.py`). The default
change is a deliberate, documented, code-visible decision — not a runtime
re-fit. Test #17 still enforces no bare literals in `gate.py`; the default
lives in `thresholds.py` so any future change is also explicit.

Held-out test (touched once at the tuned threshold):

| | tau_gate_das | F1 | FP | Recall 95% CI |
|---|---|---|---|---|
| Val (9 rows) | 0.80 | 1.00 | 0.00% | — |
| **Test (15 rows)** | **0.80** | **1.00** | **0.00%** | **[100%, 100%]** |

The bootstrap recall CI on test is `[100%, 100%]` over 1000 resamples — the
test FAIL cases (n=7) all land well above 0.80, so resampling doesn't move
the metric. This is real evidence of a stable operating point on this corpus,
not the previous `[0%, 100%]` non-answer.

**Caveat.** A 15-row test set is still small. The CI being tight means the
gate cleanly separates *these* PASS and FAIL cases; it does not mean the gate
will hold on adversarial inputs outside the authored distribution. The honest
read is: 0.80 is a defensible operating point for this challenger
implementation on the in-distribution corpus, and a larger and more
adversarially-constructed test set would tighten what we can claim past that.

**BORDERLINE distribution audit.** The 15 BORDERLINE cases were authored to
"anchor on genuinely contested literature" so that gate decisions on them
depend on threshold placement. `python -m datss.evaluation.audit_borderline`
checks whether they actually sit in a threshold-tight band [0.75, 0.85]:

| band | count | cases |
|---|---|---|
| tight (0.75 ≤ DAS ≤ 0.85) | **5/15** | 22, 23, 24, 74, 79 |
| low (DAS < 0.75) | **10/15** | 21, 25, 71, 72, 73, 75, 76, 77, 78, 80 |
| high (DAS > 0.85) | 0/15 | — |

Mean DAS = 0.644, median = 0.685, range [0.369, 0.819]. Only one-third of
BORDERLINE cases are doing the work the label promises — the other 10
include strong negative signals (peer-reviewed, IRB-approved, controlled)
that drag the prior down, so they functionally score as soft PASS. The
"borderline-ness" was author intent that the keyword scorer does not see.
Documented as a limitation in §7 rather than silently re-labelled.

---

## 4. Failure-closed paths

`run_challenge()` returns `GateDecision.FAIL` on any of:

| # | Condition | `reason` |
|---|---|---|
| 1 | Seed collision detected | `seed_collision` |
| 2 | Fewer than `TAU_POOL_MIN_CHALLENGERS` complete | `insufficient_challengers` |
| 3 | Bias-class coverage < `TAU_POOL_COVERAGE_FLOOR` | `coverage_below_floor` |
| 4 | DAS ≥ `das_threshold` | `das_above_threshold` |
| 5 | Wall-clock > `latency_budget_ms` | `latency_budget_breached` |
| 6 | Any unhandled exception | `challenger_pool_error: <ExcType>` |

There is **no** override flag, no force-PASS keyword, and no admin bypass on
the public API. Test #16 (`test_no_bypass_path`) probes every public
parameter and patches the aggregator to return 0.99 — the gate still FAILs.

---

## 5. Caching strategy

**What is cached:** a fully populated `ChallengeResult` from a completed gate
run, keyed by SHA-256 of the canonical JSON serialisation of
`(claim, evidence, component_id)`.

**Validity model** — a cached entry is returnable iff **all** hold:

1. `claim` is byte-identical.
2. `evidence` serialises identically under `json.dumps(sort_keys=True)`.
3. `component_id` is identical.
4. `das_threshold` matches the value stored at cache-write time.
5. `pool_signature` (hash of the sorted `CHALLENGER_REGISTRY` keys) is
   unchanged.

**What is never cached:** system-error FAILs —
`INSUFFICIENT_CHALLENGERS`, `SEED_COLLISION`, `LATENCY_BUDGET_BREACHED`,
`CHALLENGER_POOL_ERROR`. Caching those would persist transient infrastructure
faults as policy outcomes. Only content-driven results are cached
(`PASS`, `DAS_ABOVE_THRESHOLD`, `COVERAGE_BELOW_FLOOR`, `DAS_BELOW_THRESHOLD`).

The default cache is process-wide and in-memory. Pass `cache=...` to
`run_challenge` for per-caller isolation, or `use_cache=False` to bypass.

---

## 6. Latency numbers

Measured on the development machine (Darwin 23.5.0, Python 3.12, no GPU),
1000 calls on the 15-row test set with `use_cache=False`. **Canonical
source: `datss/evaluation/report.json` (regenerated by `evaluate.py`).**
Numbers below are quoted from that file; re-running `evaluate.py` will
update `report.json`, and any drift larger than ~20% on p99 should be
propagated here in the same commit.

| | latency |
|---|---|
| p50 | 0.21 ms |
| p95 | 0.26 ms |
| p99 | 0.39 ms |
| budget (`TAU_GATE_LATENCY_P99_MS`) | 2000.0 ms |

p99 is ~5100× under budget. The library is bound by the gate orchestration,
not the challengers themselves — substituting LLM-backed challengers would
move latency by several orders of magnitude and the budget would need to be
re-derived.

---

## 7. Known limitations

- **Per-challenger discrimination (audit).** `python -m datss.evaluation.audit_challengers`
  runs each of the 8 challengers directly over the 80-case corpus and reports
  mean score on PASS vs FAIL plus the gap. A challenger with gap < 0.10 is
  flagged WEAK — it contributes near-constant scores regardless of claim
  quality and is not exerting real adversarial pressure. Current audit:

  | bias_class | mean PASS | mean FAIL | gap | flag |
  |---|---|---|---|---|
  | `evidence_quality` | 0.081 | 0.931 | +0.849 | ok |
  | `methodology` | 0.420 | 0.962 | +0.541 | ok |
  | `provenance_coi` | 0.494 | 0.996 | +0.502 | ok |
  | `internal_consistency` | 0.568 | 0.873 | +0.305 | ok |
  | `alternative_hypothesis` | 0.506 | 0.793 | +0.287 | ok |
  | `prior_art_conflict` | 0.528 | 0.800 | +0.272 | ok |
  | `safety_ethics` | 0.601 | 0.824 | +0.223 | ok |
  | `scope_generalizability` | 0.588 | 0.762 | +0.174 | ok |

  All 8 discriminate on the current corpus. `scope_generalizability` is the
  thinnest signal — its gap was +0.008 (clear WEAK) at the 25-case point and
  only rose to +0.174 once cases 43–47 and 68 were authored with explicit
  animal/in-vitro/single-population scope-overreach language. That is
  visibility into the audit working as a corpus-quality sentinel, not
  evidence the challenger itself is broad-spectrum. Audit JSON saved to
  `datss/evaluation/challenger_audit.json`.

- **BORDERLINE label is partly aspirational.** The 80-case corpus contains
  15 BORDERLINE cases but only 5 sit in the threshold-tight band [0.75, 0.85]
  (see §3 "BORDERLINE distribution audit" and `audit_borderline.py`). The
  other 10 score below 0.75 because they carry strong positive evidence
  signals (peer-reviewed RCT, IRB approval, controlled design) that the
  keyword scorer takes at face value, even though the author flagged the
  case as borderline on grounds like tiny n or single-population scope.
  The keyword architecture cannot see "this is a real RCT but the n is too
  small to support the claim". The future-work fix is either (a) a semantic
  scorer that weighs n and effect size against claim strength, or (b)
  re-labelling the 10 affected cases as soft PASS. Neither has been done
  yet — the label gap is documented honestly rather than papered over.

- **Visible false negative.** Case 62 ("branded brain supplement reverses
  early dementia based on a press release with no peer-reviewed paper") scores
  DAS=0.75 at threshold 0.80 and is decided PASS in `run_cases`. It is the
  one FAIL-labelled case the gate misses on the full corpus (37/38 = 97.4%).
  The case lands in train under the seed-42 split, so it does not contaminate
  test, but it is the most informative failure mode visible: the claim is
  short, the evidence dict is sparse, and the COI pattern is "press release"
  without explicit "manufacturer" or "industry-funded" — under-triggers the
  provenance challenger. Either better challenger patterns or a tighter
  threshold (~0.74) would catch it.

- **Challenger sophistication.** Every challenger is a deterministic keyword
  scorer over claim+evidence text plus a tiny seeded jitter. They will miss
  any objection that doesn't surface as a recognised substring. The audit
  above gives one quantitative signal that each is non-trivial, but a real
  challenger would parse semantics rather than match patterns. The library
  is structured so a `BaseChallenger` subclass can wrap any model behind the
  same interface — but the in-tree implementations are deliberately offline.

- **Corpus size and test set.** 80 authored cases, 15 held out for test.
  Bootstrap recall CI on test is `[100%, 100%]` — tight because the seven
  test FAIL cases are well above threshold, not because the corpus is large.
  Real deployment should expand to several hundred cases including
  adversarial edge cases authored *to defeat* the keyword patterns (the
  current corpus does not deliberately attempt to evade the challengers).

- **Stratification compromise.** Three-class stratified sklearn splits
  require ≥3 rows per fold per class; on the previous 25-case corpus
  sklearn's stratify rejected the val fold. The split in `evaluate.py` is
  a manual stratified shuffle with `random_state=42`; it preserves per-class
  proportions but is not the exact sklearn API. At 80 cases sklearn would
  work too — keeping the manual splitter for reproducibility across corpus
  sizes.

- **No external model calls.** Per the task details, every challenger runs offline and
  deterministically. There is no LLM-backed scorer behind any
  `BaseScorer` interface in this library.

- **No vendor lock-in.** Challenger schemas, identifiers, and the public API
  are vendor-neutral. No cloud-service, model-SKU, or GPU-stack names appear
  in `datss/`.

---

## Running

```bash
pip install -r requirements.txt
python -m datss.evaluation.run_cases         # gate over every authored case
python -m datss.evaluation.evaluate          # tuning + held-out eval + report.json
python -m datss.evaluation.audit_challengers # per-class PASS-vs-FAIL signal audit
python -m datss.evaluation.audit_borderline  # BORDERLINE-only DAS distribution audit
pytest datss/tests/ -v                       # 18 task-details acceptance tests + 1 extra cache-invalidation test
```

Done means: all 19 pytest tests pass (the 18 task-details acceptance tests plus the
extra `test_cache_invalidates_on_threshold_change` that exercises the
threshold-change branch of the cache validity model), `evaluate.py` reports
a chosen threshold with val+test metrics and bootstrap CIs, `audit_challengers`
shows all 8 challengers above the gap=0.10 weak-signal floor, p99 latency is
under `TAU_GATE_LATENCY_P99_MS`, and `run_cases` at the tuned threshold
returns 27/27 PASS-correct and 37/38 FAIL-correct (the one visible miss,
case 62, is discussed in §7).
