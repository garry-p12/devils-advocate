"""
Structural evidence scoring — the round-2 reviewer fix.

The original challenger implementation scored only keyword/substring
patterns in claim and evidence text. The reviewer correctly observed that
this matched a corpus authored with knowledge of those patterns and
collapsed on a held-out probe set (3/10) where weak claims were phrased
without trigger vocabulary.

This module scores evidentiary STRUCTURE instead. It looks at:
  * sample size (n)
  * presence and quality of a control / comparison arm
  * replication signal (independent replicators, multi-center, etc.)
  * design integrity (stopped early, no control, single-subject, observational)
  * source quality category (lab notebook, personal account, blog vs. journal)
  * statistics presence (or explicit absence)
  * effect-size implausibility against sample size

The signals here intentionally use *structural* descriptors — words about
the evidence's shape ("single", "one", "no comparison", "halted") rather
than domain vocabulary specific to longevity research ("rapamycin",
"manufacturer", "preregistered"). A new probe phrased in any domain that
matches the same evidentiary shape should produce the same structural
score.

This module returns a single dict of per-feature scores in [-1, +1], where
positive values raise adversarial pressure (the evidence is structurally
weak) and negative values lower it (the evidence is structurally strong).
Each challenger then combines a subset of these features with its own
keyword SIGNALS — the structural features are authoritative when they
fire.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional


# Tokens that describe evidentiary shape, not domain vocabulary.
_SINGLE_SUBJECT_TOKENS = (
    "single mouse", "one mouse", "one animal", "single animal",
    "one subject", "single subject", "one patient", "single patient",
    "single observation", "one observation", "single time",
    "one rat", "single rat",
    "personal account", "founder", "myself", "i tried", "we tried",
    "case report", "case study",
    "single individual", "one individual",
)

_NO_CONTROL_TOKENS = (
    "no comparison arm", "no comparison", "no control arm", "no control group",
    "no controls", "without a control", "without controls",
    "did not feel a comparison", "did not include a comparison",
    "uncontrolled",
    "before-and-after", "before and after",
    "open-label", "open label",
)

_STOPPED_EARLY_TOKENS = (
    "stopped early", "halted when", "ended the study early",
    "ended early", "terminated early", "halted because",
    "optional stopping", "stopped once results",
    "ended once the numbers", "halted when results",
    "promising results led us to stop",
)

_SUBJECTIVE_OUTCOME_TOKENS = (
    "subjective", "felt", "self-reported", "self reported",
    "reported feeling", "reported being",
    "how he felt", "how she felt", "how they felt",
    "investigator judgment", "investigator's judgment",
    "we are confident", "clearly works", "obvious effect",
    "anecdotal",
)

_WEAK_SOURCE_TOKENS = (
    "lab notebook", "internal notes", "personal account",
    "blog post", "blog", "press release",
    "podcast", "tv interview", "newsroom", "media kit",
    "marketing", "testimonial",
    "preprint" ,
)

_STRONG_SOURCE_TOKENS = (
    "nejm", "lancet", "nature", "science", "cell ", "jama ",
    "cochrane", "bmj", "annals of internal medicine",
    "peer-reviewed", "peer reviewed",
    "preregistered", "pre-registered",
)

_REPLICATION_TOKENS = (
    "replicated", "independently replicated", "replicated by",
    "multiple groups", "multi-center", "multicenter",
    "multiple cohorts", "three independent", "two independent",
    "meta-analysis", "meta analysis", "systematic review",
)

_RANDOMIZATION_TOKENS = (
    "randomized", "randomised", "rct ", "rcts",
    "double-blind", "double blind",
    "placebo-controlled", "placebo controlled",
    "intent-to-treat", "intent to treat",
    "preregistered", "pre-registered",
)

_LARGE_EFFECT_TOKENS = (
    "reverses", "cures", "reverses aging",
    "40%", "50%", "60%", "70%", "80%", "90%",
    "doubles", "tripled", "doubled",
    "years younger", "decades younger",
    "twenty years younger", "ten years younger",
)

_NO_STATISTICS_TOKENS = (
    "none computed", "no statistics", "did not compute",
    "no p-value", "no confidence interval",
    "no significance", "not significant analysis",
)

_IN_VITRO_SCOPE_TOKENS = (
    "dish", "in vitro", "cell line", "cells in a dish",
    "petri dish", "cells we ordered",
    "yeast", "c. elegans", "worms",
)


# --- Round-2 follow-up: detectors for blind spots surfaced by ---------
# extra_probes.py. Each detector targets a class of evidentiary weakness
# (correlation→causation, surrogate endpoint, population mismatch,
# endpoint switching, paid-speakers COI, sparse evidence). Tokens here
# describe the *act* or *shape* of the weakness, not domain content; they
# are designed to generalise to claims authored in different vocabulary.

_OBSERVATIONAL_DESIGN_TOKENS = (
    "observational", "cross-sectional", "cross sectional",
    "self-report consumption survey", "self-report survey",
    "consumption survey", "questionnaire-based",
    "prospective observational", "observational cohort",
    "cohort study", "registry-based", "retrospective cohort",
)

_CAUSAL_CLAIM_TOKENS = (
    "causes", "extends lifespan", "prevents", "prevent", "reverses aging",
    "we recommend", "leads to", "is responsible for",
    "shows X prevents", "shows that X causes",
    "shows that X prevents", "drives", "produces",
    "extends human lifespan", "extends life", "shortens",
    "is the cause of", "is to blame for",
)

_SURROGATE_OUTCOME_KEYS = (
    "clinical_endpoint", "primary_endpoint", "primary endpoint",
    "cognitive_testing", "cognitive testing",
    "hard_endpoint", "clinical outcome",
    "mortality_outcome", "outcome_measured",
)

_SURROGATE_OUTCOME_VALUES = (
    "not measured", "not performed", "not assessed", "not tested",
    "biomarker change", "biomarker", "surrogate",
    "intermediate measure", "proxy",
)

_POPULATION_MISMATCH_KEYS = (
    ("studied_population", "claimed_population"),
    ("studied_in", "claimed_for"),
    ("trial_population", "target_population"),
    ("enrolled", "claimed_for"),
)

_ENDPOINT_SWITCHING_TOKENS = (
    "added after unblinding", "after seeing the data",
    "after the unblinding", "preregistered primary did not",
    "preregistered primary endpoint did not",
    "primary endpoint did not move", "primary endpoint was negative",
    "updated analysis on a different outcome",
    "different endpoint than preregistered",
    "endpoint added after",
    "subgroup of patients with the highest",
    "post-hoc subgroup",
    "subgroup analysis after",
    "the subgroup of",
)

_PAID_COI_TOKENS = (
    "paid consultants", "paid consultancies",
    "consulting fees undisclosed", "paid speakers",
    "speaker fees", "paid by the manufacturer",
    "honoraria undisclosed", "honoraria from the manufacturer",
    "undisclosed disclosures", "disclosures: undisclosed",
    "paid consultants to the drug", "paid consultants to the",
    "consultancies undisclosed",
    "also founded the company", "also founder", "patent holder",
    "patent royalties", "stock in the company",
)

_PSEUDO_REPLICATION_TOKENS = (
    "same lab", "same team", "originating lab",
    "originating investigators", "collaborator on the original",
    "consulted on the original protocol",
    "co-author on the original",
    "in our lab", "by our team",
)


def _evidence_has_observational_design(evidence: Dict[str, Any]) -> bool:
    """Check evidence dict design field or values for observational markers."""
    if not isinstance(evidence, dict):
        return False
    for key in ("design", "study_design", "method"):
        v = evidence.get(key)
        if isinstance(v, str) and any(t in v.lower() for t in _OBSERVATIONAL_DESIGN_TOKENS):
            return True
    return False


def _evidence_has_surrogate_marker(evidence: Dict[str, Any]) -> bool:
    """
    Detect explicit surrogate-endpoint markers in the evidence dict.
    Two paths:
      1. A surrogate-outcome key (e.g. clinical_endpoint) has a value that
         contains 'not measured' / 'not performed' / 'biomarker' / 'surrogate'.
      2. The primary_endpoint value explicitly names a biomarker term.
    """
    if not isinstance(evidence, dict):
        return False
    for key in _SURROGATE_OUTCOME_KEYS:
        v = evidence.get(key)
        if isinstance(v, str) and any(t in v.lower() for t in _SURROGATE_OUTCOME_VALUES):
            return True
        if isinstance(v, bool) and v is False:
            # e.g. cognitive_testing: False
            return True
    return False


def _evidence_has_population_mismatch(evidence: Dict[str, Any]) -> bool:
    """
    Detect explicit studied-vs-claimed population mismatch.
    Only fires when BOTH halves of a key pair are present AND differ.
    """
    if not isinstance(evidence, dict):
        return False
    for studied_key, claimed_key in _POPULATION_MISMATCH_KEYS:
        s = evidence.get(studied_key)
        c = evidence.get(claimed_key)
        if isinstance(s, str) and isinstance(c, str):
            s_norm = s.strip().lower()
            c_norm = c.strip().lower()
            if s_norm and c_norm and s_norm != c_norm:
                return True
    return False


def _evidence_is_sparse(evidence: Dict[str, Any], n: Optional[int]) -> bool:
    """
    Detect evidence dicts that carry essentially no evidentiary structure:
    no n, no design field, no source field, and fewer than 3 keys.
    Catches 'trust me' / 'investigator certainty' submissions.
    """
    if not isinstance(evidence, dict):
        return True
    substantive_keys = [k for k, v in evidence.items() if v not in (None, "", [], {})]
    has_design = any(k in evidence for k in ("design", "study_design", "method"))
    has_source = any(k in evidence for k in ("source", "journal", "publication"))
    return (n is None) and (not has_design) and (not has_source) and len(substantive_keys) <= 2


def _has_any(text: str, tokens) -> bool:
    return any(t in text for t in tokens)


def _flatten(claim: str, evidence: Dict[str, Any]) -> str:
    """Concatenate every textual field for substring search."""
    parts = [str(claim)]
    if isinstance(evidence, dict):
        for v in evidence.values():
            if isinstance(v, (list, tuple)):
                parts.extend(str(x) for x in v)
            else:
                parts.append(str(v))
    return " ".join(parts).lower()


def _coerce_n(evidence: Dict[str, Any]) -> Optional[int]:
    """Pull an integer sample size from evidence if present."""
    if not isinstance(evidence, dict):
        return None
    for key in ("n", "sample_size", "group_size", "participants", "runs", "subjects", "volunteers", "trials"):
        v = evidence.get(key)
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            return v
        if isinstance(v, float):
            return int(v)
        if isinstance(v, str):
            m = re.match(r"\s*(\d+)", v)
            if m:
                return int(m.group(1))
    return None


# Natural-language sample-size cues (principled extension to integer n).
# Each cue maps to a tiny-n bucket. Order matters — most specific first.
_NATURAL_N_CUES = [
    ("one friend", 1), ("a friend", 1), ("the friend", 1),
    ("one patient", 1), ("a patient", 1), ("the patient", 1),
    ("one volunteer", 1), ("the volunteer", 1),
    ("one subject", 1), ("the subject", 1),
    ("one founder", 1), ("the founder", 1), ("our founder", 1),
    ("the staff", 5),     # small group of staff
    ("our circle", 6),    # social circle, typically small
    ("our group", 6),
    ("ourselves", 3),     # "we gave it to ourselves"
    ("the three of us", 3), ("the two of us", 2),
    ("two dogs", 2), ("three dogs", 3),
    ("two cats", 2), ("three cats", 3),
    ("two mice", 2), ("three mice", 3),
    ("two rats", 2), ("three rats", 3),
    ("a few people", 5), ("a few patients", 5),
    ("several people", 8), ("several patients", 8),
    ("everyone in our", 8),
    ("our breeder kennel", 5),
]


_POST_HOC_TOKENS = (
    "the markers we were hoping for",
    "outcomes we were hoping for",
    "the markers we wanted",
    "excluded non-responders",
    "removed the patients who",
    "after we adjusted out",
    "once we removed",
    "subgroup that responded",
    "only the responders",
    "decided to wrap things up",
    "wrap things up and write",
    "decided to write it up",
    "without preregistration",
    "no preregistration",
)


_CLINICAL_IMPRESSION_TOKENS = (
    "the staff are sure",
    "staff are convinced",
    "clinical impression",
    "physicians are sure",
    "physicians believe",
    "we are sure it",
    "speaks for itself",
    "used at the clinic for",
    "in our clinic for years",
    "everyone here knows",
)


def _natural_n(text: str) -> Optional[int]:
    """Lowest-numbered match wins so 'two dogs in our group' returns 2 not 6."""
    found: list[int] = []
    for cue, n in _NATURAL_N_CUES:
        if cue in text:
            found.append(n)
    return min(found) if found else None


@dataclass
class StructuralFeatures:
    """Computed once per (claim, evidence) and reused across challengers."""
    n: Optional[int]
    text: str

    # Boolean shape predicates.
    is_single_subject: bool
    has_no_control: bool
    is_stopped_early: bool
    is_subjective_outcome: bool
    has_weak_source: bool
    has_strong_source: bool
    has_replication_language: bool
    replication_count: int
    has_randomization: bool
    claims_large_effect: bool
    claims_no_statistics: bool
    is_in_vitro_scope: bool

    # Round-2 follow-up: blind-spot detectors.
    is_causal_observational: bool      # causal claim + observational + not randomized
    has_surrogate_endpoint: bool       # evidence acknowledges clinical outcome not measured
    has_population_mismatch: bool      # studied_population != claimed_population in evidence
    is_endpoint_switching: bool        # post-hoc endpoint change patterns
    has_paid_coi: bool                 # paid-speakers / patent-holder / undisclosed disclosures
    is_pseudo_replication: bool        # "same lab", "collaborator on the original"
    is_sparse_evidence: bool           # no n, no design, no source, <=2 substantive keys

    # Derived structural risk scores in [-1, +1] (positive = adversarial).
    evidence_quality_delta: float
    methodology_delta: float
    internal_consistency_delta: float
    scope_delta: float
    provenance_delta: float
    alt_hypothesis_delta: float
    prior_art_delta: float
    safety_delta: float


def compute_features(claim: str, evidence: Dict[str, Any]) -> StructuralFeatures:
    text = _flatten(claim, evidence)
    n = _coerce_n(evidence)

    # If no explicit n in the evidence dict, fall back to natural-language
    # cues in claim+evidence text. This is the principled extension that
    # catches "two dogs", "the founder", "our group" without requiring the
    # author to put `{"n": 2}` in the evidence dict.
    if n is None:
        n = _natural_n(text)

    is_post_hoc = _has_any(text, _POST_HOC_TOKENS)
    is_clinical_impression = _has_any(text, _CLINICAL_IMPRESSION_TOKENS)
    is_endpoint_switching = _has_any(text, _ENDPOINT_SWITCHING_TOKENS)
    has_paid_coi = _has_any(text, _PAID_COI_TOKENS)
    is_pseudo_replication = _has_any(text, _PSEUDO_REPLICATION_TOKENS)
    has_surrogate_endpoint = _evidence_has_surrogate_marker(evidence)
    has_population_mismatch = _evidence_has_population_mismatch(evidence)

    # Boolean shape predicates.
    single_subject = (
        _has_any(text, _SINGLE_SUBJECT_TOKENS)
        or (n is not None and n <= 1)
    )
    no_control = _has_any(text, _NO_CONTROL_TOKENS)
    stopped_early = _has_any(text, _STOPPED_EARLY_TOKENS)
    subjective = _has_any(text, _SUBJECTIVE_OUTCOME_TOKENS)
    weak_source = _has_any(text, _WEAK_SOURCE_TOKENS)
    strong_source = _has_any(text, _STRONG_SOURCE_TOKENS)
    rep_lang = _has_any(text, _REPLICATION_TOKENS)
    rep_count = 0
    if isinstance(evidence, dict):
        rb = evidence.get("replicated_by")
        if isinstance(rb, (list, tuple)):
            rep_count = len(rb)
    randomized = _has_any(text, _RANDOMIZATION_TOKENS)
    large_effect = _has_any(text, _LARGE_EFFECT_TOKENS)
    no_stats = _has_any(text, _NO_STATISTICS_TOKENS) or (
        isinstance(evidence, dict)
        and isinstance(evidence.get("statistics"), str)
        and any(x in str(evidence["statistics"]).lower()
                for x in ("none", "not computed", "none computed"))
    )
    in_vitro = _has_any(text, _IN_VITRO_SCOPE_TOKENS)

    # Correlation→causation compound predicate: a causal claim made on
    # observational evidence with no randomization. Each piece is a
    # structural feature individually; the conjunction is what makes the
    # claim adversarially weak (the "X is associated with Y, therefore X
    # causes Y" fallacy).
    has_causal_language = _has_any(text, _CAUSAL_CLAIM_TOKENS)
    has_observational_design = (
        _evidence_has_observational_design(evidence)
        or _has_any(text, _OBSERVATIONAL_DESIGN_TOKENS)
    )
    is_causal_observational = (
        has_causal_language and has_observational_design and not randomized
    )

    # Sparse-evidence detector: "trust me" / "investigator certainty"
    # submissions where the evidence dict carries no n, no design, no
    # source, and almost no other content. Without this the BASE_SCORE
    # prior alone sits just below threshold.
    is_sparse_evidence = _evidence_is_sparse(evidence, n)

    # --- Per-class structural risk deltas --------------------------------
    # Each delta is bounded; the per-challenger combiner clips again.

    # Evidence-quality: sample size, replication, source quality, stats.
    eq = 0.0
    if n is not None:
        if n <= 1:
            eq += 0.55
        elif n < 5:
            eq += 0.40
        elif n < 15:
            eq += 0.20
        elif n < 30:
            eq += 0.05
        elif n >= 1000:
            eq -= 0.20
        elif n >= 200:
            eq -= 0.10
    else:
        eq += 0.10  # missing n is itself adversarial
    if single_subject:
        eq += 0.30
    if no_stats:
        eq += 0.25
    if weak_source:
        eq += 0.20
    if strong_source:
        eq -= 0.20
    if rep_count >= 2:
        eq -= 0.25
    elif rep_count == 1:
        eq -= 0.10
    elif rep_lang:
        eq -= 0.10
    if is_sparse_evidence:
        eq += 0.25  # round-2 follow-up: "trust me" has no evidence to evaluate
    if is_causal_observational:
        eq += 0.15  # observational + causal claim weakens the evidentiary basis
    if has_surrogate_endpoint:
        eq += 0.20  # claim about clinical outcome from a non-clinical measure
    if has_population_mismatch:
        eq += 0.10  # studied-vs-claimed mismatch weakens generalisability of evidence
    if is_endpoint_switching:
        eq += 0.20  # changed endpoint after seeing data weakens the evidence
    if has_paid_coi:
        eq += 0.15  # undisclosed paid relationships weaken the evidentiary chain
    if is_pseudo_replication:
        eq += 0.15  # non-independent confirmation isn't real replication

    # Methodology: control, randomization, stopping rule, design integrity.
    # tiny_n is the methodology angle on small samples: any study with n<5 has
    # essentially no statistical resolution regardless of design, and n<15
    # only resolves very large effects.
    tiny_n = n is not None and n < 5
    small_n = n is not None and n < 15
    mt = 0.0
    if no_control:
        mt += 0.40
    if stopped_early:
        mt += 0.35
    if single_subject:
        mt += 0.25
    if subjective:
        mt += 0.20
    if tiny_n:
        mt += 0.30
    elif small_n:
        mt += 0.15
    if randomized:
        mt -= 0.35
    if no_stats:
        mt += 0.15
    if is_post_hoc:
        mt += 0.30
    if is_clinical_impression:
        mt += 0.25
    if is_endpoint_switching:
        mt += 0.35
    if has_surrogate_endpoint:
        mt += 0.30
    if is_pseudo_replication:
        mt += 0.20
    if is_sparse_evidence:
        mt += 0.20
    if is_causal_observational:
        mt += 0.30  # the methodology angle on causal-from-observational
    if has_paid_coi:
        mt += 0.15  # paid relationships open the door to methodological choices that favour the sponsor

    # Internal consistency: large effect at small n, no stats supporting claim.
    ic = 0.0
    if large_effect and n is not None and n < 30:
        ic += 0.40
    if large_effect and single_subject:
        ic += 0.30
    if no_stats and large_effect:
        ic += 0.25
    if no_stats:
        ic += 0.10
    if rep_count >= 2:
        ic -= 0.15
    if has_surrogate_endpoint:
        ic += 0.25  # claim about clinical outcome from a non-clinical measure
    if is_endpoint_switching:
        ic += 0.25  # claim contradicts the preregistered primary outcome
    if has_population_mismatch:
        ic += 0.15  # claim outruns the studied population

    # Scope / generalizability: in vitro, single subject, single center,
    # population-mismatch overreach.
    sc = 0.0
    if in_vitro:
        sc += 0.30
    if single_subject:
        sc += 0.25
    if rep_count >= 2:
        sc -= 0.20
    if rep_lang and "multi-center" in text:
        sc -= 0.15
    if has_population_mismatch:
        sc += 0.40  # studied in X, claimed for different Y

    # Provenance: source category, replication, journal, paid COI.
    pv = 0.0
    if weak_source:
        pv += 0.30
    if strong_source:
        pv -= 0.25
    if rep_count >= 2:
        pv -= 0.15
    if is_clinical_impression:
        pv += 0.20
    if has_paid_coi:
        pv += 0.30
    if is_pseudo_replication:
        pv += 0.15  # non-independent confirmation is a provenance issue too

    # Alternative hypothesis: causal claims with no control, tiny sample, or
    # subjective outcome — the smaller the n and the more uncontrolled the
    # design, the more alternative explanations remain plausible.
    ah = 0.0
    if single_subject and large_effect:
        ah += 0.30
    if no_control and large_effect:
        ah += 0.25
    if subjective and large_effect:
        ah += 0.20
    if tiny_n and not randomized:
        ah += 0.20
    if subjective and not randomized:
        ah += 0.15
    if randomized and rep_count >= 1:
        ah -= 0.30
    if is_causal_observational:
        ah += 0.40  # causal claim from observational data without randomization
    if has_population_mismatch:
        ah += 0.15  # studied-vs-claimed mismatch opens alternative explanations

    # Prior art: no structural feature is decisive here; keep small.
    pa = 0.0
    if rep_count >= 2:
        pa -= 0.15
    if single_subject and large_effect:
        pa += 0.10

    # Safety/ethics: subjective + n=1 + no control suggests untested intervention.
    sf = 0.0
    if subjective and large_effect:
        sf += 0.15
    if single_subject:
        sf += 0.10

    return StructuralFeatures(
        n=n,
        text=text,
        is_single_subject=single_subject,
        has_no_control=no_control,
        is_stopped_early=stopped_early,
        is_subjective_outcome=subjective,
        has_weak_source=weak_source,
        has_strong_source=strong_source,
        has_replication_language=rep_lang,
        replication_count=rep_count,
        has_randomization=randomized,
        claims_large_effect=large_effect,
        claims_no_statistics=no_stats,
        is_in_vitro_scope=in_vitro,
        is_causal_observational=is_causal_observational,
        has_surrogate_endpoint=has_surrogate_endpoint,
        has_population_mismatch=has_population_mismatch,
        is_endpoint_switching=is_endpoint_switching,
        has_paid_coi=has_paid_coi,
        is_pseudo_replication=is_pseudo_replication,
        is_sparse_evidence=is_sparse_evidence,
        evidence_quality_delta=eq,
        methodology_delta=mt,
        internal_consistency_delta=ic,
        scope_delta=sc,
        provenance_delta=pv,
        alt_hypothesis_delta=ah,
        prior_art_delta=pa,
        safety_delta=sf,
    )
