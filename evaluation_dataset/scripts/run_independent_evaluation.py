
"""
DocuRecon independent evaluation runner.

Runs the frozen reconciliation engine on synthetic cases.
Does not supply ground truth fields to the engine.
Does not modify source files or the frozen pipeline.
"""

import argparse
import csv
import json
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[2]

# Add both the project root and src to Python's import path.
# Required for imports from experiments and docurecon.
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "src"))

from docurecon.reconciliation.daily_engine import run_daily



ROOT = PROJECT / "evaluation_dataset" / "independent_test"

GROUND_TRUTH = (
    ROOT / "ground_truth" / "case_ground_truth.csv"
)

RESULT_DIR = ROOT / "results"

FROZEN_COMMIT = "2a3ebdd"

FIELDS = [
    "case_id",
    "document",
    "evaluation_date",
    "status",
    "patient_name",
    "ocr_mrn",
    "match_method",
    "control_id",
    "ack_status",
    "issues",
    "uncertainty_reasons",
    "completion_date",
    "completion_time",
    "parse_errors",
    "row_count",
    "processing_seconds",
    "raw_result_json",
    "runner_error",
]


def check_pipeline():
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT,
        text=True,
    ).strip()

    frozen = subprocess.check_output(
        ["git", "rev-parse", FROZEN_COMMIT],
        cwd=PROJECT,
        text=True,
    ).strip()

    if commit != frozen:
        raise RuntimeError(
            "HEAD is not the frozen v0.3.0-pilot commit. "
            "Do not run the independent test using "
            "modified application code."
        )

    changed = subprocess.check_output(
        [
            "git", "diff", "--name-only", "HEAD",
            "--", "src/docurecon"
        ],
        cwd=PROJECT,
        text=True,
    ).strip()

    if changed:
        raise RuntimeError(
            "Application source files have uncommitted changes:\n"
            + changed
        )


def load_cases():
    with GROUND_TRUTH.open(
        newline="", encoding="utf-8-sig"
    ) as file:
        cases = list(csv.DictReader(file))

    if len(cases) != 400:
        raise ValueError(
            f"Expected 400 cases, found {len(cases)}"
        )

    return cases


def copy_case_files(case, workspace):
    for folder in [
        "paperwork",
        "hl7",
        "acknowledgements",
    ]:
        (workspace / folder).mkdir()

    document = ROOT / "paperwork" / case["document"]

    if not document.is_file():
        raise FileNotFoundError(document)

    shutil.copy2(document, workspace / "paperwork")

    prefix = f"TEST-{case['case_id']}-"

    for folder, extension in [
        ("hl7", "*.hl7"),
        ("acknowledgements", "*.ack"),
    ]:
        for source in (ROOT / folder).glob(extension):
            if source.name.startswith(prefix):
                shutil.copy2(
                    source,
                    workspace / folder,
                )


def evaluate_case(case):
    started = time.perf_counter()

    output = {
        field: "" for field in FIELDS
    }

    output["case_id"] = case["case_id"]
    output["document"] = case["document"]
    output["evaluation_date"] = case["completion_date"]

    try:
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)

            copy_case_files(case, workspace)

            result = run_daily(
                workspace,
                date.fromisoformat(
                    case["completion_date"]
                ),
                use_ai=False,
            )

        rows = result.get("rows", [])
        errors = result.get("parse_errors", [])

        output["row_count"] = len(rows)
        output["parse_errors"] = json.dumps(
            errors, default=str
        )

        # Preserve all returned rows, including unexpected
        # extra or undated rows.
        output["raw_result_json"] = json.dumps(
            rows, default=str, ensure_ascii=False
        )

        if len(rows) == 1:
            row = rows[0]

            for field in [
                "status",
                "patient_name",
                "ocr_mrn",
                "match_method",
                "control_id",
                "ack_status",
                "issues",
                "uncertainty_reasons",
                "completion_date",
                "completion_time",
            ]:
                output[field] = str(
                    row.get(field, "") or ""
                )

        elif len(rows) != 1:
            output["runner_error"] = (
                f"Expected one reconciliation row, "
                f"received {len(rows)}"
            )

    except Exception as exc:
        output["runner_error"] = (
            f"{type(exc).__name__}: {exc}"
        )

    output["processing_seconds"] = round(
        time.perf_counter() - started, 3
    )

    return output


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Number of cases to process",
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Evaluate all 400 cases",
    )

    args = parser.parse_args()

    check_pipeline()
    cases = load_cases()

    if args.all:
        selected = cases
        output_file = (
            RESULT_DIR / "independent_results_400.csv"
        )
    else:
        if not 1 <= args.limit <= 400:
            raise ValueError(
                "--limit must be between 1 and 400"
            )
        selected = cases[:args.limit]
        output_file = (
            RESULT_DIR
            / f"integration_results_{args.limit}.csv"
        )

    RESULT_DIR.mkdir(
        parents=True, exist_ok=True
    )

    if output_file.exists():
        raise FileExistsError(
            f"Results already exist: {output_file}"
        )

    print("\nDOCURECON INDEPENDENT EVALUATION")
    print("=" * 65)
    print("Frozen commit:", FROZEN_COMMIT)
    print("Cases:", len(selected))
    print("AI enabled: False")
    print("Output:", output_file)
    print("=" * 65, flush=True)

    # Write after each case so interrupted experiments
    # retain their completed observations.
    with output_file.open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=FIELDS,
        )

        writer.writeheader()

        for index, case in enumerate(
            selected, start=1
        ):
            result = evaluate_case(case)

            writer.writerow(result)
            file.flush()

            print(
                f"{index}/{len(selected)} "
                f"Case {result['case_id']} | "
                f"{result['status'] or 'NO_STATUS'} | "
                f"{result['processing_seconds']}s"
                + (
                    f" | ERROR: {result['runner_error']}"
                    if result["runner_error"]
                    else ""
                ),
                flush=True,
            )

    print("\nEvaluation completed.")
    print("Results saved:", output_file)


if __name__ == "__main__":
    main()
