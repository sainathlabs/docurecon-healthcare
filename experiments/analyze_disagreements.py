
"""
DocuRecon - Hybrid Disagreement Analysis

Research-only analysis of unresolved fields.
Ground truth is used for evaluation, never for
selecting production extraction values.
"""

import csv
from pathlib import Path

from experiments.normalize_fields import normalize_field


ROOT = Path(__file__).resolve().parents[1]

GROUND_TRUTH = (
    ROOT / "sample_data" / "paperwork" / "ground_truth.csv"
)

AUDIT = ROOT / "results" / "hybrid_audit.csv"

OUTPUT = ROOT / "results" / "disagreement_analysis.csv"


def read_csv(path):
    with path.open(
        "r", newline="", encoding="utf-8-sig"
    ) as file:
        return list(csv.DictReader(file))


def main():
    ground_truth = {
        row["filename"]: row
        for row in read_csv(GROUND_TRUTH)
    }

    analysis = []

    for row in read_csv(AUDIT):

        if row["status"] == "accepted_agreement":
            continue

        filename = row["filename"]
        field = row["field"]

        expected = normalize_field(
            field,
            ground_truth[filename].get(field),
        )

        ocr_value = normalize_field(
            field, row.get("ocr_value")
        )

        ai_value = normalize_field(
            field, row.get("ai_value")
        )

        ocr_correct = (
            ocr_value is not None
            and ocr_value == expected
        )

        ai_correct = (
            ai_value is not None
            and ai_value == expected
        )

        if ocr_correct and ai_correct:
            category = "both_correct"
        elif ocr_correct:
            category = "ocr_correct_only"
        elif ai_correct:
            category = "ai_correct_only"
        else:
            category = "neither_correct"

        analysis.append({
            "filename": filename,
            "field": field,
            "expected": expected or "",
            "ocr_value": ocr_value or "",
            "ai_value": ai_value or "",
            "ocr_correct": ocr_correct,
            "ai_correct": ai_correct,
            "category": category,
        })

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    columns = [
        "filename",
        "field",
        "expected",
        "ocr_value",
        "ai_value",
        "ocr_correct",
        "ai_correct",
        "category",
    ]

    with OUTPUT.open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file, fieldnames=columns
        )
        writer.writeheader()
        writer.writerows(analysis)

    print("\nDocuRecon Disagreement Analysis")
    print("-" * 40)

    for row in analysis:
        print(
            f"{row['field']}: {row['category']} "
            f"({row['filename']})"
        )

    print(f"\nSaved to: {OUTPUT}")


if __name__ == "__main__":
    main()
