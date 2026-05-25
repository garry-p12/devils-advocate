"""
Run the gate over adversarial_cases.csv — the round-2-reviewer-style corpus
authored adversary-first (plain-English phrasings, no reliance on the
challenger SIGNALS vocabulary).

This is a held-out evaluation distinct from test_cases.csv. The tuned
threshold from report.json (selected on the original corpus) is used as-is;
we do not re-tune on this corpus, because retuning on the adversarial set
would defeat its purpose.

Usage: python -m datss.evaluation.run_adversarial
"""

from __future__ import annotations

import json
import os
from collections import Counter
from typing import Dict, Optional

import pandas as pd

from datss import ChallengeInput, clear_default_cache, run_challenge
from datss.thresholds import TAU_GATE_DAS

CSV_PATH = os.path.join(os.path.dirname(__file__), "adversarial_cases.csv")
REPORT_PATH = os.path.join(os.path.dirname(__file__), "report.json")
OUT_PATH = os.path.join(os.path.dirname(__file__), "adversarial_report.json")


def _tuned_threshold() -> Optional[float]:
    if not os.path.exists(REPORT_PATH):
        return None
    try:
        with open(REPORT_PATH) as f:
            return float(json.load(f)["selected_threshold"])
    except (KeyError, ValueError, OSError):
        return None


def main() -> None:
    df = pd.read_csv(CSV_PATH)
    clear_default_cache()

    tuned = _tuned_threshold()
    threshold = tuned if tuned is not None else TAU_GATE_DAS
    src = "tuned (report.json)" if tuned is not None else "TAU_GATE_DAS default"
    print(f"Adversarial-first corpus: {len(df)} cases. Threshold = {threshold:.2f} [{src}]")
    print(f"{'ID':<4} | {'Label':<10} | {'Decision':<8} | {'DAS':<5} | flag")
    print("-" * 60)

    decisive = pass_correct = fail_correct = 0
    by_label = Counter()
    rows = []
    for _, row in df.iterrows():
        evidence: Dict = json.loads(row["evidence_json"])
        result = run_challenge(
            ChallengeInput(
                claim=row["claim"], evidence=evidence,
                component_id=row["component_id"],
            ),
            das_threshold=threshold, use_cache=False,
        )
        expected = row["label"]
        decision = result.decision.value
        flag = "—"
        if expected in ("PASS", "FAIL"):
            decisive += 1
            if expected == decision:
                flag = "OK"
                if expected == "PASS":
                    pass_correct += 1
                else:
                    fail_correct += 1
            else:
                flag = "MISS"
        by_label[expected] += 1
        rows.append({
            "id": row["id"], "label": expected, "decision": decision,
            "das": round(result.das, 3), "flag": flag,
        })
        print(f"{row['id']:<4} | {expected:<10} | {decision:<8} | {result.das:.2f}  | {flag}")

    n_pass = by_label["PASS"]
    n_fail = by_label["FAIL"]
    n_bord = by_label["BORDERLINE"]
    acc = (pass_correct + fail_correct) / decisive if decisive else 0.0
    print()
    print("Summary")
    print("-------")
    print(f"  PASS       : {pass_correct}/{n_pass} correct")
    print(f"  FAIL       : {fail_correct}/{n_fail} correct")
    print(f"  BORDERLINE : {n_bord} cases (no fixed ground truth)")
    print(f"  Accuracy (PASS+FAIL only): {acc*100:.2f}%")

    summary = {
        "threshold": threshold,
        "n_pass": n_pass, "n_fail": n_fail, "n_borderline": n_bord,
        "pass_correct": pass_correct, "fail_correct": fail_correct,
        "accuracy_decisive": acc,
    }
    with open(OUT_PATH, "w") as f:
        json.dump({"summary": summary, "rows": rows}, f, indent=2)
    print(f"\nSaved to: {OUT_PATH}")


if __name__ == "__main__":
    main()
