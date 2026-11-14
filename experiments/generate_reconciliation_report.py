
"""
DocuRecon - Combined Reconciliation Report

Combines:
1. Paperwork-to-HL7 validation results
2. HL7-to-ACK/NACK reconciliation results

Synthetic research dataset only.
No OpenAI API calls.
"""

import csv
from pathlib import Path

from src.docurecon.parsers.hl7_parser import (
    parse_hl7_folder,
)
from src.docurecon.parsers.ack_parser import (
    parse_ack_folder,
    link_acknowledgements,
)


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"

VALIDATION_CSV = (
    RESULTS / "cross_source_validation.csv"
)

HL7_FOLDER = ROOT / "sample_data" / "hl7"
ACK_FOLDER = (
    ROOT / "sample_data" / "acknowledgements"
)

OUTPUT = RESULTS / "combined_reconciliation.csv"


def read_csv(path):
    if not path.exists():
        raise FileNotFoundError(path)

    with path.open(
        "r", newline="", encoding="utf-8-sig"
    ) as file:
        return list(csv.DictReader(file))


def main():
    paperwork = read_csv(VALIDATION_CSV)

    messages, message_errors = parse_hl7_folder(
        HL7_FOLDER
    )

    acks, ack_errors = parse_ack_folder(
        ACK_FOLDER
    )

    if message_errors or ack_errors:
        raise ValueError(
            f"HL7 errors: {message_errors}; "
            f"ACK errors: {ack_errors}"
        )

    ack_results = link_acknowledgements(
        messages, acks
    )

    ack_lookup = {
        row["outbound_control_id"]: row
        for row in ack_results
        if row["outbound_file"]
    }

    report = []
    linked_control_ids = set()

    # Paperwork records
    for paper in paperwork:
        control_id = paper.get(
            "hl7_control_id", ""
        )

        ack = ack_lookup.get(control_id, {})

        if control_id:
            linked_control_ids.add(control_id)

        issues = [
            value for value in
            paper.get("issues", "").split(";")
            if value
        ]

        if not control_id:
            issues.append("HL7_LINK_NOT_ESTABLISHED")

        if ack:
            ack_status = ack["link_status"]

            if ack_status != "ACCEPTED":
                issues.append(
                    f"ACK_{ack_status}"
                )
        else:
            ack_status = "NOT_LINKED"

        report.append({
            "record_type": "PAPERWORK",
            "document": paper["document"],
            "patient_name": paper.get(
                "patient_name", ""
            ),
            "legal_status": paper.get(
                "legal_status", ""
            ),
            "hl7_control_id": control_id,
            "hl7_link_status": paper.get(
                "link_status", ""
            ),
            "mrn_validation": paper.get(
                "mrn_validation", ""
            ),
            "timestamp_validation": paper.get(
                "timestamp_validation", ""
            ),
            "ack_status": ack_status,
            "issues": ";".join(
                dict.fromkeys(issues)
            ),
        })

    # Preserve messages that could not be
    # linked to any paperwork record.
    for message in messages:
        control_id = message["control_id"]

        if control_id in linked_control_ids:
            continue

        ack = ack_lookup.get(control_id, {})

        report.append({
            "record_type": "UNLINKED_HL7",
            "document": "",
            "patient_name": message.get(
                "patient_name", ""
            ),
            "legal_status": message.get(
                "legal_status", ""
            ),
            "hl7_control_id": control_id,
            "hl7_link_status": (
                "NO_PAPERWORK_LINK"
            ),
            "mrn_validation": "NOT_EVALUATED",
            "timestamp_validation": (
                "NOT_EVALUATED"
            ),
            "ack_status": ack.get(
                "link_status", "NOT_EVALUATED"
            ),
            "issues": "UNLINKED_HL7_MESSAGE",
        })

    # Preserve acknowledgements whose outbound
    # message was not supplied.
    for ack in ack_results:
        if (
            ack["link_status"]
            != "ORPHAN_ACK_NO_OUTBOUND_MESSAGE"
        ):
            continue

        report.append({
            "record_type": "ORPHAN_ACK",
            "document": "",
            "patient_name": "",
            "legal_status": "",
            "hl7_control_id": ack[
                "outbound_control_id"
            ],
            "hl7_link_status": "NO_OUTBOUND",
            "mrn_validation": "NOT_EVALUATED",
            "timestamp_validation": (
                "NOT_EVALUATED"
            ),
            "ack_status": ack["link_status"],
            "issues": "ORPHAN_ACK",
        })

    OUTPUT.parent.mkdir(
        parents=True, exist_ok=True
    )

    columns = [
        "record_type",
        "document",
        "patient_name",
        "legal_status",
        "hl7_control_id",
        "hl7_link_status",
        "mrn_validation",
        "timestamp_validation",
        "ack_status",
        "issues",
    ]

    with OUTPUT.open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file, fieldnames=columns
        )
        writer.writeheader()
        writer.writerows(report)

    print("\nDocuRecon Combined Reconciliation")
    print("=" * 50)

    for row in report:
        print(
            f"\n{row['record_type']}: "
            f"{row['document'] or row['hl7_control_id']}"
        )
        print(
            f"HL7 link: {row['hl7_link_status']}"
        )
        print(
            f"ACK: {row['ack_status']}"
        )
        print(
            f"Issues: {row['issues'] or 'None'}"
        )

    print(f"\nTotal report rows: {len(report)}")
    print(f"Saved to: {OUTPUT}")


if __name__ == "__main__":
    main()
