"""
Held-out probe set from the CureForge reviewer (round 2 feedback).

Probes weak claims phrased without trigger keywords and strong claims phrased
plainly. Run as:

    python heldout_datss_probes.py

The point is to evaluate the gate's ability to score evidentiary STRUCTURE
(sample size, control presence, replication, design integrity) rather than
keyword/vocabulary patterns.
"""

from datss.models import ChallengeInput
from datss.gate import run_challenge

PROBES = [
    # Genuinely weak, phrased without trigger keywords (should FAIL):
    ("A single mouse lived 40% longer after we gave it the compound once.",
     {"n": 1, "design": "one animal, observed a single time", "source": "lab notebook"},
     "FAIL"),

    ("Our founder took the supplement and felt twenty years younger within a week.",
     {"source": "personal account", "measurement": "how he felt"}, "FAIL"),

    ("The molecule reversed aging in a dish of cells we ordered online.",
     {"system": "cells in a dish", "runs": 1}, "FAIL"),

    ("We are confident this extends lifespan; the result simply felt very strong.",
     {"evidence": "investigator judgment", "statistics": "none computed"}, "FAIL"),

    ("The therapy clearly works - we ended the study early once the numbers looked good.",
     {"design": "halted when results looked promising", "n": 12}, "FAIL"),

    ("Everyone in our group who tried it reported feeling sharper.",
     {"group_size": 6, "outcome": "subjective reports"}, "FAIL"),

    ("Because the effect was so large, we did not feel a comparison arm was necessary.",
     {"design": "no comparison arm by design", "effect": "large"}, "FAIL"),

    # Genuinely strong, phrased plainly (should PASS):
    ("A randomized, double-blind, placebo-controlled trial of 4,200 participants, "
     "preregistered and NIH-funded, found reduced mortality; published in NEJM and "
     "independently replicated.",
     {"n": 4200, "design": "RCT double-blind placebo-controlled",
      "funding": "NIH R01", "journal": "NEJM",
      "replicated_by": ["group A", "group B"]}, "PASS"),

    ("A preregistered meta-analysis of 38 randomized controlled trials confirmed the "
     "effect with a clear dose-response and established mechanism.",
     {"design": "meta-analysis of 38 RCTs", "n": 51000,
      "mechanism": "elucidated"}, "PASS"),

    ("Across three independent multi-center cohorts spanning diverse populations, the "
     "intervention showed a consistent, dose-dependent reduction in the biomarker, "
     "with prospective, blinded assessment.",
     {"design": "three multi-center prospective cohorts", "n": 12000,
      "assessment": "blinded"}, "PASS"),
]


def main() -> None:
    correct = 0
    print(f"{'expected':<8}  {'got':<5}  {'das':>6}  {'flag':<5}  claim_snippet")
    print("-" * 90)
    for claim, ev, expected in PROBES:
        r = run_challenge(
            ChallengeInput(claim=claim, evidence=ev, component_id="probe"),
            use_cache=False,
        )
        flag = "OK" if r.decision.value == expected else "MISS"
        if flag == "OK":
            correct += 1
        snippet = claim[:55] + ("..." if len(claim) > 55 else "")
        print(f"{expected:<8}  {r.decision.value:<5}  {r.das:>6.3f}  {flag:<5}  {snippet}")
    print()
    print(f"Score: {correct}/{len(PROBES)} correct")


if __name__ == "__main__":
    main()
