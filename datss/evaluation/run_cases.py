"""
Run all cases in test_cases.csv through the gate and print a per-case table
plus an accuracy summary.

Usage: python -m datss.evaluation.run_cases
"""

from __future__ import annotations

import json
import os
from collections import Counter
from typing import Dict, Optional

import pandas as pd

from datss import ChallengeInput, GateDecision, clear_default_cache, run_challenge
from datss.thresholds import TAU_GATE_DAS

CSV_PATH = os.path.join(os.path.dirname(__file__), "test_cases.csv")
REPORT_PATH = os.path.join(os.path.dirname(__file__), "report.json")


def _tuned_threshold() -> Optional[float]:
    """Read the tuned threshold from a prior evaluate.py run, if present."""
    if not os.path.exists(REPORT_PATH):
        return None
    try:
        with open(REPORT_PATH) as f:
            return float(json.load(f)["selected_threshold"])
    except (KeyError, ValueError, OSError):
        return None


def _expected_decision(label: str) -> str:
    return "FAIL" if label.upper() == "FAIL" else "PASS"


def main() -> None:
    df = pd.read_csv(CSV_PATH)
    clear_default_cache()

    tuned = _tuned_threshold()
    threshold = tuned if tuned is not None else TAU_GATE_DAS
    src = "tuned (report.json)" if tuned is not None else "TAU_GATE_DAS default"
    print(f"Using das_threshold = {threshold:.2f}  [{src}]")
    print(f"{'ID':<3} | {'Label':<10} | {'Decision':<8} | {'DAS':<5} | "
          f"{'Cov':<4} | {'Seeds':<6} | Reason")
    print("-" * 90)

    correct = 0
    by_label = Counter()
    correct_by_label = Counter()

    for _, row in df.iterrows():
        evidence: Dict = json.loads(row["evidence_json"])
        result = run_challenge(
            ChallengeInput(
                claim=row["claim"],
                evidence=evidence,
                component_id=row["component_id"],
            ),
            das_threshold=threshold,
            use_cache=False,
        )
        seeds_ok = "OK" if len(set(result.challenger_seeds)) == len(result.challenger_seeds) else "DUP"
        print(
            f"{int(row['id']):<3} | {row['label']:<10} | "
            f"{result.decision.value:<8} | {result.das:.2f}  | "
            f"{result.coverage:.2f} | {seeds_ok:<6} | {result.reason}"
        )
        by_label[row["label"]] += 1
        if row["label"] in ("PASS", "FAIL") and result.decision.value == _expected_decision(row["label"]):
            correct += 1
            correct_by_label[row["label"]] += 1

    decisive_total = by_label["PASS"] + by_label["FAIL"]
    acc = correct / decisive_total if decisive_total else 0.0
    print("\nSummary")
    print("-------")
    for lbl, n in by_label.items():
        if lbl in ("PASS", "FAIL"):
            print(f"  {lbl:<10}: {correct_by_label[lbl]}/{n} correct")
        else:
            print(f"  {lbl:<10}: {n} cases (no fixed ground truth)")
    print(f"  Accuracy (PASS+FAIL only): {acc*100:.2f}%")


if __name__ == "__main__":
    main()
