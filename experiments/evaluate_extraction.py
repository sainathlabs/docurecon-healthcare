
"""
DocuRecon - Document Extraction Evaluation
==========================================

Evaluate extraction accuracy for:
    1. Traditional Tesseract OCR
    2. OpenAI Vision

Both methods are evaluated against the same
synthetic ground-truth dataset.

Usage:
    py -m experiments.evaluate_extraction --method ai
    py -m experiments.evaluate_extraction --method ocr
"""

import argparse
import csv
from pathlib import Path

from experiments.normalize_fields import normalize_field


# --------------------------------------------------
# Project paths
# --------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]

GROUND_TRUTH = (
    ROOT / "sample_data" / "paperwork" / "ground_truth.csv"
)

RESULTS_DIR = ROOT / "results"


METHODS = {
    "ai": {
        "name": "OpenAI Vision",
        "predictions": ROOT / "ai_benchmark_results.csv",
        "output": RESULTS_DIR / "ai_evaluation.csv",
    },
    "ocr": {
        "name": "Tesseract OCR",
        "predictions": RESULTS_DIR / "ocr_baseline.csv",
        "output": RESULTS_DIR / "ocr_evaluation.csv",
    },
    "hybrid": {
        "name": "Hybrid OCR + AI",
        "predictions": RESULTS_DIR / "hybrid_baseline.csv",
        "output": RESULTS_DIR / "hybrid_evaluation.csv",
    },
}


FIELDS = [
    "patient_name",
    "mrn",
    "completion_date",
    "completion_time",
]


# --------------------------------------------------
# CSV utilities
# --------------------------------------------------

def read_csv(path: Path) -> list[dict]:
    """Read a CSV file and return its records."""

    if not path.exists():
        raise FileNotFoundError(
            f"Required CSV file not found: {path}"
        )

    with path.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        reader = csv.DictReader(file)

        if not reader.fieldnames:
            raise ValueError(f"CSV has no header: {path}")

        return list(reader)


def index_records(records: list[dict], key: str) -> dict:
    """Index records by filename and reject duplicate IDs."""

    indexed = {}

    for row in records:
        filename = (row.get(key) or "").strip()

        if not filename:
            raise ValueError(
                f"Missing '{key}' value in CSV record."
            )

        if filename in indexed:
            raise ValueError(
                f"Duplicate record found: {filename}"
            )

        indexed[filename] = row

    return indexed


# --------------------------------------------------
# Extraction evaluation
# --------------------------------------------------

def evaluate(ground_truth: dict, predictions: dict) -> list[dict]:
    """Compare extracted fields against ground truth."""

    results = []

    for filename, expected in ground_truth.items():

        predicted = predictions.get(filename)
        prediction_available = predicted is not None

        if predicted is None:
            predicted = {}

        for field in FIELDS:

            expected_value = normalize_field(
                field,
                expected.get(field),
            )

            predicted_value = normalize_field(
                field,
                predicted.get(field),
            )

            correct = (
                prediction_available
                and expected_value is not None
                and predicted_value == expected_value
            )

            results.append({
                "filename": filename,
                "field": field,
                "expected": expected_value or "",
                "predicted": predicted_value or "",
                "correct": correct,
                "prediction_available": prediction_available,
            })

    return results


# --------------------------------------------------
# Save evaluation results
# --------------------------------------------------

def save_results(results: list[dict], output: Path):
    """Save detailed evaluation results to CSV."""

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fieldnames = [
        "filename",
        "field",
        "expected",
        "predicted",
        "correct",
        "prediction_available",
    ]

    with output.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(results)


# --------------------------------------------------
# Display evaluation summary
# --------------------------------------------------

def print_summary(results: list[dict], method_name: str):
    """Display accuracy for each extracted field."""

    print()
    print("=" * 55)
    print(f"DocuRecon - {method_name} Extraction Evaluation")
    print("=" * 55)

    total_correct = 0
    total_fields = 0

    for field in FIELDS:

        field_results = [
            row for row in results
            if row["field"] == field
        ]

        correct = sum(
            1 for row in field_results
            if row["correct"]
        )

        total = len(field_results)

        accuracy = (
            (correct / total) * 100
            if total else 0.0
        )

        total_correct += correct
        total_fields += total

        print(
            f"{field:<20} "
            f"{correct}/{total} correct "
            f"({accuracy:.2f}%)"
        )

    overall_accuracy = (
        (total_correct / total_fields) * 100
        if total_fields else 0.0
    )

    print("-" * 55)

    print(
        f"{'OVERALL ACCURACY':<20} "
        f"{total_correct}/{total_fields} "
        f"({overall_accuracy:.2f}%)"
    )

    print("=" * 55)


# --------------------------------------------------
# Main
# --------------------------------------------------

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Evaluate DocuRecon document extraction accuracy."
        )
    )

    parser.add_argument(
        "--method",
        choices=METHODS.keys(),
        default="ai",
        help="Extraction method: ai or ocr",
    )

    args = parser.parse_args()

    config = METHODS[args.method]

    # Read datasets
    ground_truth_rows = read_csv(GROUND_TRUTH)
    prediction_rows = read_csv(config["predictions"])

    # Validate required columns
    required_ground_truth = {"filename", *FIELDS}
    required_predictions = {"source", *FIELDS}

    if ground_truth_rows:
        missing = required_ground_truth - set(
            ground_truth_rows[0].keys()
        )
        if missing:
            raise ValueError(
                f"Missing ground-truth columns: {sorted(missing)}"
            )

    if prediction_rows:
        missing = required_predictions - set(
            prediction_rows[0].keys()
        )
        if missing:
            raise ValueError(
                f"Missing prediction columns: {sorted(missing)}"
            )

    # Index records
    ground_truth = index_records(
        ground_truth_rows,
        "filename",
    )

    predictions = index_records(
        prediction_rows,
        "source",
    )

    # Check incomplete benchmark runs
    missing_files = (
        set(ground_truth) - set(predictions)
    )

    if missing_files:
        print("\nWARNING: Missing predictions for:")

        for filename in sorted(missing_files):
            print(f"  - {filename}")

    # Evaluate
    results = evaluate(
        ground_truth,
        predictions,
    )

    # Display summary
    print_summary(
        results,
        config["name"],
    )

    # Export results
    save_results(
        results,
        config["output"],
    )

    print(
        f"\nDetailed results saved to: "
        f"{config['output']}"
    )


if __name__ == "__main__":
    main()
