
"""
DocuRecon: 10-case end-to-end reconciliation pilot.

Uses fresh OCR, HL7 and ACK parsing.
AI disabled.
Does not modify input files or ground truth.
"""

import csv
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "src"))

from docurecon.reconciliation.daily_engine import run_daily


ROOT = PROJECT / "evaluation_dataset" / "pilot_form_based"

OUTPUT = (
    PROJECT / "evaluation_dataset"
    / "pilot" / "reconciliation_results.csv"
)

START = date(2026, 11, 16)


def main():
    all_rows = []
    error_count = 0

    print("\nDOCURECON END-TO-END PILOT")
    print("=" * 65)

    for index in range(10):
        day = START + timedelta(days=index)

        result = run_daily(
            ROOT,
            day,
            use_ai=False,
        )

        error_count += len(result["parse_errors"])

        # Exclude undated paperwork diagnostic rows
        # when counting records for a selected day.
        selected_rows = [
            row for row in result["rows"]
            if row.get("completion_date") == day.isoformat()
        ]

        print(f"\nCASE {index + 1:03d} | {day}")

        if len(selected_rows) != 1:
            print(
                "WARNING: Expected one dated paperwork row, "
                f"found {len(selected_rows)}"
            )

        for row in selected_rows:
            row = dict(row)
            row["evaluation_date"] = day.isoformat()
            all_rows.append(row)

            print("Patient:", row.get("patient_name"))
            print("MRN:", row.get("ocr_mrn"))
            print("Match:", row.get("match_method"))
            print("HL7:", row.get("control_id"))
            print("ACK:", row.get("ack_status"))
            print("Status:", row.get("status"))
            print("Issues:", row.get("issues"))
            print(
                "Uncertainty:",
                row.get("uncertainty_reasons")
            )

    print("\n" + "=" * 65)
    print("SUMMARY")

    counts = Counter(
        row["status"] for row in all_rows
    )

    print("Paperwork rows:", len(all_rows))
    print("Parse errors across runs:", error_count)

    for status, count in sorted(counts.items()):
        print(f"{status}: {count}")

    if all_rows:
        OUTPUT.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        # Prevent accidental overwrite.
        if OUTPUT.exists():
            raise FileExistsError(
                f"Report already exists: {OUTPUT}"
            )

        fieldnames = list(
            dict.fromkeys(
                key
                for row in all_rows
                for key in row
            )
        )

        with OUTPUT.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=fieldnames,
            )
            writer.writeheader()
            writer.writerows(all_rows)

        print("\nSaved:", OUTPUT)


if __name__ == "__main__":
    main()
