"""
Path-A generalisation check (round-3 self-authored, NOT from the reviewer).

The round-3 reviewer's v2 probes exposed a split: weaknesses encoded in a
structured evidence-dict field were caught; weaknesses living only in free
text were missed because the token lists are fixed substrings. Path A replaces
those with regexes that extract STRUCTURE from a class of phrasings.

The honest question Path A has to answer is: did it generalise, or did it just
memorise the reviewer's eight strings? This file tests that directly.

  PART 1  Novel paraphrases of the SAME structural weakness, none of which
          appear in heldout_datss_probes_v2.py. If Path A generalised, these
          are caught (FAIL).
  PART 2  The honest ceiling: weaknesses that are semantic, not pattern-shaped
          (population mismatch / surrogate endpoint stated only in prose, or a
          single subject named with a noun outside the extractor vocabulary).
          These are STILL missed. This is the embedding-scorer's job
          (future-work item #1), and naming it keeps the docs honest.

Run as: python path_a_generalization_check.py
"""

from datss.models import ChallengeInput
from datss.gate import run_challenge

# PART 1 — novel paraphrases of covered structural classes (expect FAIL).
GENERALISES = [
    ("single-subject / novel noun",
     "The solitary test subject improved markedly after a single dose.",
     {"design": "observed afterward"}),
    ("single-subject / novel noun",
     "We dosed a single hamster and saw striking rejuvenation.",
     {"design": "one shot, observed later"}),
    ("single-subject / quantifier",
     "Only one volunteer was given the compound, and he reported feeling decades younger.",
     {"source": "personal note"}),
    ("named single person",
     "My neighbour insists the protocol restored his energy overnight.",
     {"source": "personal conversation"}),
    ("informal source / novel outlet",
     "A post in a Facebook group described remarkable anti-ageing results.",
     {"source": "facebook group post"}),
    ("informal source / novel outlet",
     "Someone on Reddit reported the stack cured their chronic fatigue.",
     {"source": "reddit comment"}),
    ("optional stopping / paraphrase",
     "We halted the trial as soon as the numbers looked good.",
     {"n": 22}),
    ("optional stopping / paraphrase",
     "Data collection ended once the effect turned favourable.",
     {"n": 26}),
    ("no comparison / paraphrase",
     "There was simply no group to compare our treated patients against.",
     {"n": 31}),
    ("no comparison / paraphrase",
     "We ran the whole thing without any comparator.",
     {"n": 28}),
]

# PART 2 — the honest ceiling: STILL missed (semantic, not pattern-shaped).
CEILING = [
    ("population mismatch in prose (no dict keys)",
     "The drug restored strength in college athletes, so it will obviously help "
     "frail nursing-home residents regain mobility.",
     {"design": "randomized trial", "n": 90}),
    ("surrogate endpoint in prose (no dict marker)",
     "Cholesterol fell sharply on the therapy, so heart attacks will surely drop too.",
     {"design": "randomized trial", "n": 300}),
    ("single subject / noun outside vocabulary",
     "The one gentleman we enrolled recovered completely within days.",
     {"design": "observed afterward"}),
]


def _run(claim, ev):
    return run_challenge(
        ChallengeInput(claim=claim, evidence=ev, component_id="probe"),
        use_cache=False,
    )


def main() -> None:
    print("PART 1 — novel paraphrases of covered classes (want FAIL)")
    print("-" * 78)
    caught = 0
    for label, claim, ev in GENERALISES:
        r = _run(claim, ev)
        ok = r.decision.value == "FAIL"
        caught += ok
        print(f"  [{'OK ' if ok else 'MISS'}] {r.decision.value:<4} das={r.das:.3f}  {label}")
    print(f"\n  generalised: {caught}/{len(GENERALISES)} novel paraphrases caught\n")

    print("PART 2 — honest ceiling: expected to be MISSED (semantic, not pattern)")
    print("-" * 78)
    for label, claim, ev in CEILING:
        r = _run(claim, ev)
        # 'leak' means the gate happened to catch it via some other signal;
        # 'ceiling' means it slipped through as predicted.
        tag = "ceiling (missed, as documented)" if r.decision.value == "PASS" else "caught via other signal"
        print(f"  [{r.decision.value:<4} das={r.das:.3f}]  {label}  -> {tag}")


if __name__ == "__main__":
    main()
