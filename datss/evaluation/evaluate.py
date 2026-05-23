"""
Threshold tuning + evaluation.

Pipeline:
  1. Load test_cases.csv.
  2. Stratified 70/10/20 split by label, random_state=42.
  3. Sweep das_threshold over [0.80 ... 0.94] step 0.02 on val only,
     pick value maximising F1 (FAIL = positive class) subject to FP <= 10%.
  4. Apply selected threshold to test set exactly once.
  5. Bootstrap 95% CIs over the test set, seed=42.
  6. Report latency stats from 1000 calls on test cases.

Run: python -m datss.evaluation.evaluate
"""

from __future__ import annotations

import json
import os
import random
import time
from statistics import quantiles
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from datss import ChallengeInput, GateDecision, clear_default_cache, run_challenge
from datss.thresholds import TAU_GATE_LATENCY_P99_MS

CSV_PATH = os.path.join(os.path.dirname(__file__), "test_cases.csv")
REPORT_PATH = os.path.join(os.path.dirname(__file__), "report.json")

THRESHOLD_SWEEP = [0.80, 0.82, 0.84, 0.86, 0.88, 0.90, 0.92, 0.94]
RANDOM_STATE = 42
BOOTSTRAP_ITERS = 1000
LATENCY_CALLS = 1000


def _load() -> pd.DataFrame:
    df = pd.read_csv(CSV_PATH)
    df["evidence"] = df["evidence_json"].apply(json.loads)
    return df


def _split(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Manual stratified 70/10/20 split that guarantees each fold contains at
    least one row per label (sklearn.train_test_split chokes on three-class
    stratification when the val fold rounds to 2 rows).

    Targets per class: train = round(0.70*n), val = max(1, round(0.10*n)),
    test = remaining. Within each class we sort by id then shuffle with
    random_state=RANDOM_STATE so the split is fully reproducible.
    """
    rng = random.Random(RANDOM_STATE)
    train_rows: List[Any] = []
    val_rows: List[Any] = []
    test_rows: List[Any] = []
    for label in sorted(df["label"].unique()):
        rows = df[df["label"] == label].sort_values("id").to_dict(orient="records")
        rng.shuffle(rows)
        n = len(rows)
        n_train = round(0.70 * n)
        n_val = max(1, round(0.10 * n))
        # Ensure we leave at least one for test.
        if n_train + n_val >= n:
            n_val = max(1, n - n_train - 1)
        n_test = n - n_train - n_val
        if n_test < 1:
            n_train -= 1
            n_test = 1
        train_rows.extend(rows[:n_train])
        val_rows.extend(rows[n_train : n_train + n_val])
        test_rows.extend(rows[n_train + n_val :])
    train = pd.DataFrame(train_rows)
    val = pd.DataFrame(val_rows)
    test = pd.DataFrame(test_rows)
    assert set(train["id"]).isdisjoint(set(val["id"]))
    assert set(train["id"]).isdisjoint(set(test["id"]))
    assert set(val["id"]).isdisjoint(set(test["id"]))
    return train.reset_index(drop=True), val.reset_index(drop=True), test.reset_index(drop=True)


def _decisions(df: pd.DataFrame, threshold: float) -> List[str]:
    decisions: List[str] = []
    for _, row in df.iterrows():
        r = run_challenge(
            ChallengeInput(
                claim=row["claim"],
                evidence=row["evidence"],
                component_id=row["component_id"],
            ),
            das_threshold=threshold,
            use_cache=False,
        )
        decisions.append(r.decision.value)
    return decisions


def _confusion(labels: List[str], decisions: List[str]) -> Dict[str, int]:
    # FAIL is positive class. BORDERLINE rows are excluded from metrics here —
    # they have no fixed ground truth and contaminate F1.
    tp = fp = tn = fn = 0
    for lbl, dec in zip(labels, decisions):
        if lbl == "FAIL":
            if dec == "FAIL":
                tp += 1
            else:
                fn += 1
        elif lbl == "PASS":
            if dec == "FAIL":
                fp += 1
            else:
                tn += 1
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn}


def _metrics(c: Dict[str, int]) -> Dict[str, float]:
    tp, fp, tn, fn = c["tp"], c["fp"], c["tn"], c["fn"]
    total = tp + fp + tn + fn
    acc = (tp + tn) / total if total else 0.0
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    fp_rate = fp / (fp + tn) if (fp + tn) else 0.0
    fn_rate = fn / (fn + tp) if (fn + tp) else 0.0
    return {
        "accuracy": acc,
        "precision": prec,
        "recall": rec,
        "f1": f1,
        "fp_rate": fp_rate,
        "fn_rate": fn_rate,
    }


def _tune(val: pd.DataFrame) -> Tuple[float, Dict[float, Dict[str, float]]]:
    sweep_results: Dict[float, Dict[str, float]] = {}
    best_thr = THRESHOLD_SWEEP[0]
    best_f1 = -1.0
    for thr in THRESHOLD_SWEEP:
        clear_default_cache()
        decisions = _decisions(val, thr)
        c = _confusion(list(val["label"]), decisions)
        m = _metrics(c)
        sweep_results[thr] = m
        # Subject to FP <= 10%.
        if m["fp_rate"] <= 0.10 and m["f1"] > best_f1:
            best_f1 = m["f1"]
            best_thr = thr
    return best_thr, sweep_results


def _latency_stats(test: pd.DataFrame, threshold: float) -> Dict[str, float]:
    clear_default_cache()
    rows = list(test.to_dict(orient="records"))
    if not rows:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0}
    times: List[float] = []
    for i in range(LATENCY_CALLS):
        row = rows[i % len(rows)]
        t0 = time.perf_counter()
        run_challenge(
            ChallengeInput(
                claim=row["claim"],
                evidence=row["evidence"],
                component_id=row["component_id"],
            ),
            das_threshold=threshold,
            use_cache=False,
        )
        times.append((time.perf_counter() - t0) * 1000.0)
    arr = np.array(times)
    return {
        "p50": float(np.percentile(arr, 50)),
        "p95": float(np.percentile(arr, 95)),
        "p99": float(np.percentile(arr, 99)),
    }


def _bootstrap_ci(
    labels: List[str], decisions: List[str], n_iter: int = BOOTSTRAP_ITERS
) -> Dict[str, Tuple[float, float]]:
    rng = random.Random(RANDOM_STATE)
    n = len(labels)
    recalls: List[float] = []
    fp_rates: List[float] = []
    for _ in range(n_iter):
        idx = [rng.randrange(n) for _ in range(n)]
        bl = [labels[i] for i in idx]
        bd = [decisions[i] for i in idx]
        c = _confusion(bl, bd)
        m = _metrics(c)
        recalls.append(m["recall"])
        fp_rates.append(m["fp_rate"])
    def _ci(xs: List[float]) -> Tuple[float, float]:
        arr = np.array(xs)
        return float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))
    return {"recall": _ci(recalls), "fp_rate": _ci(fp_rates)}


def main() -> None:
    df = _load()
    train, val, test = _split(df)

    total = len(df)
    n_pass = int((df["label"] == "PASS").sum())
    n_fail = int((df["label"] == "FAIL").sum())
    n_bord = int((df["label"] == "BORDERLINE").sum())

    chosen_thr, sweep_results = _tune(val)
    val_metrics = sweep_results[chosen_thr]

    clear_default_cache()
    test_decisions = _decisions(test, chosen_thr)
    test_labels = list(test["label"])
    test_confusion = _confusion(test_labels, test_decisions)
    test_metrics = _metrics(test_confusion)

    latency = _latency_stats(test, chosen_thr)
    ci = _bootstrap_ci(test_labels, test_decisions)

    print("==============================")
    print("  DATSS — EVALUATION REPORT")
    print("==============================")
    print(f"Corpus: {total} total ({n_pass} PASS, {n_fail} FAIL, {n_bord} BORDERLINE)")
    print(
        f"Splits: train={len(train)}, val={len(val)}, test={len(test)} "
        f"(stratified, seed={RANDOM_STATE}, zero leakage confirmed)"
    )
    print()
    print("Threshold tuning (val only):")
    print(f"  Swept: {THRESHOLD_SWEEP}")
    print(
        f"  Selected: tau_gate_das = {chosen_thr:.2f}  "
        f"(F1={val_metrics['f1']:.2f} on val, FP={val_metrics['fp_rate']*100:.2f}%)"
    )
    print()
    print("Test set results (touched once):")
    print(f"  Accuracy:  {test_metrics['accuracy']*100:.2f}%")
    print(f"  Precision: {test_metrics['precision']*100:.2f}%")
    print(f"  Recall:    {test_metrics['recall']*100:.2f}%")
    print(f"  F1:        {test_metrics['f1']*100:.2f}%")
    print(f"  FP rate:   {test_metrics['fp_rate']*100:.2f}%   [PASS cases incorrectly blocked]")
    print(f"  FN rate:   {test_metrics['fn_rate']*100:.2f}%   [FAIL cases incorrectly allowed]")
    print()
    print(f"Latency (ms) — {LATENCY_CALLS} calls on test cases:")
    print(f"  p50:  {latency['p50']:.2f}")
    print(f"  p95:  {latency['p95']:.2f}")
    print(f"  p99:  {latency['p99']:.2f}  [budget: TAU_GATE_LATENCY_P99_MS = {TAU_GATE_LATENCY_P99_MS}]")
    print()
    print(f"Bootstrap 95% CI ({BOOTSTRAP_ITERS} resamples, seed={RANDOM_STATE}):")
    print(f"  Recall:    [{ci['recall'][0]*100:.2f}%, {ci['recall'][1]*100:.2f}%]")
    print(f"  FP rate:   [{ci['fp_rate'][0]*100:.2f}%, {ci['fp_rate'][1]*100:.2f}%]")
    print("==============================")

    report: Dict[str, Any] = {
        "corpus": {"total": total, "pass": n_pass, "fail": n_fail, "borderline": n_bord},
        "splits": {"train": len(train), "val": len(val), "test": len(test), "seed": RANDOM_STATE},
        "sweep": {f"{k:.2f}": v for k, v in sweep_results.items()},
        "selected_threshold": chosen_thr,
        "val_metrics": val_metrics,
        "test_metrics": test_metrics,
        "test_confusion": test_confusion,
        "latency_ms": latency,
        "latency_budget_ms": TAU_GATE_LATENCY_P99_MS,
        "bootstrap_ci_95": {k: list(v) for k, v in ci.items()},
        "test_decisions": list(zip([int(x) for x in test["id"]], test_labels, test_decisions)),
    }
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nFull report saved to: {REPORT_PATH}")


if __name__ == "__main__":
    main()
