
"""Evaluate DocuRecon's 10-case synthetic reconciliation pilot."""

import csv
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]

RESULTS = (
    PROJECT / "evaluation_dataset"
    / "pilot" / "reconciliation_results.csv"
)

SCENARIOS = (
    PROJECT / "evaluation_dataset"
    / "manifests" / "pilot_reconciliation_scenarios.csv"
)

EXPECTATIONS = {
    "MATCH_AA": ("PROVISIONAL_MATCH", ""),
    "APPLICATION_ERROR": (
        "PROVISIONAL_EXCEPTION", "APPLICATION_ERROR"
    ),
    "NO_HL7_IN_SAMPLE": (
        "OCR_UNCERTAIN", "NO_HL7_CANDIDATE_IN_SUPPLIED_FILES"
    ),
    "MRN_MISMATCH": (
        "OCR_UNCERTAIN", "MRN_DISAGREEMENT"
    ),
    "NO_ACK_IN_SAMPLE": (
        "PROVISIONAL_EXCEPTION", "NO_ACK_IN_SUPPLIED_FILES"
    ),
    "COMPLETION_TIME_MISMATCH": (
        "PROVISIONAL_EXCEPTION",
        "COMPLETION_TIME_MISMATCH_PROVISIONAL"
    ),
    "DUPLICATE_CANDIDATES": (
        "OCR_UNCERTAIN",
        "AMBIGUOUS_MULTIPLE_HL7_CANDIDATES"
    ),
    "APPLICATION_REJECTED": (
        "PROVISIONAL_EXCEPTION", "APPLICATION_REJECTED"
    ),
}


def load_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def main():
    results = load_csv(RESULTS)
    scenarios = load_csv(SCENARIOS)

    if len(results) != 10 or len(scenarios) != 10:
        raise ValueError("Expected exactly 10 pilot results and scenarios")

    by_document = {
        row["paperwork_file"]: row
        for row in results
    }

    if len(by_document) != 10:
        raise ValueError("Duplicate paperwork results detected")

    passed = 0
    partial = 0
    failed = 0

    print("\nDOCURECON PILOT SCENARIO EVALUATION")
    print("=" * 65)

    for case in scenarios:
        document = case["document"]
        scenario = case["scenario"]

        if document not in by_document:
            raise ValueError(f"Missing result: {document}")

        result = by_document[document]
        expected_status, expected_issue = EXPECTATIONS[scenario]

        actual_status = result["status"]
        issues = set(
            result.get("issues", "").split("; ")
        )
        reasons = set(
            result.get("uncertainty_reasons", "").split("; ")
        )

        status_ok = actual_status == expected_status
        issue_ok = (
            not expected_issue
            or expected_issue in issues
        )

        if status_ok and issue_ok:
            verdict = "PASS"
            passed += 1
        elif (
            scenario == "MRN_MISMATCH"
            and status_ok
            and "PATIENT_IDENTIFIER_REQUIRES_VALIDATION"
            in reasons
        ):
            verdict = "PARTIAL"
            partial += 1
        else:
            verdict = "FAIL"
            failed += 1

        print(
            f"{case['case_id']} | {scenario} | {verdict}"
        )

    print("\nSUMMARY")
    print("Passed:", passed)
    print("Partial:", partial)
    print("Failed:", failed)
    print("Total:", len(scenarios))


if __name__ == "__main__":
    main()
