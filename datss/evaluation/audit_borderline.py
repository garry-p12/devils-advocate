"""
BORDERLINE-case distribution audit.

The BORDERLINE label is supposed to identify cases whose gate decision
genuinely depends on threshold placement — i.e. cases whose DAS sits in a
band tight around the operating point. If a BORDERLINE case scores far below
the threshold, it is functionally a soft PASS and the label is not doing
work; symmetrically for far above.

This audit runs the gate over BORDERLINE-only cases and reports the DAS
distribution against the threshold tight-band [0.75, 0.85]. Any case
outside that band on the current corpus is flagged for re-classification
or strengthening.

Run: python -m datss.evaluation.audit_borderline
"""

from __future__ import annotations

import json
import os
import statistics
from typing import Dict, List

import pandas as pd

from datss import ChallengeInput, clear_default_cache, run_challenge
from datss.thresholds import TAU_GATE_DAS

CSV_PATH = os.path.join(os.path.dirname(__file__), "test_cases.csv")
AUDIT_PATH = os.path.join(os.path.dirname(__file__), "borderline_audit.json")

TIGHT_LO = 0.75
TIGHT_HI = 0.85


def main() -> None:
    df = pd.read_csv(CSV_PATH)
    df["evidence"] = df["evidence_json"].apply(json.loads)
    df_b = df[df["label"] == "BORDERLINE"].sort_values("id").reset_index(drop=True)
    clear_default_cache()

    rows: List[Dict] = []
    for _, r in df_b.iterrows():
        res = run_challenge(
            ChallengeInput(claim=r["claim"], evidence=r["evidence"], component_id=r["component_id"]),
            use_cache=False,
        )
        in_band = TIGHT_LO <= res.das <= TIGHT_HI
        band = "tight" if in_band else ("low" if res.das < TIGHT_LO else "high")
        rows.append({
            "id": int(r["id"]),
            "das": round(res.das, 3),
            "decision": res.decision.value,
            "band": band,
        })

    vs = [row["das"] for row in rows]
    summary = {
        "tight_band": [TIGHT_LO, TIGHT_HI],
        "tau_gate_das": TAU_GATE_DAS,
        "n": len(rows),
        "in_band": sum(1 for v in vs if TIGHT_LO <= v <= TIGHT_HI),
        "below": sum(1 for v in vs if v < TIGHT_LO),
        "above": sum(1 for v in vs if v > TIGHT_HI),
        "mean": round(statistics.mean(vs), 3),
        "median": round(statistics.median(vs), 3),
        "min": min(vs),
        "max": max(vs),
    }

    print("================================================================")
    print("  DATSS — BORDERLINE DISTRIBUTION AUDIT")
    print("================================================================")
    print(
        f"Corpus: {summary['n']} BORDERLINE cases. "
        f"Tight band: [{TIGHT_LO}, {TIGHT_HI}]. "
        f"tau_gate_das={TAU_GATE_DAS}"
    )
    print()
    print(f"{'id':>3} {'das':>6} {'decision':>9}  band")
    print("-" * 40)
    for r in rows:
        print(f"{r['id']:>3} {r['das']:>6.3f} {r['decision']:>9}  [{r['band']}]")
    print()
    print(
        f"in {TIGHT_LO}-{TIGHT_HI} band: {summary['in_band']}/{summary['n']}   "
        f"below: {summary['below']}/{summary['n']}   "
        f"above: {summary['above']}/{summary['n']}"
    )
    print(f"mean={summary['mean']}  median={summary['median']}  range=[{summary['min']:.3f}, {summary['max']:.3f}]")

    if summary["in_band"] < summary["n"] // 2:
        outside = [r["id"] for r in rows if r["band"] != "tight"]
        print()
        print(
            f"⚠  fewer than half of BORDERLINE cases sit in the tight band. "
            f"Cases functionally not borderline: {outside}"
        )
        print(
            "  Either re-label these (likely soft PASS), strengthen the "
            "claim/evidence so they exhibit real ambiguity, or accept that "
            "the BORDERLINE label on this corpus is partly aspirational."
        )

    with open(AUDIT_PATH, "w") as f:
        json.dump({"summary": summary, "rows": rows}, f, indent=2)
    print()
    print(f"Audit saved to: {AUDIT_PATH}")


if __name__ == "__main__":
    main()
