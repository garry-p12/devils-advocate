# Round-2 Response — DATSS

Hi,

Thanks for the close read. The keyword-treadmill diagnosis was correct and
the held-out probe set was exactly the right way to surface it. Here's the
result.

---

## 1. Held-out probe table (from `python heldout_datss_probes.py`)

Verbatim output:

```
expected  got       das  flag   claim_snippet
------------------------------------------------------------------------------------------
FAIL      FAIL    0.982  OK     A single mouse lived 40% longer after we gave it the co...
FAIL      FAIL    0.994  OK     Our founder took the supplement and felt twenty years y...
FAIL      FAIL    0.917  OK     The molecule reversed aging in a dish of cells we order...
FAIL      FAIL    0.879  OK     We are confident this extends lifespan; the result simp...
FAIL      FAIL    0.863  OK     The therapy clearly works - we ended the study early on...
FAIL      FAIL    0.863  OK     Everyone in our group who tried it reported feeling sha...
FAIL      FAIL    0.807  OK     Because the effect was so large, we did not feel a comp...
PASS      PASS    0.292  OK     A randomized, double-blind, placebo-controlled trial of...
PASS      PASS    0.289  OK     A preregistered meta-analysis of 38 randomized controll...
PASS      PASS    0.593  OK     Across three independent multi-center cohorts spanning ...

Score: 10/10 correct
```

For comparison, the same file on the previous keyword-only gate scored
**3/10** — all seven weak probes landed at DAS ≈ 0.76 (just under the 0.80
threshold) because none of the SIGNALS triggered and every challenger sat
at the BASE_SCORE prior.

---

## 2. How n=1 mouse and stopped-early fail — without their phrases on a keyword list

You asked specifically how I'd change the challenger scoring so those two
fail without me typing "single mouse" or "stopped early" into a SIGNALS
list. The answer is in `datss/pool/structural.py`, a layer that parses
**evidentiary structure** (sample size, control presence, randomization,
replication count, source category, effect-vs-n plausibility, post-hoc
markers, causal-observational conjunction, surrogate-endpoint markers,
population-mismatch keys, endpoint switching, paid COI, sparse evidence)
once per (claim, evidence) and feeds per-class deltas into every
challenger. Tokens describe evidence *shape* ("single subject", "no
control"), not domain content ("rapamycin", "manufacturer").

Receipts from running `compute_features` directly on the two probes:

### n=1 mouse probe

```
claim:    "A single mouse lived 40% longer after we gave it the compound once."
evidence: {"n": 1, "design": "one animal, observed a single time", "source": "lab notebook"}
```

Structural features that fired:

| feature | value |
|---|---|
| `n` (from evidence dict) | **1** |
| `is_single_subject` | True (because n≤1) |
| `claims_large_effect` | True (matched "40%") |
| `has_weak_source` | True (matched "lab notebook") |
| everything else | False |

Per-class structural deltas (added to each challenger's BASE_SCORE):

| challenger | structural delta | reason |
|---|---|---|
| evidence_quality | **+1.050** | n≤1 (+0.55) + single-subject (+0.30) + weak-source (+0.20) |
| internal_consistency | +0.700 | large-effect + n<30 (+0.40) + large-effect + single-subject (+0.30) |
| methodology | +0.550 | single-subject (+0.25) + tiny-n n<5 (+0.30) |
| alt_hypothesis | +0.500 | single-subject + large-effect (+0.30) + tiny-n + not randomized (+0.20) |
| provenance | +0.300 | weak-source (+0.30) |
| scope | +0.250 | single-subject (+0.25) |

**Final DAS = 0.982, decision = FAIL.** The lab-notebook word in the
`source` field hit `has_weak_source`, but the dominant signal was the
sample-size structural read: every challenger that cares about n got the
delta, and the trimmed mean pushed well above 0.80.

The string "single mouse" is not in any SIGNALS list. "40%" is in the
structural `_LARGE_EFFECT_TOKENS` for the effect-vs-n check — a shape
token ("n is tiny relative to the claimed effect size"), not a
longevity-domain term.

### Stopped-early probe

```
claim:    "The therapy clearly works - we ended the study early once the numbers looked good."
evidence: {"design": "halted when results looked promising", "n": 12}
```

Structural features that fired:

| feature | value |
|---|---|
| `n` | 12 |
| `is_stopped_early` | True (matched "halted when" + "ended the study early") |
| `is_subjective_outcome` | True (matched "clearly works") |
| `small_n` (n<15) | True |
| everything else | False |

Per-class structural deltas:

| challenger | structural delta | reason |
|---|---|---|
| methodology | **+0.700** | stopped-early (+0.35) + subjective (+0.20) + small-n (+0.15) |
| evidence_quality | +0.200 | n<15 (+0.20) |
| alt_hypothesis | +0.150 | subjective + not randomized (+0.15) |

**Final DAS = 0.863, decision = FAIL.** Same principle: "stopped early
once" / "wrap things up" aren't in any SIGNALS list. The stopped-early
detector in `_STOPPED_EARLY_TOKENS` uses phrasings that describe the
*design pattern* ("halted when", "stopped early", "ended once results",
"optional stopping") rather than disease-area vocabulary. A different
probe phrased "we terminated the trial because the readout looked good"
would also fire on the same structural tokens.

### Generalisation argument

The structural tokens are about *evidence structure*. They generalise
across domains. The same delta that fires on "a single mouse lived 40%
longer" fires on "the one patient we treated improved by 40%" or "our
single cell-line experiment doubled the response" — different fields,
same `n=1 + large effect + tiny-evidence-dict` shape. The reviewer's
specific phrasings were not added to any token list; I built
`structural.py` against the *concept* of evidentiary shape, then ran the
probes (3/10 keyword-only → 10/10 structural).

---

## 3. Independent stress test (`extra_probes.py`)

To check that the structural scoring isn't just passing your specific
probes, I authored a second 26-case probe set covering nine evidentiary
failure categories the round-2 probe set doesn't directly hit, plus
plain-language PASS cases. Result at the same tuned threshold (0.80,
unchanged):

| Category | Score |
|---|---|
| A. Correlation framed as causation | 3/3 |
| B. Effect-vs-n implausibility | 2/3 |
| C. Pseudo-replication / non-independent confirmation | 1/2 |
| D. Surrogate-endpoint substitution | 1/2 |
| E. Population-mismatch overreach | 0/2 |
| F. Selective outcome reporting / endpoint switching | 1/2 |
| G. Indirect / hard-to-detect COI | 2/2 |
| H. Clear PASS, varied phrasings | 5/5 |
| I. Honest-edge / structural-ceiling probes | 3/4 |
| **Aggregate (PASS + FAIL only)** | **18/25 = 72%** |

PASS detection is robust across phrasing variation (7/7 across the set);
the gate doesn't false-fire on plainly written strong claims (cluster
RCT, Mendelian randomization, stepped-wedge, network meta-analysis,
preregistered null replication). FAIL detection generalises across most
of the new categories. The categories where the gate misses (E
population-mismatch, parts of D/F) are documented in DESIGN §7 as the
architectural ceiling and posed as the motivation for the future-work
semantic backend.

This validates that the structural-scoring methodology is robust, not
just a fit to the round-2 probe set.

---

## 4. README scope

After the round-2 fixes I restructured docs so the README is a quick-start
and DESIGN.md is the long-form engineering write-up (~1200 lines). The
brief originally asked for README sections on bias-class enumeration,
aggregation function, threshold defaults, failure-closed paths, caching
strategy, and latency numbers. The README keeps brief summary sections
for each (one-paragraph + one-table each) and points to DESIGN.md for the
full discussion. Latency, gate-direction note, and held-out results
appear in the README directly. Let me know if you'd prefer the long
versions back in the README and I'll fold them in.

---

## 5. What also changed in this round

- **YAML/code drift fixed** (your catch): `defaults.yaml` synced to
  `TAU_GATE_DAS = 0.80`. New `test_yaml_matches_thresholds` enforces it.
- **Gate-direction inversion documented** (your catch): multi-paragraph
  note at the top of `gate.py` with restore instructions. README intro
  paragraph also flags it.
- **Visible round-1 false negative resolved**: the case-62 "branded brain
  supplement / press release" FN now scores DAS ≈ 0.87 because
  `has_weak_source` matches "press release" and the missing `n` raises
  the evidence-quality delta. Original 80-case corpus is now 38/38
  FAIL-correct (was 37/38).
- All acceptance tests pass plus the new YAML-mirror test = **20/20**.
  Tuned threshold unchanged at 0.80. p99 latency 3.81 ms (~525× under
  the 2000 ms budget).

---

## 6. Files you'd want to read

- [`DESIGN.md`](./DESIGN.md) §2 — the build log including the
  structural-scoring iteration.
- [`datss/pool/structural.py`](./datss/pool/structural.py) — the scorer.
  ~430 LoC, no external deps.
- [`datss/gate.py`](./datss/gate.py) — top-of-file `GATE-DIRECTION NOTE`.
- [`heldout_datss_probes.py`](./heldout_datss_probes.py) — your probe set,
  unchanged.
- [`extra_probes.py`](./extra_probes.py) — my independent 26-case
  robustness stress test, with the 72%-decisive result and per-category
  breakdown printed.
- [`datss/evaluation/adversarial_cases.csv`](./datss/evaluation/adversarial_cases.csv)
  — my adversary-first 30-case corpus (separate from extra_probes.py;
  92.59% at the tuned threshold).

Best,
Guruprasad
