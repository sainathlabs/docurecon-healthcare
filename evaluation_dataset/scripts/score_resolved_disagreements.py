
"""
DocuRecon - Resolved AI Disagreement Evaluation

Scores OCR/AI disagreement before and after
legal-status resolution using saved predictions.

No API requests. No changes to original results.
"""

import csv
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

RESULTS = (
    ROOT / "evaluation_dataset"
    / "ai_development" / "results"
)

INPUT = RESULTS / "paired_ocr_ai_30.csv"
OUTPUT = RESULTS / "resolved_disagreement_analysis.csv"

FIELDS = (
    "patient_name",
    "mrn",
    "legal_status",
    "completion_date",
    "completion_time",
)


def agreement(ocr, ai):
    if ocr and ai:
        return "AGREE" if ocr == ai else "DISAGREE"
    if ai:
        return "AI_ONLY"
    if ocr:
        return "OCR_ONLY"
    return "BOTH_MISSING"


def main():
    with INPUT.open(
        newline="", encoding="utf-8-sig"
    ) as handle:
        cases = list(csv.DictReader(handle))

    assert len(cases) == 30, (
        f"Expected 30 cases, found {len(cases)}"
    )

    details = []
    raw_metrics = Counter()
    resolved_metrics = Counter()
    raw_categories = Counter()
    resolved_categories = Counter()

    for case in cases:
        for field in FIELDS:
            ocr = case[f"{field}_ocr"]
            raw_ai = case[f"{field}_ai"]
            resolved_ai = case[
                f"{field}_resolved_ai"
            ]

            truth = case[f"{field}_truth"]
            ocr_error = ocr != truth

            raw_status = agreement(ocr, raw_ai)
            resolved_status = agreement(
                ocr, resolved_ai
            )

            raw_categories[raw_status] += 1
            resolved_categories[resolved_status] += 1

            for status, metrics in (
                (raw_status, raw_metrics),
                (resolved_status, resolved_metrics),
            ):
                flagged = status != "AGREE"

                if ocr_error and flagged:
                    metrics["TP"] += 1
                elif not ocr_error and flagged:
                    metrics["FP"] += 1
                elif ocr_error and not flagged:
                    metrics["FN"] += 1
                else:
                    metrics["TN"] += 1

            details.append({
                "case_id": case["case_id"],
                "scan_quality": case["scan_quality"],
                "field": field,
                "truth": truth,
                "ocr": ocr,
                "raw_ai": raw_ai,
                "resolved_ai": resolved_ai,
                "ocr_error": int(ocr_error),
                "raw_agreement": raw_status,
                "resolved_agreement": resolved_status,
            })

    with OUTPUT.open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(details[0]),
        )
        writer.writeheader()
        writer.writerows(details)

    print("\nDOCURECON RESOLVED DISAGREEMENT EVALUATION")
    print("=" * 65)

    for name, metrics, categories in (
        ("RAW AI", raw_metrics, raw_categories),
        ("RESOLVED AI", resolved_metrics, resolved_categories),
    ):
        tp = metrics["TP"]
        fp = metrics["FP"]
        fn = metrics["FN"]
        tn = metrics["TN"]

        precision = tp / (tp + fp) if tp + fp else 0
        recall = tp / (tp + fn) if tp + fn else 0
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall else 0
        )

        print(f"\n{name}")
        print("-" * 40)
        print(f"TP={tp} FP={fp} FN={fn} TN={tn}")
        print(f"Precision: {precision:.2%}")
        print(f"Recall:    {recall:.2%}")
        print(f"F1 score:  {f1:.4f}")

        print("Agreement categories:")
        for category, count in sorted(categories.items()):
            print(f"  {category}: {count}")

    assert sum(raw_metrics.values()) == 150
    assert sum(resolved_metrics.values()) == 150

    print("\nChanged comparisons:")
    for row in details:
        if row["raw_agreement"] != row[
            "resolved_agreement"
        ]:
            print(
                row["case_id"],
                row["field"],
                row["raw_agreement"],
                "->",
                row["resolved_agreement"],
            )

    print("\nDetailed results:", OUTPUT)


if __name__ == "__main__":
    main()
