
"""
DocuRecon - Hybrid Extraction Benchmark

Combines saved Tesseract OCR and OpenAI Vision
predictions using conservative field agreement.

No new API calls are made.
"""

import csv
from pathlib import Path

from experiments.normalize_fields import normalize_field


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"

GROUND_TRUTH = (
    ROOT / "sample_data" / "paperwork" / "ground_truth.csv"
)

OCR_INPUT = RESULTS / "ocr_baseline.csv"
AI_INPUT = ROOT / "ai_benchmark_results.csv"

HYBRID_OUTPUT = RESULTS / "hybrid_baseline.csv"
AUDIT_OUTPUT = RESULTS / "hybrid_audit.csv"

FIELDS = [
    "patient_name",
    "mrn",
    "completion_date",
    "completion_time",
]


def read_csv(path):
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")

    with path.open(
        "r", newline="", encoding="utf-8-sig"
    ) as file:
        return list(csv.DictReader(file))


def index_by(rows, key):
    records = {}

    for row in rows:
        filename = (row.get(key) or "").strip()

        if not filename:
            raise ValueError(
                f"Missing {key} in input CSV"
            )

        if filename in records:
            raise ValueError(
                f"Duplicate filename: {filename}"
            )

        records[filename] = row

    return records


def compare_field(field, ocr_raw, ai_raw):
    ocr_value = normalize_field(field, ocr_raw)
    ai_value = normalize_field(field, ai_raw)

    if ocr_value is not None and ai_value is not None:

        if ocr_value == ai_value:
            return (
                ocr_value,
                "accepted_agreement",
                "Both extractors agree",
            )

        return (
            "",
            "disagreement",
            "OCR and AI returned different values",
        )

    if ocr_value is not None:
        return (
            "",
            "ocr_only",
            "Only OCR returned a usable value",
        )

    if ai_value is not None:
        return (
            "",
            "ai_only",
            "Only AI returned a usable value",
        )

    return (
        "",
        "missing",
        "Neither extractor returned a usable value",
    )


def save_csv(path, rows, columns):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file, fieldnames=columns
        )
        writer.writeheader()
        writer.writerows(rows)


def main():
    ground_truth = index_by(
        read_csv(GROUND_TRUTH), "filename"
    )

    ocr_records = index_by(
        read_csv(OCR_INPUT), "source"
    )

    ai_records = index_by(
        read_csv(AI_INPUT), "source"
    )

    hybrid_records = []
    audit_records = []

    for filename in sorted(ground_truth):

        ocr = ocr_records.get(filename, {})
        ai = ai_records.get(filename, {})

        hybrid = {"source": filename}

        for field in FIELDS:

            ocr_raw = ocr.get(field)
            ai_raw = ai.get(field)

            value, status, reason = compare_field(
                field, ocr_raw, ai_raw
            )

            hybrid[field] = value

            audit_records.append({
                "filename": filename,
                "field": field,
                "ocr_value": normalize_field(
                    field, ocr_raw
                ) or "",
                "ai_value": normalize_field(
                    field, ai_raw
                ) or "",
                "hybrid_value": value,
                "status": status,
                "reason": reason,
            })

        hybrid_records.append(hybrid)

    save_csv(
        HYBRID_OUTPUT,
        hybrid_records,
        ["source", *FIELDS],
    )

    save_csv(
        AUDIT_OUTPUT,
        audit_records,
        [
            "filename",
            "field",
            "ocr_value",
            "ai_value",
            "hybrid_value",
            "status",
            "reason",
        ],
    )

    accepted = sum(
        row["status"] == "accepted_agreement"
        for row in audit_records
    )

    disagreements = sum(
        row["status"] == "disagreement"
        for row in audit_records
    )

    total = len(audit_records)

    print("\nDocuRecon Hybrid Extraction Benchmark")
    print("-" * 45)
    print(f"Total fields: {total}")
    print(f"Accepted by agreement: {accepted}")
    print(f"Disagreements: {disagreements}")
    print(f"Other unresolved fields: {total - accepted - disagreements}")

    coverage = (accepted / total * 100) if total else 0
    print(f"Coverage: {coverage:.2f}%")

    print(f"\nHybrid predictions: {HYBRID_OUTPUT}")
    print(f"Audit report: {AUDIT_OUTPUT}")


if __name__ == "__main__":
    main()
