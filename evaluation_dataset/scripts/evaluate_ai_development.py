
"""
DocuRecon - AI Development Evaluation

Evaluates AI extraction against ground truth.
Uses only approved synthetic development PDFs.

Does not modify the frozen OCR baseline.
"""

import argparse
import csv
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]

# Allow imports from both the project root and src.
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from docurecon.ai.document_extractor import extract_document
from experiments.normalize_fields import normalize_field


DATASET = ROOT / "evaluation_dataset" / "ai_development"
TRUTH_FILE = DATASET / "ground_truth" / "ai_development_ground_truth.csv"
PAPERWORK = DATASET / "paperwork"
RESULTS = DATASET / "results"

FIELDS = (
    "patient_name",
    "mrn",
    "legal_status",
    "completion_date",
    "completion_time",
)


def evaluate(case):
    pdf_path = PAPERWORK / case["document"]

    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)

    response = extract_document(pdf_path)
    extracted = response["extracted_fields"]

    raw_output_dir = RESULTS / "raw_ai_responses"
    raw_output_dir.mkdir(parents=True, exist_ok=True)

    raw_output_path = raw_output_dir / f"{case['case_id']}.json"

    with raw_output_path.open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(
            response,
            handle,
            indent=2,
            ensure_ascii=False,
        )

    result = {
        "case_id": case["case_id"],
        "document": case["document"],
        "scan_quality": case["scan_quality"],
        "model": response["model"],
        "elapsed_seconds": response["elapsed_seconds"],
        "input_tokens": response["input_tokens"],
        "output_tokens": response["output_tokens"],
    }

    for field in FIELDS:
        expected = normalize_field(field, case[field])
        actual = normalize_field(field, extracted.get(field))

        result[f"{field}_expected"] = expected
        result[f"{field}_ai"] = actual
        result[f"{field}_correct"] = int(
            expected is not None
            and actual == expected
        )

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Number of documents to evaluate",
    )
    parser.add_argument(
        "--case-ids",
        nargs="+",
        help="Specific development case IDs",
    )

    args = parser.parse_args()

    with TRUTH_FILE.open(
        newline="", encoding="utf-8-sig"
    ) as handle:
        cases = list(csv.DictReader(handle))

    if args.case_ids:
        wanted = set(args.case_ids)
        cases = [
            case for case in cases
            if case["case_id"] in wanted
        ]

        missing = wanted - {
            case["case_id"] for case in cases
        }

        if missing:
            raise ValueError(
                f"Unknown case IDs: {sorted(missing)}"
            )
    else:
        cases = cases[:args.limit]

    RESULTS.mkdir(parents=True, exist_ok=True)

    output = []

    for index, case in enumerate(cases, start=1):
        print(
            f"\n[{index}/{len(cases)}] "
            f"{case['case_id']} | "
            f"{case['scan_quality']}",
            flush=True,
        )

        try:
            result = evaluate(case)
        except Exception as exc:
            print(
                f"AI extraction failed: "
                f"{type(exc).__name__}: {exc}"
            )
            continue

        output.append(result)

        for field in FIELDS:
            print(
                f"  {field}: "
                f"{'CORRECT' if result[f'{field}_correct'] else 'INCORRECT'}"
                f" | AI={result[f'{field}_ai']}"
                f" | Truth={result[f'{field}_expected']}"
            )

        print(
            "  Time:",
            result["elapsed_seconds"],
            "seconds"
        )

    if not output:
        print("No successful AI extractions.")
        sys.exit(1)

    output_path = (
        RESULTS / "ai_development_results.csv"
    )

    with output_path.open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(output[0]),
        )
        writer.writeheader()
        writer.writerows(output)

    print("\n" + "=" * 60)
    print("DOCURECON AI DEVELOPMENT SUMMARY")
    print("=" * 60)
    print("Successful cases:", len(output))

    for field in FIELDS:
        correct = sum(
            row[f"{field}_correct"]
            for row in output
        )
        accuracy = 100 * correct / len(output)

        print(
            f"{field}: "
            f"{correct}/{len(output)} "
            f"({accuracy:.2f}%)"
        )

    print("\nResults saved:", output_path)


if __name__ == "__main__":
    main()
