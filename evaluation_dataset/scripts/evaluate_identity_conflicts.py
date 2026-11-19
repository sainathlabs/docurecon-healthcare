
"""
DocuRecon - Patient Identity Conflict Evaluation

Evaluates three-source identity consistency using
30 synthetic development cases and saved predictions.

Constructs synthetic HL7 identity scenarios.
Does not call the OpenAI API.
Does not modify the independent evaluation dataset.

This is a component-level development experiment,
not a complete HL7 candidate-linkage evaluation.
"""

import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from docurecon.reconciliation.identity_validation import (
    assess_identity,
)

DATA = ROOT / "evaluation_dataset" / "ai_development"
INPUT = DATA / "results" / "paired_ocr_ai_30.csv"
OUTPUT = DATA / "results" / "identity_conflict_evaluation.csv"


def main():
    with INPUT.open(
        newline="", encoding="utf-8-sig"
    ) as handle:
        cases = list(csv.DictReader(handle))

    if len(cases) != 30:
        raise ValueError(
            f"Expected 30 development cases, found {len(cases)}"
        )

    results = []
    counts = Counter()

    for case in cases:
        case_id = case["case_id"]

        truth_name = case["patient_name_truth"]
        truth_mrn = case["mrn_truth"]

        # Saved document extraction predictions.
        ocr_name = case["patient_name_ocr"]
        ocr_mrn = case["mrn_ocr"]
        ai_name = case["patient_name_ai"]
        ai_mrn = case["mrn_ai"]

        # Controlled HL7 simulation.
        # Ground truth is used to construct fixtures,
        # not to correct OCR or AI predictions.
        scenarios = [
            {
                "scenario": "MATCHING_IDENTITY",
                "hl7_name": truth_name,
                "hl7_mrn": truth_mrn,
                "expected_name_conflict": False,
                "expected_mrn_conflict": False,
            },
            {
                "scenario": "HL7_NAME_CONFLICT",
                "hl7_name": "SYNTHETIC, DIFFERENT",
                "hl7_mrn": truth_mrn,
                "expected_name_conflict": True,
                "expected_mrn_conflict": False,
            },
            {
                "scenario": "HL7_MRN_CONFLICT",
                "hl7_name": truth_name,
                "hl7_mrn": "SYN-CONFLICT-999",
                "expected_name_conflict": False,
                "expected_mrn_conflict": True,
            },
        ]

        for scenario in scenarios:
            assessment = assess_identity(
                ocr_name=ocr_name,
                ocr_mrn=ocr_mrn,
                ai_name=ai_name,
                ai_mrn=ai_mrn,
                hl7_name=scenario["hl7_name"],
                hl7_mrn=scenario["hl7_mrn"],
            )

            name_status = assessment["name"]["status"]
            mrn_status = assessment["mrn"]["status"]

            # Overall conflict indicators include OCR/AI
            # discrepancies, not exclusively HL7 errors.
            name_flag = name_status == "CONFLICT"
            mrn_flag = mrn_status == "CONFLICT"

            row = {
                "case_id": case_id,
                "scan_quality": case["scan_quality"],
                "scenario": scenario["scenario"],
                "name_status": name_status,
                "mrn_status": mrn_status,
                "name_conflict_flag": int(name_flag),
                "mrn_conflict_flag": int(mrn_flag),
                "expected_hl7_name_conflict": int(
                    scenario["expected_name_conflict"]
                ),
                "expected_hl7_mrn_conflict": int(
                    scenario["expected_mrn_conflict"]
                ),
                "review_required": int(
                    assessment["identity_review_required"]
                ),
                "identity_verified": int(
                    assessment["identity_verified"]
                ),
            }

            results.append(row)

            key = scenario["scenario"]
            counts[(key, "total")] += 1
            counts[(key, "name_flag")] += int(name_flag)
            counts[(key, "mrn_flag")] += int(mrn_flag)
            counts[(key, "review")] += int(
                assessment["identity_review_required"]
            )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT.open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(results[0]),
        )
        writer.writeheader()
        writer.writerows(results)

    print("\nDOCURECON IDENTITY CONFLICT EVALUATION")
    print("=" * 65)

    for scenario in (
        "MATCHING_IDENTITY",
        "HL7_NAME_CONFLICT",
        "HL7_MRN_CONFLICT",
    ):
        print(f"\n{scenario}")
        print("-" * 45)
        print("Cases:", counts[(scenario, "total")])
        print("Name conflict flags:",
              counts[(scenario, "name_flag")])
        print("MRN conflict flags:",
              counts[(scenario, "mrn_flag")])
        print("Human review flags:",
              counts[(scenario, "review")])

    assert len(results) == 90
    assert all(
        row["identity_verified"] == 0
        for row in results
    )

    print("\nTotal assessments:", len(results))
    print("Results saved:", OUTPUT)


if __name__ == "__main__":
    main()
