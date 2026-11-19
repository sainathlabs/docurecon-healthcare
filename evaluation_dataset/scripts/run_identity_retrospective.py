
"""
DocuRecon retrospective identity-conflict evaluation.

Reuses the original case-isolation and OCR-only
evaluation procedure with the current reconciliation
engine.

Does not modify the frozen independent results.
Does not call the AI API.

This is a retrospective development evaluation,
not a new independent test.
"""

import argparse
import csv
import importlib.util
import re
from collections import Counter
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
ROOT = PROJECT / "evaluation_dataset" / "independent_test"
RESULTS = ROOT / "results"

BASELINE_FILE = RESULTS / "independent_results_400.csv"
TRUTH_FILE = ROOT / "ground_truth" / "case_ground_truth.csv"

FLAG = "PAPERWORK_HL7_NAME_DISAGREEMENT"


def load_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_original_runner():
    """Reuse the original case-by-case evaluation logic."""
    path = (
        PROJECT
        / "evaluation_dataset/scripts/run_independent_evaluation.py"
    )

    spec = importlib.util.spec_from_file_location(
        "docurecon_original_evaluation_runner",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Deliberately do not call check_pipeline():
    # this run uses the CURRENT engine and writes
    # to a separate retrospective output file.
    return module


def split_ids(value):
    """Read expected HL7 control IDs for candidate checks."""
    return {
        part.strip()
        for part in re.split(r"[,;|\s]+", value or "")
        if part.strip()
    }


def has_issue(value, issue):
    return issue in {
        item.strip()
        for item in (value or "").split(";")
    }



def main():
    parser = argparse.ArgumentParser()

    # Select either a smoke test or the full evaluation.
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--smoke", action="store_true")
    group.add_argument("--all", action="store_true")

    # Optional label to create a separate results file.
    parser.add_argument(
        "--label",
        default="",
        help="Optional suffix for a new retrospective output file",
    )

    args = parser.parse_args()

    # --------------------------------------------------
    # 1. Load ground truth and frozen baseline
    # --------------------------------------------------

    truth = load_csv(TRUTH_FILE)

    baseline = {
        row["case_id"]: row
        for row in load_csv(BASELINE_FILE)
    }

    assert len(truth) == 400
    assert len(baseline) == 400

    # --------------------------------------------------
    # 2. Select evaluation cases and output filename
    # --------------------------------------------------

    if args.smoke:
        case_ids = {
            "0001", "0002", "0003",
            "0217", "0228",
        }

        selected = [
            case for case in truth
            if case["case_id"] in case_ids
        ]

        output_path = (
            RESULTS / "identity_retrospective_smoke_5.csv"
        )

        assert len(selected) == 5

    else:
        selected = truth

        output_path = (
            RESULTS / "identity_retrospective_400.csv"
        )

    # --------------------------------------------------
    # 3. Apply optional output label
    # --------------------------------------------------
    # IMPORTANT:
    # Apply the label BEFORE checking file existence.
    # This preserves earlier retrospective results.

    if args.label:
        if not re.fullmatch(
            r"[A-Za-z0-9_-]+",
            args.label,
        ):
            raise ValueError(
                "Label may contain only letters, numbers, "
                "underscores and hyphens."
            )

        output_path = output_path.with_name(
            f"{output_path.stem}_{args.label}"
            f"{output_path.suffix}"
        )

    # --------------------------------------------------
    # 4. Prevent accidental result overwriting
    # --------------------------------------------------

    if output_path.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing results: "
            f"{output_path}"
        )

    # --------------------------------------------------
    # 5. Load the original case-isolation runner
    # --------------------------------------------------

    runner = load_original_runner()

    output = []
    summary = Counter()

    print("\nDOCURECON IDENTITY RETROSPECTIVE")
    print("=" * 70)
    print("Cases:", len(selected))
    print("AI enabled: No")
    print("Output:", output_path)

    # --------------------------------------------------
    # 6. Evaluate each synthetic case
    # --------------------------------------------------

    for index, case in enumerate(selected, start=1):

        # Run the current OCR-only reconciliation engine
        # using the original isolated-case procedure.
        result = runner.evaluate_case(case)

        # Retrieve frozen baseline results for comparison.
        previous = baseline[case["case_id"]]

        # --------------------------------------------------
        # Identify intentional HL7 name conflicts
        # --------------------------------------------------
        # Ground truth is used ONLY for evaluation.
        # It is not provided to the reconciliation engine.

        from docurecon.reconciliation.identity_validation import (
            normalize_name,
        )

        truth_name = normalize_name(
            case["patient_name"]
        )

        hl7_name = normalize_name(
            case["hl7_patient_name"]
        )

        intentional_conflict = bool(
            truth_name
            and hl7_name
            and truth_name != hl7_name
        )

        # --------------------------------------------------
        # Check whether the engine flagged the conflict
        # --------------------------------------------------

        flagged = has_issue(
            result["issues"],
            FLAG,
        )

        # --------------------------------------------------
        # Check HL7 candidate correctness
        # --------------------------------------------------

        expected_ids = split_ids(
            case["expected_hl7_control_ids"]
        )

        chosen_control = (
            result["control_id"] or ""
        ).strip()

        correct_candidate = bool(
            chosen_control
            and chosen_control in expected_ids
        )

        # --------------------------------------------------
        # 7. Update evaluation summary
        # --------------------------------------------------

        summary["processed"] += 1

        if result["runner_error"]:
            summary["runner_errors"] += 1

        if intentional_conflict:
            summary["intentional_conflicts"] += 1

            if flagged:
                summary["conflicts_flagged"] += 1

            if correct_candidate:
                summary["conflicts_correctly_linked"] += 1

        elif flagged:
            summary["other_name_disagreement_flags"] += 1

        # --------------------------------------------------
        # 8. Preserve complete case-level results
        # --------------------------------------------------

        output.append({
            **result,

            "intentional_name_conflict": (
                intentional_conflict
            ),

            "expected_hl7_control_ids": (
                case["expected_hl7_control_ids"]
            ),

            "correct_candidate_selected": (
                correct_candidate
            ),

            "name_disagreement_flagged": (
                flagged
            ),

            "baseline_match_method": (
                previous["match_method"]
            ),

            "baseline_control_id": (
                previous["control_id"]
            ),

            "baseline_issues": (
                previous["issues"]
            ),

            "baseline_status": (
                previous["status"]
            ),
        })

        if (
            index % 25 == 0
            or index == len(selected)
        ):
            print(
                f"Processed {index}/{len(selected)}"
            )

    # --------------------------------------------------
    # 9. Save retrospective results
    # --------------------------------------------------

    RESULTS.mkdir(
        parents=True,
        exist_ok=True,
    )

    fieldnames = list(output[0].keys())

    # Exclusive creation mode "x" prevents overwriting
    # any existing research evaluation results.
    with output_path.open(
        "x",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(output)

    # --------------------------------------------------
    # 10. Print evaluation summary
    # --------------------------------------------------

    print("\nRESULTS")
    print("=" * 70)

    for key, value in summary.items():
        print(f"{key}: {value}")

    print("\nResults saved:", output_path)


if __name__ == "__main__":
    main()
