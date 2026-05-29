"""
Extra robustness probes — independent of heldout_datss_probes.py (the
round-2 reviewer's file, kept verbatim) and of adversarial_cases.csv (my
adversary-first 30-case corpus already in datss/evaluation/).

The reviewer's probe set is good but small (10 cases) and hits a specific
cluster of failure modes (single-subject, founder anecdote, in vitro,
stopped early, no comparison arm, group testimonial). The point of THIS
file is to test the gate against a broader range of evidentiary failure
modes that the reviewer's set doesn't directly probe — and against PASS
cases phrased in less stereotyped ways — so I can honestly report which
angles the structural scorer covers and which it doesn't.

Probe categories:
  A. Correlation framed as causation (observational confounding)
  B. Effect-vs-n implausibility (giant claim, moderate n)
  C. Pseudo-replication / non-independent confirmation
  D. Surrogate-endpoint substitution
  E. Population-mismatch overreach
  F. Selective outcome reporting / endpoint switching
  G. Indirect / hard-to-detect COI
  H. Clear PASS, varied phrasings
  I. Edge cases that probe the structural ceiling honestly

Run as: python extra_probes.py

This is for diagnostic stress-testing of the gate, not for re-tuning.
Threshold is read from the existing report.json (the gate's operational
value), exactly as run_adversarial.py does.
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
    """Use the tuned threshold from report.json if available, else the named default."""
    if not os.path.exists(REPORT_PATH):
        return TAU_GATE_DAS
    try:
        with open(REPORT_PATH) as f:
            return float(json.load(f)["selected_threshold"])
    except (KeyError, ValueError, OSError):
        return TAU_GATE_DAS


PROBES: List[Tuple[str, str, Dict[str, Any], str]] = [
    # ---- A. Correlation framed as causation ------------------------------
    ("A_coffee",
     "Coffee drinkers in our 80,000-person survey lived three years longer on average, "
     "so coffee extends lifespan.",
     {"design": "cross-sectional survey", "n": 80000,
      "adjustment": "age and sex only"},
     "FAIL"),

    ("A_optimism",
     "People who reported being more optimistic at baseline were less likely to develop "
     "heart disease, which shows optimism prevents heart disease.",
     {"design": "observational cohort", "n": 5400,
      "confounders_not_adjusted": ["income", "social support", "baseline health"]},
     "FAIL"),

    ("A_supplement_users",
     "Adults who report taking multivitamins live 1.8 years longer on average; we "
     "recommend multivitamins for longevity.",
     {"design": "self-report consumption survey", "n": 22000,
      "note": "users likely differ on baseline health and SES"},
     "FAIL"),

    # ---- B. Effect-vs-n implausibility -----------------------------------
    ("B_huge_effect_small",
     "The intervention reduced biological age by 12 years in our adults.",
     {"n": 18, "design": "open-label", "measurement": "epigenetic clock"},
     "FAIL"),

    ("B_double_lifespan",
     "Lifespan was effectively doubled in the treated cohort.",
     {"n": 24, "design": "single-arm pilot"},
     "FAIL"),

    ("B_perfect_response",
     "Every single patient responded; cure rate was 100%.",
     {"n": 11, "design": "single-arm, selected by treating clinician"},
     "FAIL"),

    # ---- C. Pseudo-replication / non-independent confirmation ------------
    ("C_same_lab",
     "We replicated the finding in three follow-up experiments run by the same lab.",
     {"design": "three sequential runs in originating lab",
      "n_per_run": 8, "investigators": "same team"},
     "FAIL"),

    ("C_friendly_replication",
     "A collaborator who consulted on the original protocol confirmed the result.",
     {"design": "single follow-up by collaborator",
      "n": 14, "note": "collaborator was author on original"},
     "FAIL"),

    # ---- D. Surrogate-endpoint substitution ------------------------------
    ("D_surrogate_only",
     "The therapy reduced a blood biomarker by 22%, so we expect it to reduce "
     "cardiovascular mortality.",
     {"design": "RCT", "n": 320,
      "primary_endpoint": "biomarker change",
      "clinical_endpoint": "not measured"},
     "FAIL"),

    ("D_imaging_proxy",
     "Brain volume on MRI increased after the supplement, indicating cognitive "
     "improvement.",
     {"design": "single-arm, MRI-only",
      "n": 40, "cognitive_testing": "not performed"},
     "FAIL"),

    # ---- E. Population-mismatch overreach --------------------------------
    ("E_young_to_old",
     "The drug improves muscle strength in healthy adults aged 22-35, so it will "
     "help frail elderly patients regain mobility.",
     {"design": "RCT in young healthy adults", "n": 96,
      "studied_population": "ages 22-35",
      "claimed_population": "frail elderly"},
     "FAIL"),

    ("E_men_to_women",
     "The hormone therapy reduced fracture risk in our male cohort; women should "
     "consider taking it for the same reason.",
     {"design": "RCT in men only", "n": 1200,
      "claimed_for": "women"},
     "FAIL"),

    # ---- F. Selective outcome reporting / endpoint switching -------------
    ("F_endpoint_switch",
     "Although the original primary endpoint did not move, our updated analysis on a "
     "different outcome shows a significant improvement.",
     {"design": "RCT", "n": 240,
      "preregistered_primary": "no change",
      "reported_endpoint": "added after unblinding"},
     "FAIL"),

    ("F_subgroup_only",
     "While the overall trial was negative, the subgroup of patients with the highest "
     "baseline values showed a meaningful benefit.",
     {"design": "post-hoc subgroup", "n_subgroup": 38,
      "preregistered": False},
     "FAIL"),

    # ---- G. Indirect / hard-to-detect COI --------------------------------
    ("G_founder_owns",
     "Our team's clinical work supports the approach. (Trial led by Dr. X, who also "
     "founded the company that holds the patent.)",
     {"design": "open-label trial", "n": 60,
      "investigator_role": "also founder and patent holder"},
     "FAIL"),

    ("G_paid_speakers",
     "All three co-authors of the favorable interpretation are paid consultants to the "
     "drug's manufacturer.",
     {"design": "narrative review", "n": None,
      "author_disclosures": "paid consultancies undisclosed in main text"},
     "FAIL"),

    # ---- H. Clear PASS, varied phrasings ---------------------------------
    ("H_cluster_rct",
     "A cluster-randomized trial across 84 primary-care clinics enrolling 12,400 "
     "patients found a small but consistent reduction in hospitalization over two years.",
     {"design": "cluster-randomized, multi-center", "n": 12400,
      "duration": "two years", "preregistered": True},
     "PASS"),

    ("H_crossover_washout",
     "A double-blind crossover trial with a four-week washout between phases showed "
     "the medication consistently reduced the symptom score across both periods.",
     {"design": "double-blind crossover with washout", "n": 88},
     "PASS"),

    ("H_mendelian_random",
     "Mendelian randomization analysis using three independent genetic instruments "
     "supported a causal effect of LDL on cardiovascular events, consistent with the "
     "results of subsequent randomized trials.",
     {"design": "Mendelian randomization plus RCT confirmation",
      "n_genetic": 380000,
      "replicated_by": ["statin trials", "PCSK9 trials"]},
     "PASS"),

    ("H_stepped_wedge",
     "Under a stepped-wedge implementation across 22 hospitals, the protocol change "
     "produced a measurable improvement in the primary safety outcome with prospective "
     "blinded adjudication.",
     {"design": "stepped-wedge implementation trial", "n": 7800,
      "outcome_adjudication": "blinded"},
     "PASS"),

    ("H_negative_then_replicated",
     "Two large preregistered trials failed to find a benefit; a third, also "
     "preregistered, replicated the negative finding. The intervention does not work "
     "as claimed.",
     {"design": "three preregistered RCTs", "n": 18000,
      "finding": "null effect replicated"},
     "PASS"),

    # ---- I. Honest-edge / structural-ceiling probes ----------------------
    ("I_small_but_clean",
     "A small but careful preregistered trial of 38 patients, randomized and blinded, "
     "found a modest improvement in the primary outcome; the authors note replication "
     "is needed before clinical adoption.",
     {"design": "preregistered randomized blinded", "n": 38,
      "claim_strength": "modest, caveated"},
     "PASS"),

    ("I_thin_but_real",
     "Initial findings from a 14-patient open-label pilot are encouraging; the "
     "investigators have not yet drawn clinical conclusions.",
     {"design": "open-label pilot", "n": 14,
      "claim_strength": "explicitly tentative"},
     "BORDERLINE"),

    ("I_strong_design_thin_claim",
     "A large preregistered RCT measured a 0.4% reduction in the primary endpoint, "
     "which the authors describe as not clinically meaningful despite statistical "
     "significance.",
     {"design": "preregistered RCT", "n": 8400,
      "claim_strength": "statistically significant but clinically tiny"},
     "PASS"),

    ("I_evasive_weak",
     "The procedure has been used successfully in our network for some years now.",
     {"design": "clinical experience report",
      "n": "not specified", "outcomes": "narrative"},
     "FAIL"),

    ("I_extreme_simple",
     "Trust me on this one — it works.",
     {"evidence": "personal certainty"},
     "FAIL"),

    # ---- J. Path-A generalisation: fresh weak paraphrases ----------------
    # None of these phrasings appear in heldout_datss_probes_v2.py or in
    # path_a_generalization_check.py. They test whether the round-3 structure
    # extractors fire on a class of phrasings rather than memorised strings.
    ("J_sole_ferret",
     "Our sole ferret bounced back to youthful vigour after a single dose.",
     {"design": "watched the animal afterward"},
     "FAIL"),

    ("J_one_recruit",
     "Just one recruit received the compound, and his markers reversed entirely.",
     {"design": "watched him afterward"},
     "FAIL"),

    ("J_message_board",
     "A regular on an anti-ageing message board reported the protocol delivered "
     "dramatic gains.",
     {"source": "message board post"},
     "FAIL"),

    ("J_halted_positive",
     "The study was halted once the numbers turned positive.",
     {"n": 24},
     "FAIL"),

    ("J_nothing_contrast",
     "We simply had nothing to contrast the treated group against.",
     {"n": 33},
     "FAIL"),

    # ---- K. False-positive guards: strong claims that LOOK like Path-A ---
    # triggers. Real generalisation means the extractors do NOT fire here.
    # If any of these flip to FAIL, the regex is overfiring on surface form.
    ("K_not_single_lost",
     "Across 4,200 randomized participants in a preregistered double-blind trial, "
     "not a single one was lost to follow-up, and mortality fell; the result was "
     "independently replicated.",
     {"n": 4200, "design": "RCT double-blind preregistered",
      "replicated_by": ["group A", "group B"]},
     "PASS"),

    ("K_expert_forum",
     "A consensus forum of forty independent experts, drawing on a preregistered "
     "meta-analysis of 30 randomized trials, endorsed the mortality finding.",
     {"design": "meta-analysis of 30 RCTs", "n": 51000},
     "PASS"),

    ("K_within_subject_nocompare",
     "There was no separate comparison arm because the double-blind within-subject "
     "crossover design makes each patient serve as their own control.",
     {"n": 120, "design": "double-blind within-subject crossover"},
     "PASS"),

    ("K_prespecified_stop",
     "The trial ended after its prespecified two-year duration; the preregistered "
     "results were favourable.",
     {"n": 8000, "design": "preregistered RCT"},
     "PASS"),

    ("K_single_factor",
     "Across a large multi-site cohort with subsequent RCT confirmation, the single "
     "strongest predictor of survival was the intervention.",
     {"n": 9000, "design": "multi-site cohort plus RCT confirmation",
      "replicated_by": ["confirmatory RCT"]},
     "PASS"),
]


def main() -> None:
    clear_default_cache()
    threshold = _tuned_threshold()
    print(
        f"Extra robustness probes: {len(PROBES)} cases. "
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
            flag = "—"  # BORDERLINE has no fixed ground truth

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
        "J": "Path-A generalisation: fresh weak paraphrases",
        "K": "Path-A false-positive guards (strong claims that look weak)",
    }
    for cat in sorted(by_category):
        n = by_category[cat]
        # only count decisive in this denominator
        decisive_in_cat = sum(
            1 for pid, _, _, lbl in PROBES
            if pid.split("_", 1)[0] == cat and lbl in ("PASS", "FAIL")
        )
        c = by_category_correct[cat]
        if decisive_in_cat == 0:
            print(f"  {cat}  {category_descriptions[cat]:<55} {n} cases (no decisive)")
        else:
            print(
                f"  {cat}  {category_descriptions[cat]:<55} "
                f"{c}/{decisive_in_cat} correct"
            )


if __name__ == "__main__":
    main()
