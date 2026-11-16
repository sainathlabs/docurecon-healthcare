
"""
DocuRecon independent evaluation scoring.

Reads frozen outputs and synthetic ground truth.
Does not rerun or modify DocuRecon.
"""

import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
ROOT = PROJECT / "evaluation_dataset" / "independent_test"

RESULTS = ROOT / "results" / "independent_results_400.csv"
TRUTH = ROOT / "ground_truth" / "case_ground_truth.csv"
OUTPUT = ROOT / "results" / "field_accuracy_summary.json"

FIELDS = {
    "patient_name": "patient_name",
    "mrn": "ocr_mrn",
    "completion_date": "completion_date",
    "completion_time": "completion_time",
}

def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def normalise(value):
    return " ".join(str(value or "").upper().split())


def extracted_value(prediction, field):
    """Read saved predictions without changing the frozen engine."""

    if field != "completion_time":
        return prediction.get(FIELDS[field], "")

    raw_json = prediction.get("raw_result_json", "")

    if not raw_json:
        return ""

    try:
        rows = json.loads(raw_json)
    except (ValueError, TypeError):
        return ""

    if len(rows) != 1:
        return ""

    return rows[0].get("completion_time_ocr", "")


def summarise(rows):
    total = len(rows)

    metrics = {}

    for truth_field, result_field in FIELDS.items():
        correct = sum(
            normalise(truth[truth_field])
            == normalise(extracted_value(pred, truth_field))
            for truth, pred in rows
        )

        metrics[truth_field] = {
            "correct": correct,
            "total": total,
            "accuracy": round(correct / total, 4) if total else None,
        }

    # The existing reconciliation output does not expose
    # legal status as a dedicated top-level column.
    # Do not invent legal-status accuracy.
    metrics["legal_status"] = {
        "status": "NOT_SCORED_FROM_CURRENT_RESULT_SCHEMA"
    }

    return metrics


def main():
    truth_rows = read_csv(TRUTH)
    result_rows = read_csv(RESULTS)

    if len(truth_rows) != 400 or len(result_rows) != 400:
        raise ValueError("Expected 400 truth and 400 result rows")

    truth_ids = [r["case_id"] for r in truth_rows]
    result_ids = [r["case_id"] for r in result_rows]

    if len(set(truth_ids)) != 400:
        raise ValueError("Duplicate ground-truth case IDs")

    if len(set(result_ids)) != 400:
        raise ValueError("Duplicate result case IDs")

    truth = {r["case_id"]: r for r in truth_rows}
    predictions = {r["case_id"]: r for r in result_rows}

    if set(truth) != set(predictions):
        raise ValueError("Ground-truth/result case IDs differ")

    joined = [
        (truth[case_id], predictions[case_id])
        for case_id in sorted(truth)
    ]

    coverage = sum(
        p.get("row_count") == "1"
        and not p.get("runner_error", "").strip()
        for _, p in joined
    )

    metrics = summarise(joined)

    by_quality = {}
    qualities = sorted({
        t["scan_quality"] for t, _ in joined
    })

    for quality in qualities:
        group = [
            pair for pair in joined
            if pair[0]["scan_quality"] == quality
        ]
        by_quality[quality] = {
            "count": len(group),
            "metrics": summarise(group),
        }

    by_scenario = {}

    scenarios = sorted({
        t["primary_scenario"] for t, _ in joined
    })

    for scenario in scenarios:
        group = [
            pair for pair in joined
            if pair[0]["primary_scenario"] == scenario
        ]
        by_scenario[scenario] = {
            "count": len(group),
            "metrics": summarise(group),
        }

    times = [
        float(p["processing_seconds"])
        for _, p in joined
        if p.get("processing_seconds")
    ]

    missing_rows = [
        t["case_id"]
        for t, p in joined
        if p.get("row_count") != "1"
        or p.get("runner_error", "").strip()
    ]

    status_counts = dict(Counter(
        p.get("status", "") or "NO_RESULT"
        for _, p in joined
    ))

    output = {
        "evaluation": "Independent synthetic OCR-only",
        "pipeline_commit": "2a3ebdd",
        "total_cases": 400,
        "reconciliation_coverage": {
            "correctly_returned_one_row": coverage,
            "total": 400,
            "rate": round(coverage / 400, 4),
        },
        "missing_result_cases": missing_rows,
        "field_accuracy": metrics,
        "by_scan_quality": by_quality,
        "by_primary_scenario": by_scenario,
        "status_distribution": status_counts,
        "processing_seconds": {
            "mean": round(statistics.mean(times), 3),
            "median": round(statistics.median(times), 3),
            "min": round(min(times), 3),
            "max": round(max(times), 3),
        } if times else {},
    }

    if OUTPUT.exists():
        raise FileExistsError(
            f"Preserving existing scoring output: {OUTPUT}"
        )

    OUTPUT.write_text(
        json.dumps(output, indent=2),
        encoding="utf-8",
    )

    print("\nDOCURECON INDEPENDENT FIELD EVALUATION")
    print("=" * 60)
    print("Cases:", len(joined))
    print("Reconciliation coverage:", f"{coverage}/400")
    print("Missing result cases:", missing_rows)

    print("\nFIELD EXACT-MATCH ACCURACY")
    for field, values in metrics.items():
        if "accuracy" in values:
            print(
                f"{field}: {values['correct']}/"
                f"{values['total']} "
                f"({values['accuracy'] * 100:.2f}%)"
            )

    print("\nACCURACY BY SCAN QUALITY")
    for quality, group in by_quality.items():
        name = group["metrics"]["patient_name"]
        mrn = group["metrics"]["mrn"]

        print(
            f"{quality} (n={group['count']}): "
            f"name={name['accuracy'] * 100:.2f}%, "
            f"MRN={mrn['accuracy'] * 100:.2f}%"
        )

    print("\nPROCESSING TIME (SECONDS)")
    for key, value in output["processing_seconds"].items():
        print(f"{key}: {value}")

    print("\nSaved:", OUTPUT)


if __name__ == "__main__":
    main()
