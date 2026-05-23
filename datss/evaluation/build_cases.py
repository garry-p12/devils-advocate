"""
Documentation of how test_cases.csv was constructed.

We did NOT scrape or generate these from any model. Each row was authored
manually with the following recipe:

PASS cases (10):
  - Anchor on a real, well-known longevity-research finding (Harrison 2009
    rapamycin, PREDIMED, statin meta-analyses, etc.). Strip detail down to the
    cited evidence and a defensible, narrow claim.
  - Include positive evidence markers the challengers can detect: "randomized
    controlled", "meta-analysis", "peer-reviewed", "replicated", "nih funded".
  - Keep the scope tight — "in mice over 18 months" rather than "reverses
    aging in humans".

FAIL cases (10):
  - Take one or more failure modes and stack them: tiny n, no controls, no
    IRB, blog-post sourcing, manufacturer COI, retracted source, hype
    language ("magic bullet", "paradigm shift"), claim/data mismatch.
  - Cover all 8 BiasClass dimensions across the FAIL pool:
        EVIDENCE_QUALITY       — cases 11, 14, 18 (uncontrolled, anecdotal)
        METHODOLOGY            — cases 14, 18, 19 (no control, retrospective,
                                  post-hoc, cherry-picked)
        ALTERNATIVE_HYPOTHESIS — cases 19, 22-style (correlation/confounder)
        SCOPE_GENERALIZABILITY — cases 12, 17 (tiny pop, single clinic)
        PROVENANCE_COI         — cases 11, 12, 13, 15, 16, 17, 18, 19
        INTERNAL_CONSISTENCY   — case 20 (data-claim mismatch flagged)
        PRIOR_ART_CONFLICT     — cases 13, 16, 20 (contradicts prior, unprec.)
        SAFETY_ETHICS          — cases 11, 12, 13, 15, 16, 17, 20 (no IRB,
                                  serious adverse, self-experiment, DIY)

BORDERLINE cases (5):
  - Real published work where reasonable people would disagree on whether
    the claim is defensible: tiny-n peer-reviewed pilots, observational
    cohorts with confounders, meta-analyses of low-quality studies.
  - The gate decision on these depends on the chosen threshold; they are
    the cases that exercise the tuning sweep.

No two cases are paraphrases of each other. The split in evaluate.py is
stratified by label with random_state=42 so the same train/val/test
partition is used for every run.
"""

if __name__ == "__main__":
    print(__doc__)
