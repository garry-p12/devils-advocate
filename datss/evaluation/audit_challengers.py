"""
Per-challenger discrimination audit.

For each registered BiasClass, runs the corresponding challenger directly on
every case in test_cases.csv and reports:
  - mean score on PASS cases
  - mean score on FAIL cases
  - gap (mean_FAIL - mean_PASS)

A small gap means the challenger is contributing near-constant scores
regardless of claim quality — i.e. it is not actually exerting adversarial
pressure on the gate. We flag any challenger with gap < 0.10 as a weak
signal so the README §7 can be honest about it.

Run: python -m datss.evaluation.audit_challengers
"""

from __future__ import annotations

import json
import os
from typing import Dict, List

import numpy as np
import pandas as pd

from datss.models import BiasClass
from datss.pool.challenger import CHALLENGER_REGISTRY
from datss.pool.seeder import SeedAllocator

CSV_PATH = os.path.join(os.path.dirname(__file__), "test_cases.csv")
AUDIT_PATH = os.path.join(os.path.dirname(__file__), "challenger_audit.json")
WEAK_SIGNAL_GAP = 0.10


def _score_one(challenger_cls, claim: str, evidence: dict, seed: int) -> float:
    return challenger_cls().challenge(claim, evidence, seed, 0).score


def main() -> None:
    df = pd.read_csv(CSV_PATH)
    df["evidence"] = df["evidence_json"].apply(json.loads)

    # Use the same seed-derivation as the gate so the audit reflects real
    # operating conditions, not a one-off shuffle.
    seeds, _ = SeedAllocator().allocate(master_seed=42, n=len(BiasClass))
    seed_for: Dict[BiasClass, int] = {
        bc: seeds[i] for i, bc in enumerate(CHALLENGER_REGISTRY.keys())
    }

    rows = []
    for bias_class, cls in CHALLENGER_REGISTRY.items():
        pass_scores: List[float] = []
        fail_scores: List[float] = []
        border_scores: List[float] = []
        for _, r in df.iterrows():
            s = _score_one(cls, r["claim"], r["evidence"], seed_for[bias_class])
            if r["label"] == "PASS":
                pass_scores.append(s)
            elif r["label"] == "FAIL":
                fail_scores.append(s)
            else:
                border_scores.append(s)
        mean_pass = float(np.mean(pass_scores)) if pass_scores else float("nan")
        mean_fail = float(np.mean(fail_scores)) if fail_scores else float("nan")
        mean_bord = float(np.mean(border_scores)) if border_scores else float("nan")
        std_pass = float(np.std(pass_scores)) if pass_scores else float("nan")
        std_fail = float(np.std(fail_scores)) if fail_scores else float("nan")
        gap = mean_fail - mean_pass
        weak = gap < WEAK_SIGNAL_GAP
        rows.append({
            "bias_class": bias_class.value,
            "mean_pass": mean_pass,
            "std_pass": std_pass,
            "mean_fail": mean_fail,
            "std_fail": std_fail,
            "mean_borderline": mean_bord,
            "gap": gap,
            "weak_signal": weak,
        })

    print("================================================================")
    print("  DATSS — PER-CHALLENGER DISCRIMINATION AUDIT")
    print("================================================================")
    print(f"Corpus: {len(df)} cases. Weak-signal flag: gap < {WEAK_SIGNAL_GAP}")
    print()
    print(f"{'bias_class':<25} {'PASS':>10} {'FAIL':>10} {'BORD':>10} {'gap':>8} flag")
    print("-" * 78)
    weak_classes = []
    for r in rows:
        flag = "WEAK" if r["weak_signal"] else "ok"
        if r["weak_signal"]:
            weak_classes.append(r["bias_class"])
        print(
            f"{r['bias_class']:<25} "
            f"{r['mean_pass']:>10.3f} "
            f"{r['mean_fail']:>10.3f} "
            f"{r['mean_borderline']:>10.3f} "
            f"{r['gap']:>+8.3f} {flag}"
        )
    print()
    if weak_classes:
        print(f"Weak-signal challengers (gap < {WEAK_SIGNAL_GAP}): {weak_classes}")
        print("  → These contribute little adversarial pressure; document in README §7.")
    else:
        print(f"All 8 challengers discriminate above the {WEAK_SIGNAL_GAP} gap threshold.")
    print("================================================================")

    with open(AUDIT_PATH, "w") as f:
        json.dump({"weak_signal_gap_threshold": WEAK_SIGNAL_GAP, "rows": rows}, f, indent=2)
    print(f"Audit saved to: {AUDIT_PATH}")


if __name__ == "__main__":
    main()
