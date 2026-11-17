
"""
DocuRecon - Paired OCR and AI Development Evaluation

Compares existing Tesseract OCR with saved AI responses
on the same 30 synthetic development documents.

No AI API requests.
No modifications to the frozen baseline.
"""

import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from docurecon.parsers.paperwork_parser import extract_paperwork
from docurecon.legal_status_resolver import resolve_legal_status
from experiments.normalize_fields import normalize_field

DATA = ROOT / "evaluation_dataset" / "ai_development"
TRUTH = DATA / "ground_truth" / "ai_development_ground_truth.csv"
PDF_DIR = DATA / "paperwork"
RAW_AI = DATA / "results" / "raw_ai_responses"
OUTPUT = DATA / "results" / "paired_ocr_ai_30.csv"

FIELDS = (
    "patient_name",
    "mrn",
    "legal_status",
    "completion_date",
    "completion_time",
)


def norm(field, value):
    return normalize_field(field, value)


def main():
    with TRUTH.open(newline="", encoding="utf-8-sig") as f:
        cases = list(csv.DictReader(f))

    if len(cases) != 30:
        raise ValueError(f"Expected 30 cases, found {len(cases)}")

    rows = []
    failures = []

    for index, case in enumerate(cases, 1):
        case_id = case["case_id"]
        pdf_path = PDF_DIR / case["document"]
        ai_path = RAW_AI / f"{case_id}.json"

        print(
            f"[{index}/30] {case_id} | "
            f"{case['scan_quality']}",
            flush=True,
        )

        if not pdf_path.is_file():
            raise FileNotFoundError(pdf_path)

        if not ai_path.is_file():
            raise FileNotFoundError(ai_path)

        ai_response = json.loads(
            ai_path.read_text(encoding="utf-8")
        )
        ai_fields = ai_response["extracted_fields"]

        start = time.perf_counter()

        try:
            ocr = extract_paperwork(pdf_path)
            ocr_error = ""
        except Exception as exc:
            ocr = {}
            ocr_error = f"{type(exc).__name__}: {exc}"
            failures.append(case_id)

        ocr_seconds = round(
            time.perf_counter() - start, 3
        )

        # The OCR parser puts the legal reference
        # in "form_type", not "legal_status".
        ocr_fields = {
            "patient_name": ocr.get("patient_name"),
            "mrn": ocr.get("mrn"),
            "legal_status": ocr.get("form_type"),
            "completion_date": ocr.get("completion_date"),
            "completion_time": ocr.get("completion_time"),
        }

        # Resolve AI evidence independently.
        # No OCR evidence is supplied here.
        resolved_ai = resolve_legal_status(
            {"legal_status": None},
            ai_fields,
        )

        row = {
            "case_id": case_id,
            "document": case["document"],
            "scan_quality": case["scan_quality"],
            "expected_legal_status": case["legal_status"],
            "ocr_seconds": ocr_seconds,
            "ai_seconds": ai_response.get(
                "elapsed_seconds", ""
            ),
            "ai_input_tokens": ai_response.get(
                "input_tokens", ""
            ),
            "ai_output_tokens": ai_response.get(
                "output_tokens", ""
            ),
            "ocr_error": ocr_error,
            "ocr_review_reasons": ";".join(
                ocr.get("review_reasons", [])
            ),
            "ai_legal_resolution": resolved_ai[
                "resolution"
            ],
        }

        for field in FIELDS:
            expected = norm(field, case.get(field))
            ocr_value = norm(
                field, ocr_fields.get(field)
            )
            ai_value = norm(
                field, ai_fields.get(field)
            )

            if field == "legal_status":
                resolved_value = resolved_ai[
                    "legal_status"
                ]
            else:
                resolved_value = ai_value

            ocr_correct = (
                expected is not None
                and ocr_value == expected
            )
            ai_correct = (
                expected is not None
                and ai_value == expected
            )
            resolved_correct = (
                expected is not None
                and resolved_value == expected
            )

            if ocr_value and ai_value:
                agreement = (
                    "AGREE"
                    if ocr_value == ai_value
                    else "DISAGREE"
                )
            elif ai_value:
                agreement = "AI_ONLY"
            elif ocr_value:
                agreement = "OCR_ONLY"
            else:
                agreement = "BOTH_MISSING"

            row[f"{field}_truth"] = expected or ""
            row[f"{field}_ocr"] = ocr_value or ""
            row[f"{field}_ai"] = ai_value or ""
            row[f"{field}_resolved_ai"] = (
                resolved_value or ""
            )
            row[f"{field}_ocr_correct"] = int(
                ocr_correct
            )
            row[f"{field}_ai_correct"] = int(
                ai_correct
            )
            row[f"{field}_resolved_correct"] = int(
                resolved_correct
            )
            row[f"{field}_agreement"] = agreement

        rows.append(row)

        correct_ocr = sum(
            row[f"{field}_ocr_correct"]
            for field in FIELDS
        )
        correct_ai = sum(
            row[f"{field}_ai_correct"]
            for field in FIELDS
        )

        print(
            f"  OCR: {correct_ocr}/5 | "
            f"Raw AI: {correct_ai}/5 | "
            f"OCR time: {ocr_seconds:.2f}s"
        )

    OUTPUT.parent.mkdir(
        parents=True, exist_ok=True
    )

    with OUTPUT.open(
        "w", newline="", encoding="utf-8"
    ) as f:
        writer = csv.DictWriter(
            f, fieldnames=list(rows[0].keys())
        )
        writer.writeheader()
        writer.writerows(rows)

    print("\n" + "=" * 65)
    print("DOCURECON PAIRED OCR vs AI DEVELOPMENT EVALUATION")
    print("=" * 65)

    for field in FIELDS:
        values = []

        for method, suffix in (
            ("OCR", "ocr_correct"),
            ("Raw AI", "ai_correct"),
            ("Resolved AI", "resolved_correct"),
        ):
            correct = sum(
                row[f"{field}_{suffix}"]
                for row in rows
            )
            values.append(
                f"{method}={correct}/30 "
                f"({correct / 30 * 100:.2f}%)"
            )

        print(field)
        print("  " + " | ".join(values))

    print("\nOVERALL FIELD ACCURACY")

    for method, suffix in (
        ("OCR", "ocr_correct"),
        ("Raw AI", "ai_correct"),
        ("Resolved AI", "resolved_correct"),
    ):
        correct = sum(
            row[f"{field}_{suffix}"]
            for row in rows
            for field in FIELDS
        )
        total = len(rows) * len(FIELDS)

        print(
            f"{method}: {correct}/{total} "
            f"({correct / total * 100:.2f}%)"
        )

    print("\nBY SCAN QUALITY")

    groups = defaultdict(list)

    for row in rows:
        groups[row["scan_quality"]].append(row)

    for quality, group in sorted(groups.items()):
        total = len(group) * len(FIELDS)

        ocr_correct = sum(
            r[f"{f}_ocr_correct"]
            for r in group
            for f in FIELDS
        )
        ai_correct = sum(
            r[f"{f}_ai_correct"]
            for r in group
            for f in FIELDS
        )

        print(
            f"{quality}: n={len(group)} | "
            f"OCR={ocr_correct}/{total} | "
            f"Raw AI={ai_correct}/{total}"
        )

    print("\nOCR/AI DISAGREEMENT ANALYSIS")

    detected_ocr_errors = 0
    missed_ocr_errors = 0
    false_alerts = 0
    both_correct = 0

    for row in rows:
        for field in FIELDS:
            ocr_ok = bool(
                row[f"{field}_ocr_correct"]
            )
            ai_ok = bool(
                row[f"{field}_ai_correct"]
            )
            agreement = row[
                f"{field}_agreement"
            ]

            flagged = agreement != "AGREE"

            if not ocr_ok and flagged:
                detected_ocr_errors += 1
            elif not ocr_ok and not flagged:
                missed_ocr_errors += 1

            if ocr_ok and flagged:
                false_alerts += 1

            if ocr_ok and ai_ok:
                both_correct += 1

    print(
        "OCR errors flagged by disagreement:",
        detected_ocr_errors
    )
    print(
        "OCR errors missed by disagreement:",
        missed_ocr_errors
    )
    print(
        "Correct OCR fields unnecessarily flagged:",
        false_alerts
    )
    print(
        "Fields correct in both OCR and AI:",
        both_correct
    )

    print("\nOCR extraction failures:", failures)

    print(
        "Mean OCR time:",
        round(
            sum(r["ocr_seconds"] for r in rows)
            / len(rows), 3
        ),
        "seconds",
    )
    print(
        "Mean AI time:",
        round(
            sum(float(r["ai_seconds"]) for r in rows)
            / len(rows), 3
        ),
        "seconds",
    )

    print("\nResults saved:", OUTPUT)


if __name__ == "__main__":
    main()
