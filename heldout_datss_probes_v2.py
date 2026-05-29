"""
Round-2 follow-up probes: novel paraphrases (reviewer-authored).

Place at repo root next to the `datss/` package and run:

    python heldout_datss_probes_v2.py

These probes test whether the structural read in `pool/structural.py`
generalises across phrasing variation, OR whether it leans on the specific
substrings present in the existing token lists.

Each weak claim below is genuinely weak (n=1, stopped-early, no-control,
testimonial, weak-source) but phrased so that the surface tokens differ
from the ones in `_SINGLE_SUBJECT_TOKENS`, `_STOPPED_EARLY_TOKENS`,
`_NO_CONTROL_TOKENS`, `_WEAK_SOURCE_TOKENS`, etc. Where the weakness is
encoded structurally (e.g. n in the evidence dict), the gate should still
catch it. Where the weakness lives only in the free-text phrasing, the
question is whether the structural read generalises or whether a different
paraphrase walks through.
"""
from datss.models import ChallengeInput
from datss.gate import run_challenge

PROBES = [
    # n=1 in the evidence dict, but the text does NOT use any single-subject token.
    ("The intervention produced a striking improvement in the participant we observed.",
     {"n": 1},
     "FAIL", "n=1 in dict; text avoids 'single/one/lone' tokens"),

    # Single subject phrased as 'lone test animal'; n NOT in dict.
    ("Our lone test animal showed remarkable rejuvenation afterward.",
     {"design": "observed the animal after dosing"},
     "FAIL", "'lone test animal' not in single-subject tokens; no n field"),

    # n=1 with a MODEST effect size (12%, outside the 40-90% bucket).
    ("The single rodent improved by about 12 percent following treatment.",
     {"n": 1},
     "FAIL", "12% dodges large-effect tokens; n=1 should still carry it"),

    # Stopped-early, novel paraphrase outside the stopped-early token list.
    ("We wrapped up data collection the moment the trend turned favorable.",
     {"n": 20},
     "FAIL", "'wrapped up...moment trend turned favorable' is optional stopping"),

    # No control arm, novel phrasing.
    ("Participants were measured before and assessed again after; there was nothing to compare against.",
     {"n": 30},
     "FAIL", "'nothing to compare against' is a no-control phrasing"),

    # Weak source, novel.
    ("According to a thread on a longevity forum, the protocol delivered dramatic gains.",
     {"source": "online forum thread"},
     "FAIL", "'forum thread' is a weak source; not in weak-source tokens"),

    # Testimonial dodging 'felt' / 'founder' / 'tried'.
    ("A colleague swears the compound restored his vigor almost immediately.",
     {"source": "word of mouth"},
     "FAIL", "'swears...restored vigor' is testimonial; dodges subjective tokens"),

    # Strong claim phrased plainly, without the canonical strong-source vocabulary.
    ("A large multi-site controlled experiment with thousands of randomly assigned participants, "
     "independently reproduced by other laboratories, found a reliable reduction in the endpoint.",
     {"n": 6000, "design": "randomly assigned, controlled, multi-site", "reproduced": True},
     "PASS", "strong but avoids 'RCT'/'NEJM'/'peer-reviewed' exact tokens"),
]


def main():
    print(f"{'expected':<9} {'verdict':<7} {'das':<7} note")
    print("-" * 100)
    correct = 0
    for claim, ev, expected, note in PROBES:
        r = run_challenge(ChallengeInput(claim=claim, evidence=ev, component_id="probe"),
                          use_cache=False)
        ok = (r.decision.value == expected)
        correct += ok
        flag = "OK " if ok else "MISS"
        print(f"{expected:<9} {r.decision.value:<7} {r.das:<7.3f} [{flag}] {note}")
    print(f"\nNovel-paraphrase accuracy: {correct}/{len(PROBES)}")


if __name__ == "__main__":
    main()
