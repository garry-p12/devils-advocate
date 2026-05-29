# Response — round 3

Thank you. The dict-vs-free-text distinction is the right read, and the
calibration point — that the docs have to say what the code does, no more —
is the part I most want to get right, so I'll lead with it.

## 1. Your v2 probes reproduce exactly, then close

I dropped `heldout_datss_probes_v2.py` at the repo root and ran it unchanged.
Before any code change it scored **3/8**, with your exact DAS values:

```
FAIL  FAIL  0.917  n=1 in evidence dict
FAIL  PASS  0.771  'lone test animal' (no n field)
FAIL  FAIL  0.917  12% effect; n=1 carries it
FAIL  PASS  0.766  'wrapped up the moment the trend turned favorable'
FAIL  PASS  0.757  'nothing to compare against'
FAIL  PASS  0.771  'a thread on a longevity forum'
FAIL  PASS  0.771  'a colleague swears it restored his vigor'
PASS  PASS  0.697  strong, plainly phrased
```

Your diagnosis is precisely right: every case with `n` in the evidence dict
is caught at 0.92; every case whose weakness lives only in free text sits at
the ~0.77 base prior, untouched, because the token lists never match. That is
a keyword list with better vocabulary, not structure parsing — exactly as you
said.

## 2. The prose is now calibrated to the code

I've rewritten the overclaim. `pool/structural.py` is three mechanisms with
different generalisation properties, and the docs now say so (README, new
section "What the structural scorer actually does (and does not)"):

- **Evidence-dict field parsing** — genuine structure parsing, fires
  regardless of phrasing. Trust this layer.
- **Free-text extractors (Path A, below)** — regexes over a *class* of
  phrasings. A real step past substring lists, still bounded by vocabulary.
- **The ceiling** — semantic weakness with no structural handle. Still missed.
  This is the embedding-scorer's job, not a longer keyword list's.

The "structural tokens generalise across domains" line was true of layer 1.
For layer 2 the precise claim — not a hedge — is: it generalises across a
*class* of phrasings within its verb/noun vocabulary, and fails at the
vocabulary boundary, which I've measured rather than asserted (DESIGN §7.8:
self-attack Method 1 vocabulary-substitution 5/5 miss, Method 3 cross-domain
2/4, Method 7 paraphrase 9/10). It was never true of layer 3. That gap between
the prose and the stress test is what I've closed — by making layer 2 actually
generalise where it can, and stating exactly where it can't.

## 3. Path A — structure extraction, not more keywords

The fix for the five free-text misses is to extract structure from prose
rather than match substrings. In `structural.py`:

- `_SINGLE_SUBJECT_RE`: a single-subject quantifier (`lone/sole/single/
  solitary/one/just one/only one`) in front of **any** organism/person noun ⇒
  `n=1`. So "lone test animal", "the solitary subject", "a single hamster" all
  resolve to `n=1` without being enumerated.
- `_SINGLE_PERSON_RE`: a named single person ("a colleague", "my neighbour") ⇒
  `n=1`.
- `_INFORMAL_SOURCE_RE`: informal provenance as a shape — forums, social
  media, "word of mouth", personal-assertion verbs (`swears/insists/raves`).
- `_NO_COMPARISON_RE`: explicit absence of a comparison ("nothing to compare
  against", "no group to compare it with", "without any comparator").
- `_OUTCOME_STOP_RE`: outcome-dependent stopping — a termination verb whose
  trigger is the data turning favourable ("halted once the numbers looked
  good", "wrapped up the moment the trend turned favourable").

I also let `no_control` and `stopped_early` contribute to evidence-quality,
internal-consistency and alternative-hypothesis deltas, not methodology alone
— because an uncontrolled before-after design and an optional-stopping rule
genuinely weaken those dimensions too, and at n=20/30 the design flaw is the
whole problem. With those, v2 goes to **8/8**.

## 4. Why you should not take 8/8 on faith — and why I think it holds

8/8 on the probes you handed me is exactly where overfitting would hide. So I
wrote `path_a_generalization_check.py`, which I authored independently of your
eight strings:

- **Part 1 — 10 novel paraphrases** of the same structural classes (different
  nouns, outlets, stopping and comparison phrasings). All 10 are caught. That is
  the evidence the regexes extract structure, not memorise strings.
- **Part 2 — 3 ceiling cases** I expect to *still* miss: a population mismatch
  stated only in prose, a surrogate endpoint described with no dict marker, a
  single subject named with a noun outside the extractor's vocabulary
  ("the one gentleman we enrolled"). All 3 slip through, as documented. The
  honest ceiling after Path A is unchanged in kind: semantic weakness with no
  structural handle.

I then pushed harder than my own check, in `extra_probes.py`:

- **Cat J — 5 fresh weak paraphrases** ("sole ferret", "just one recruit",
  "message board", "halted once the numbers turned positive", "nothing to
  contrast against"): **5/5 caught**.
- **Cat K — 5 false-positive guards**: strong claims phrased to *look* weak —
  "not a single one was lost to follow-up", an expert/consensus "forum", a
  within-subject crossover with "no separate comparison arm", a trial "ended
  after its prespecified duration; results were favourable". **5/5 correctly
  PASS.**

Cat K earned its keep, and so did a fuller nine-method self-attack battery
(`self_attack.py`, the round-3 list you sketched). Two genuine precision bugs
fell out and I fixed both:

- **Bare "forum" over-fired** on an expert/consensus forum (it passed only
  because the meta-analysis evidence buried it — a latent false positive).
  Tightened to require an online-forum qualifier; the v2 forum probe still
  fires via "thread on".
- **A prespecified-duration stop** dodged the optional-stopping regex only by a
  character-window fluke. I added a `_SCHEDULED_STOP_TOKENS` guard so a
  prespecified / group-sequential interim stop no longer reads as optional
  stopping — a real precision gain, robust now rather than lucky.

What the battery did **not** make me do is the important part. Method 1
(vocabulary substitution) misses 5/5 and Method 3 (cross-domain) 2/4 — "brought
the experiment to a close", "no yardstick to measure against", "lone prototype".
I did not extend the verb/noun lists to pass them, because (a) it just defers
the miss one paraphrase, and (b) it provably trades precision: broadening
single-subject nouns to "single trial/run/sample" false-fires on "a single
large trial of 4,000". That vocabulary boundary is doing real work; the honest
fix is Path B, not a longer list.

That residual — schedule-vs-outcome stopping, population mismatch / surrogate
endpoints stated only in prose, single subjects named outside the noun list —
is Path B, the embedding-similarity scorer (future-work item #1), the
principled fix you've pointed at since round 2. Path A is the
structure-extraction step that's implementable today without new dependencies;
it does not pretend to be Path B.

## 5. No tuning, no regressions

- Threshold unchanged at **0.80**. Nothing was re-fit to make probes pass.
- `heldout_datss_probes.py` (round 1): still **10/10**.
- `extra_probes.py`: **29/35** (was 18/25); **12/12 PASS intact** — including
  the 5 cat-K false-positive guards. Path A added no false positives on strong
  claims, even ones phrased to look weak.
- `pytest`: **20/20**.
- The strong v2 PASS case is unchanged at DAS 0.697.

Reproduce:

```bash
python heldout_datss_probes_v2.py        # 8/8
python path_a_generalization_check.py    # 10/10 caught; 3/3 ceiling missed
python self_attack.py                    # nine-method battery (raw behaviour)
python heldout_datss_probes.py           # 10/10
python extra_probes.py                   # 29/35, 12/12 PASS (incl. cat J/K)
pytest datss/tests/ -v                   # 20/20
```

The full reasoning, per-feature receipts, and the documented ceiling are in
`DESIGN.md` iteration 17 (§2), §5.7 (calibration), §7.8 (vocabulary ceiling),
§7.9–§7.10 (stress test + self-attack battery), and §8 (Path A as the interim
step toward the Path B embedding scorer). README, DESIGN.md and the code now
report the same numbers.
