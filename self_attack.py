"""
Systematic self-attack battery (round 3).

Implements the nine scriptable diagnostics from the reviewer's "how do I
attack my own system" list (the tenth, adversary-first authoring, is a
discipline this whole file follows: every probe below was written to expose a
weakness, and whatever the gate does is reported verbatim — nothing here is
tuned to make a number look good).

Each method answers one question:

  1. Vocabulary substitution   - does swapping synonyms change the verdict?
  2. Dict vs free-text         - which layer does the catching?
  3. Cross-domain transfer     - did it learn structure or biology register?
  4. Minimal perturbation      - how thin is the detection margin?
  5. Null evidence dict        - what happens with no structured input at all?
  6. PASS-case stripping       - at what point does a strong claim flip?
  7. Paraphrase battery        - 10 paraphrases per detector, how many hold?
  8. Compound vs single        - does stacking weaknesses raise DAS?
  9. Threshold sensitivity     - is 0.80 a real boundary or a smear?

Run: python self_attack.py
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from datss.models import ChallengeInput
from datss.gate import run_challenge
from datss.thresholds import TAU_GATE_DAS


def _das(claim: str, ev: Dict[str, Any]) -> Tuple[str, float]:
    r = run_challenge(
        ChallengeInput(claim=claim, evidence=ev, component_id="probe"),
        use_cache=False,
    )
    return r.decision.value, r.das


def _row(label: str, claim: str, ev: Dict[str, Any], want: str | None = None) -> bool:
    verdict, das = _das(claim, ev)
    flag = ""
    ok = True
    if want is not None:
        ok = verdict == want
        flag = "  OK" if ok else "  <-- MISS"
    print(f"  {verdict:<4} {das:5.3f}{flag:<11} {label}")
    return ok


def header(n: int, title: str) -> None:
    print(f"\n{'='*78}\nMETHOD {n}. {title}\n{'='*78}")


# --------------------------------------------------------------------------
def method_1_vocab_substitution() -> None:
    header(1, "Vocabulary substitution — synonyms NOT in any token list")
    print("Weak claims (want FAIL). A miss means the detector is vocabulary-bound.")
    # stopped-early synonyms outside _STOPPED_EARLY_TOKENS and _OUTCOME_STOP_RE
    _row("stop: 'brought the experiment to a close as soon as readings looked encouraging'",
         "We brought the experiment to a close as soon as the readings looked encouraging.",
         {"n": 20}, "FAIL")
    _row("stop: 'pulled the plug the instant the curve bent our way'",
         "We pulled the plug the instant the curve bent our way.",
         {"n": 20}, "FAIL")
    # no-control synonyms outside _NO_CONTROL_TOKENS and _NO_COMPARISON_RE
    _row("no-control: 'no yardstick to measure our patients against'",
         "There was no yardstick to measure our patients against.",
         {"n": 30}, "FAIL")
    _row("no-control: 'we never ran a parallel untreated set'",
         "We never ran a parallel untreated set.",
         {"n": 30}, "FAIL")
    # weak-source synonyms
    _row("source: 'a chap I met at a conference bar told me'",
         "A chap I met at a conference bar told me it works wonders.",
         {"source": "hallway chat"}, "FAIL")


def method_2_dict_vs_freetext() -> None:
    header(2, "Dict vs free-text isolation — same weakness, two encodings")
    claim = "The lone subject showed a dramatic improvement."
    print("Same single-subject weakness:")
    _row("weakness in dict   {'n': 1}", claim, {"n": 1}, "FAIL")
    _row("weakness in text   {'design': 'we observed the outcome'}",
         claim, {"design": "we observed the outcome"}, "FAIL")
    _row("misleading dict    {'n': 'cohort'}  (text still says 'lone subject')",
         claim, {"design": "we observed the outcome"}, "FAIL")


def method_3_cross_domain() -> None:
    header(3, "Cross-domain transfer — same structure, no biology vocabulary")
    print("Longevity FAIL cases rewritten into other domains (want FAIL).")
    _row("materials: 'lone prototype' free-text, n absent",
         "Our lone prototype passed the stress test after a single tuning pass.",
         {"design": "observed afterward"}, "FAIL")
    _row("materials: n=3 in dict",
         "Three units survived the stress test, with no baseline batch.",
         {"n": 3}, "FAIL")
    _row("economics: 'wound down the pilot once the figures looked good'",
         "We wound down the pilot once the figures looked good.",
         {"n": 25}, "FAIL")
    _row("economics: 'nothing to benchmark our markets against'",
         "There was nothing to benchmark our treated markets against.",
         {"n": 40}, "FAIL")


def method_4_minimal_perturbation() -> None:
    header(4, "Minimal perturbation — smallest change that flips a verdict")
    base = "Everyone in our group who tried it reported feeling sharper."
    print("Baseline (group testimonial, subjective):")
    _row("base  {'group_size': 6, 'outcome': 'subjective reports'}",
         base, {"group_size": 6, "outcome": "subjective reports"}, "FAIL")
    print("One-word / one-field perturbations:")
    _row("swap 'feeling sharper' -> 'improvement'",
         "Everyone on the team who tried it noticed improvement.",
         {"group_size": 6, "outcome": "subjective reports"}, "FAIL")
    _row("drop the subjective dict field",
         "Everyone on the team who tried it noticed improvement.",
         {"group_size": 6}, "FAIL")


def method_5_null_dict() -> None:
    header(5, "Null evidence dict — adversary omits all structured fields")
    print("v2 FAIL claims with evidence replaced by {} (want FAIL):")
    _row("'participant we observed' (was n=1 in dict)",
         "The intervention produced a striking improvement in the participant we observed.",
         {}, "FAIL")
    _row("'lone test animal'",
         "Our lone test animal showed remarkable rejuvenation afterward.", {}, "FAIL")
    _row("'single rodent ... 12 percent'",
         "The single rodent improved by about 12 percent following treatment.", {}, "FAIL")
    _row("'wrapped up the moment the trend turned favorable'",
         "We wrapped up data collection the moment the trend turned favorable.", {}, "FAIL")
    _row("'nothing to compare against'",
         "Participants were measured before and assessed again after; there was nothing to compare against.",
         {}, "FAIL")


def method_6_pass_stripping() -> None:
    header(6, "PASS-case stripping — progressively remove positive markers")
    claim = ("A randomized double-blind placebo-controlled trial found reduced "
             "mortality, independently replicated.")
    print("Strong claim, fields stripped one at a time (want PASS until evidence is gone):")
    _row("full   n+design+journal+replicated",
         claim, {"n": 4200, "design": "RCT double-blind", "journal": "NEJM",
                 "replicated_by": ["A", "B"]}, "PASS")
    _row("-journal",
         claim, {"n": 4200, "design": "RCT double-blind", "replicated_by": ["A", "B"]}, "PASS")
    _row("-replication",
         claim, {"n": 4200, "design": "RCT double-blind"}, "PASS")
    _row("-design key (text still says RCT)",
         claim, {"n": 4200}, "PASS")
    _row("empty dict (text still says RCT double-blind)",
         claim, {}, "PASS")


def method_7_paraphrase_battery() -> None:
    header(7, "Paraphrase battery — 10 phrasings of one weakness (single-subject)")
    print("All want FAIL; report how many of 10 hold.")
    paraphrases = [
        ("one mouse", "A single mouse improved after one dose.", {"design": "observed"}),
        ("a single rodent", "A single rodent improved after treatment.", {"design": "observed"}),
        ("the lone test animal", "The lone test animal recovered fully.", {"design": "observed"}),
        ("the sole subject", "The sole subject showed reversal.", {"design": "observed"}),
        ("our only participant", "Our only participant felt years younger.", {"design": "observed"}),
        ("just one volunteer", "Just one volunteer received it and thrived.", {"design": "observed"}),
        ("a solitary patient", "A solitary patient responded dramatically.", {"design": "observed"}),
        ("the individual we dosed", "The single individual we dosed bounced back.", {"design": "observed"}),
        ("one specimen", "One specimen exhibited total recovery.", {"design": "observed"}),
        ("the one gentleman", "The one gentleman we enrolled recovered completely.", {"design": "observed"}),
    ]
    held = sum(_row(lbl, c, e, "FAIL") for lbl, c, e in paraphrases)
    print(f"\n  held: {held}/10  (document which miss and why — that is the honest ceiling)")


def method_8_compound_vs_single() -> None:
    header(8, "Compound vs single weakness — does stacking raise DAS?")
    print("Same claim, weaknesses added cumulatively (DAS should climb):")
    claim = "The treatment produced a large improvement."
    _row("n=1 only", claim, {"n": 1})
    _row("n=1 + no control", claim, {"n": 1, "design": "no comparison arm"})
    _row("n=1 + no control + weak source", claim,
         {"n": 1, "design": "no comparison arm", "source": "blog post"})
    _row("n=1 + no control + weak source + subjective", claim,
         {"n": 1, "design": "no comparison arm", "source": "blog post",
          "outcome": "how he felt"})


def method_9_threshold_sensitivity() -> None:
    header(9, "Threshold sensitivity — cases near the 0.80 boundary")
    print(f"Threshold = {TAU_GATE_DAS}. Listing borderline DAS (0.74-0.86):")
    cases = [
        ("group testimonial", "Everyone in our small group felt better.",
         {"group_size": 6, "outcome": "subjective"}),
        ("14-pt open-label pilot, tentative",
         "A 14-patient open-label pilot is encouraging; no clinical conclusions yet.",
         {"n": 14, "design": "open-label pilot"}),
        ("modest preregistered n=38",
         "A preregistered randomized blinded trial of 38 found a modest improvement.",
         {"n": 38, "design": "preregistered randomized blinded"}),
        ("observational + causal, large n",
         "Coffee drinkers lived longer, so coffee extends lifespan.",
         {"design": "cross-sectional survey", "n": 80000}),
        ("surrogate endpoint RCT",
         "The therapy cut a biomarker 22%, so it will cut mortality.",
         {"design": "RCT", "n": 320, "clinical_endpoint": "not measured"}),
    ]
    for lbl, c, e in cases:
        v, d = _das(c, e)
        near = "  <-- in 0.74-0.86 band" if 0.74 <= d <= 0.86 else ""
        print(f"  {v:<4} {d:5.3f}{near:<26} {lbl}")


def main() -> None:
    method_1_vocab_substitution()
    method_2_dict_vs_freetext()
    method_3_cross_domain()
    method_4_minimal_perturbation()
    method_5_null_dict()
    method_6_pass_stripping()
    method_7_paraphrase_battery()
    method_8_compound_vs_single()
    method_9_threshold_sensitivity()
    print(f"\n{'='*78}\nThis battery reports raw behaviour. Misses are findings, not failures.\n{'='*78}")


if __name__ == "__main__":
    main()
