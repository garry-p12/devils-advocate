"""
extra_probes_v2.py — second independent robustness stress test.

Authored AFTER implementing the round-2 structural detectors
(correlation→causation, surrogate endpoint, population mismatch,
endpoint switching, paid COI, pseudo-replication, sparse evidence) but
with deliberately different phrasings than extra_probes.py. The point is
to test whether the detectors generalise to the *concept* of each
weakness or only to the specific phrasings in v1.

Same threshold (0.80, from report.json), same instrumentation. Run as:

    python extra_probes_v2.py

I am NOT modifying structural.py in response to whatever this file
prints. The honest test is one-shot: I write the probes, run the file,
report the result.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from typing import Any, Dict, List, Tuple

from datss import ChallengeInput, GateDecision, clear_default_cache, run_challenge
from datss.thresholds import TAU_GATE_DAS

REPORT_PATH = os.path.join(
    os.path.dirname(__file__), "datss", "evaluation", "report.json"
)


def _tuned_threshold() -> float:
    if not os.path.exists(REPORT_PATH):
        return TAU_GATE_DAS
    try:
        with open(REPORT_PATH) as f:
            return float(json.load(f)["selected_threshold"])
    except (KeyError, ValueError, OSError):
        return TAU_GATE_DAS


# Same nine categories as extra_probes.py, different phrasings.
PROBES: List[Tuple[str, str, Dict[str, Any], str]] = [
    # ---- A. Correlation framed as causation ------------------------------
    ("A_walnuts",
     "Adults who eat walnuts daily develop dementia 4 years later on average, so "
     "walnuts protect against cognitive decline.",
     {"design": "questionnaire-based cohort", "n": 41000,
      "adjustment": "minimal"},
     "FAIL"),
    ("A_friend_count",
     "People with more close friends in their 50s lived measurably longer; "
     "expanding your social circle adds years to your life.",
     {"design": "prospective observational", "n": 9800},
     "FAIL"),
    ("A_morning_runs",
     "Among the 22,000 respondents, morning exercisers had a 28% lower rate of "
     "depression diagnoses — exercising before noon prevents depression.",
     {"design": "cross sectional", "n": 22000},
     "FAIL"),

    # ---- B. Effect-vs-n implausibility -----------------------------------
    ("B_decade_younger",
     "Subjects appeared a decade younger after the intervention.",
     {"n": 22, "design": "single-arm pilot"},
     "FAIL"),
    ("B_quintuple",
     "Memory test scores quintupled after a month on the protocol.",
     {"n": 9, "design": "open label"},
     "FAIL"),
    ("B_all_healed",
     "Every participant recovered full function within two weeks.",
     {"n": 13, "design": "single-arm, investigator-selected enrolment"},
     "FAIL"),

    # ---- C. Pseudo-replication ------------------------------------------
    ("C_in_house_followup",
     "We re-ran the assay four more times in our lab and obtained the same effect.",
     {"design": "in-house follow-ups", "n_per_run": 6,
      "investigators": "originating team"},
     "FAIL"),
    ("C_protocol_advisor",
     "Confirmation came from an investigator who had advised on the original study "
     "design.",
     {"design": "single confirmation by protocol advisor",
      "n": 18},
     "FAIL"),

    # ---- D. Surrogate-endpoint substitution ------------------------------
    ("D_blood_marker",
     "Treatment reduced an inflammatory blood marker by 31%, suggesting "
     "long-term cardiovascular protection.",
     {"design": "RCT", "n": 410,
      "primary_endpoint": "biomarker",
      "clinical_endpoint": "not measured"},
     "FAIL"),
    ("D_no_function_test",
     "Plasma neurofilament dropped after six months on the drug, so we expect "
     "clinical slowing of disease progression.",
     {"design": "open-label", "n": 70,
      "primary_endpoint": "biomarker",
      "cognitive_testing": "not performed"},
     "FAIL"),

    # ---- E. Population-mismatch overreach --------------------------------
    ("E_athletes_to_seniors",
     "The supplement enhanced VO2 max in elite male athletes aged 18-26; we "
     "recommend it for community-dwelling seniors with mobility limits.",
     {"design": "RCT in elite athletes", "n": 64,
      "studied_population": "elite male athletes 18-26",
      "claimed_population": "community-dwelling seniors"},
     "FAIL"),
    ("E_pediatric_to_adult",
     "The vaccine was tested in healthy children aged 5-11; we are extending the "
     "indication to immunocompromised adults.",
     {"design": "pediatric RCT", "n": 1200,
      "studied_in": "healthy children 5-11",
      "claimed_for": "immunocompromised adults"},
     "FAIL"),

    # ---- F. Selective outcome reporting / endpoint switching -------------
    ("F_swapped_primary",
     "While the originally specified primary endpoint did not reach significance, "
     "an exploratory secondary endpoint added after seeing the data was clearly "
     "positive.",
     {"design": "RCT", "n": 540,
      "preregistered_primary": "no change",
      "reported_endpoint": "added after unblinding"},
     "FAIL"),
    ("F_responder_only",
     "Although the trial overall was null, the subgroup of patients with the "
     "highest baseline biomarker showed a strong effect.",
     {"design": "post-hoc subgroup", "n_subgroup": 41,
      "preregistered": False},
     "FAIL"),

    # ---- G. Indirect / hard-to-detect COI --------------------------------
    ("G_advisory_board",
     "The clinical lead, who reports findings here as favorable, sits on the "
     "advisory board of the drug's developer and receives consulting fees.",
     {"design": "open-label trial", "n": 88,
      "author_disclosures": "consulting fees undisclosed in main text"},
     "FAIL"),
    ("G_speaker_circuit",
     "Two of the three co-authors are paid speakers for the manufacturer's "
     "educational program.",
     {"design": "narrative review", "n": None,
      "author_disclosures": "paid speakers undisclosed"},
     "FAIL"),

    # ---- H. Clear PASS, varied phrasings ---------------------------------
    ("H_factorial_rct",
     "A factorial RCT enrolling 3,800 patients across 26 sites compared four "
     "treatment combinations against placebo with blinded outcome adjudication; "
     "results were preregistered and independently re-analysed.",
     {"design": "factorial preregistered RCT", "n": 3800,
      "outcome_adjudication": "blinded",
      "replicated_by": ["independent re-analysis"]},
     "PASS"),
    ("H_adaptive_platform",
     "An adaptive platform trial running across 84 ICUs over three years tested "
     "multiple interventions on a shared control arm, with preregistered "
     "stopping rules and blinded outcome assessment.",
     {"design": "adaptive platform trial, preregistered",
      "n": 12200},
     "PASS"),
    ("H_cluster_negative",
     "A cluster-randomised trial of a workplace intervention in 312 worksites "
     "found no effect on the primary outcome and the authors recommend against "
     "scaling the intervention.",
     {"design": "cluster-randomized, preregistered",
      "n": 24500,
      "finding": "null effect, authors recommend against adoption"},
     "PASS"),
    ("H_meta_dose_response",
     "A network meta-analysis of 52 randomised trials covering 88,000 "
     "participants showed a clear dose-response relationship consistent across "
     "regions and risk strata.",
     {"design": "network meta-analysis of 52 RCTs",
      "n": 88000},
     "PASS"),
    ("H_quasi_experiment",
     "A regression-discontinuity analysis of a policy threshold change "
     "produced a clean estimate of the policy's effect on hospitalisations, "
     "consistent with parallel evidence from an independent jurisdiction.",
     {"design": "regression discontinuity plus independent replication",
      "n": 220000,
      "replicated_by": ["independent jurisdiction"]},
     "PASS"),

    # ---- I. Honest-edge probes ------------------------------------------
    ("I_modest_real",
     "A preregistered randomised trial of 64 participants with blinded assessment "
     "found a small effect on the primary outcome; the authors describe the "
     "result as preliminary and call for a larger replication.",
     {"design": "preregistered randomised blinded", "n": 64,
      "claim_strength": "preliminary, caveated"},
     "PASS"),
    ("I_brag",
     "It just works. You'll see when you try it.",
     {"evidence": "personal certainty"},
     "FAIL"),
    ("I_tiny_caveated",
     "Early observations from an 11-patient open pilot suggest a possible signal; "
     "the investigators have explicitly avoided drawing clinical conclusions.",
     {"design": "open-label pilot", "n": 11,
      "claim_strength": "tentative"},
     "BORDERLINE"),
    ("I_clinic_years",
     "We have been using this protocol in our clinic for several years and the "
     "outcomes have generally been good.",
     {"design": "clinical experience report",
      "n": "not specified"},
     "FAIL"),
]


def main() -> None:
    clear_default_cache()
    threshold = _tuned_threshold()
    print(
        f"extra_probes_v2: {len(PROBES)} cases. "
        f"Threshold = {threshold:.2f} (from datss/evaluation/report.json)."
    )
    print()
    print(f"{'id':<28}  {'expected':<10}  {'got':<5}  {'das':>6}  flag")
    print("-" * 78)

    correct_decisive = 0
    decisive_total = 0
    by_label = Counter()
    by_label_correct = Counter()
    by_category = Counter()
    by_category_correct = Counter()

    for probe_id, claim, ev, expected in PROBES:
        r = run_challenge(
            ChallengeInput(claim=claim, evidence=ev, component_id="probe"),
            das_threshold=threshold,
            use_cache=False,
        )
        category = probe_id.split("_", 1)[0]
        by_label[expected] += 1
        by_category[category] += 1

        if expected in ("PASS", "FAIL"):
            decisive_total += 1
            flag = "OK" if r.decision.value == expected else "MISS"
            if flag == "OK":
                correct_decisive += 1
                by_label_correct[expected] += 1
                by_category_correct[category] += 1
        else:
            flag = "—"

        print(
            f"{probe_id:<28}  {expected:<10}  {r.decision.value:<5}  "
            f"{r.das:>6.3f}  {flag}"
        )

    acc = correct_decisive / decisive_total if decisive_total else 0.0
    print()
    print("Summary by label")
    print("----------------")
    for lbl in ("PASS", "FAIL", "BORDERLINE"):
        n = by_label.get(lbl, 0)
        if not n:
            continue
        if lbl in ("PASS", "FAIL"):
            print(f"  {lbl:<10}: {by_label_correct[lbl]}/{n} correct")
        else:
            print(f"  {lbl:<10}: {n} cases (no fixed ground truth)")
    print(f"  Accuracy (PASS+FAIL only): {acc*100:.2f}%")

    print()
    print("Summary by category (PASS+FAIL only)")
    print("------------------------------------")
    category_descriptions = {
        "A": "correlation framed as causation",
        "B": "effect-vs-n implausibility",
        "C": "pseudo-replication",
        "D": "surrogate-endpoint substitution",
        "E": "population-mismatch overreach",
        "F": "selective outcome reporting / endpoint switching",
        "G": "indirect / hard-to-detect COI",
        "H": "clear PASS, varied phrasings",
        "I": "honest-edge / structural-ceiling probes",
    }
    for cat in sorted(by_category):
        decisive_in_cat = sum(
            1 for pid, _, _, lbl in PROBES
            if pid.split("_", 1)[0] == cat and lbl in ("PASS", "FAIL")
        )
        c = by_category_correct[cat]
        n = by_category[cat]
        if decisive_in_cat == 0:
            print(f"  {cat}  {category_descriptions[cat]:<55} {n} cases (no decisive)")
        else:
            print(
                f"  {cat}  {category_descriptions[cat]:<55} "
                f"{c}/{decisive_in_cat} correct"
            )


if __name__ == "__main__":
    main()
