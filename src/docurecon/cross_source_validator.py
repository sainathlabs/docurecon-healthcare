
"""
DocuRecon - Cross-Source Validation v1

Research-only reconciliation of synthetic:
- Tesseract OCR predictions
- OpenAI Vision predictions
- HL7 ADT messages

Does not access ground truth.
Does not automatically overwrite conflicting fields.
"""

import csv
from datetime import datetime
from pathlib import Path

from experiments.normalize_fields import normalize_field
from src.docurecon.parsers.hl7_parser import parse_hl7_folder

from src.docurecon.legal_status_resolver import resolve_legal_status


ROOT = Path(__file__).resolve().parents[2]

OCR_CSV = ROOT / "results" / "ocr_baseline.csv"
AI_CSV = ROOT / "ai_benchmark_results.csv"
HL7_DIR = ROOT / "sample_data" / "hl7"

OUTPUT = ROOT / "results" / "cross_source_validation.csv"


def read_predictions(path):
    with path.open(
        "r", newline="", encoding="utf-8-sig"
    ) as file:
        records = list(csv.DictReader(file))

    indexed = {}

    for record in records:
        source = record["source"]

        if source in indexed:
            raise ValueError(f"Duplicate source: {source}")

        indexed[source] = record

    return indexed


def normalise_patient_name(value):
    if not value:
        return None

    # HL7 PID-5: FAMILY^GIVEN
    text = str(value).strip()

    if "^" in text:
        parts = text.split("^")
        family = parts[0].strip()
        given = parts[1].strip() if len(parts) > 1 else ""
        text = f"{family}, {given}"

    return normalize_field("patient_name", text)


def timestamp(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def validate_record(source, ocr, ai, hl7_messages):

    ocr_name = normalise_patient_name(
        ocr.get("patient_name")
    )

    ai_name = normalise_patient_name(
        ai.get("patient_name")
    )

    status_result = resolve_legal_status(ocr, ai)
    resolved_status = status_result["legal_status"]

    issues = []

    result = {
        "document": source,
        "patient_name": "",
        "legal_status": "",
        "hl7_control_id": "",
        "ocr_mrn": ocr.get("mrn", ""),
        "ai_mrn": ai.get("mrn", ""),
        "hl7_mrn": "",
        "mrn_validation": "NOT_EVALUATED",
        "paperwork_completion": "",
        "hl7_completion": "",
        "message_timestamp": "",
        "timestamp_validation": "NOT_EVALUATED",
        "link_status": "UNRESOLVED",
        "issues": "",
    }

    # Never link solely by filename or MRN.
    # Require consistent name and legal status
    # from both document extraction methods.

    if not ocr_name or ocr_name != ai_name:
        issues.append("DOCUMENT_NAME_DISAGREEMENT")

    if not resolved_status:
        issues.append("DOCUMENT_STATUS_UNRESOLVED")

    if issues:
        result["issues"] = ";".join(issues)
        return result

    result["patient_name"] = ocr_name
    result["legal_status"] = resolved_status

    candidates = [
        msg for msg in hl7_messages
        if (
            normalise_patient_name(
                msg.get("patient_name")
            ) == ocr_name
            and msg.get("legal_status") == resolved_status
        )
    ]

    if len(candidates) == 0:
        result["link_status"] = "NO_HL7_MATCH"
        result["issues"] = "NO_UNIQUE_HL7_MATCH"
        return result

    if len(candidates) > 1:
        result["link_status"] = "AMBIGUOUS"
        result["issues"] = "MULTIPLE_HL7_CANDIDATES"
        return result

    hl7 = candidates[0]

    result["link_status"] = "CANDIDATE_MATCH"
    result["hl7_control_id"] = hl7["control_id"]

    # Compare three MRN sources.
    ocr_mrn = normalize_field(
        "mrn", ocr.get("mrn")
    )

    ai_mrn = normalize_field(
        "mrn", ai.get("mrn")
    )

    hl7_mrn = normalize_field(
        "mrn", hl7.get("patient_id")
    )

    result["hl7_mrn"] = hl7_mrn or ""

    if not all([ocr_mrn, ai_mrn, hl7_mrn]):
        result["mrn_validation"] = "INCOMPLETE_EVIDENCE"
        issues.append("MISSING_MRN")

    elif ocr_mrn == ai_mrn == hl7_mrn:
        result["mrn_validation"] = "ALL_SOURCES_AGREE"

    elif ai_mrn == hl7_mrn:
        result["mrn_validation"] = "AI_HL7_AGREE_OCR_DIFFERS"
        issues.append("OCR_MRN_DISAGREEMENT")

    elif ocr_mrn == hl7_mrn:
        result["mrn_validation"] = "OCR_HL7_AGREE_AI_DIFFERS"
        issues.append("AI_MRN_DISAGREEMENT")

    else:
        result["mrn_validation"] = "MRN_CONFLICT"
        issues.append("MRN_CONFLICT")

    # Compare completion timestamps only if
    # OCR and AI agree on both date and time.
    ocr_date = normalize_field(
        "completion_date",
        ocr.get("completion_date")
    )

    ai_date = normalize_field(
        "completion_date",
        ai.get("completion_date")
    )

    ocr_time = normalize_field(
        "completion_time",
        ocr.get("completion_time")
    )

    ai_time = normalize_field(
        "completion_time",
        ai.get("completion_time")
    )

    hl7_completion = timestamp(
        hl7.get("completion_timestamp")
    )

    message_time = timestamp(
        hl7.get("transmitted_at")
    )

    result["hl7_completion"] = (
        hl7.get("completion_timestamp") or ""
    )
    result["message_timestamp"] = (
        hl7.get("transmitted_at") or ""
    )

    if (
        ocr_date
        and ai_date
        and ocr_time
        and ai_time
        and ocr_date == ai_date
        and ocr_time == ai_time
    ):
        paperwork_completion = timestamp(
            f"{ocr_date}T{ocr_time}"
        )
    else:
        paperwork_completion = None
        issues.append("PAPERWORK_TIMESTAMP_UNRESOLVED")

    if paperwork_completion:
        result["paperwork_completion"] = (
            paperwork_completion.isoformat(
                timespec="minutes"
            )
        )

    if not paperwork_completion or not hl7_completion:
        result["timestamp_validation"] = "INCOMPLETE_EVIDENCE"

    elif paperwork_completion == hl7_completion:
        result["timestamp_validation"] = "COMPLETION_TIMES_AGREE"

    else:
        result["timestamp_validation"] = "COMPLETION_MISMATCH"
        issues.append("COMPLETION_TIMESTAMP_MISMATCH")

    # MSH-7 is a message timestamp.
    # It is not independent proof of transmission.
    if (
        message_time is not None
        and paperwork_completion is not None
        and message_time < paperwork_completion
    ):
        issues.append(
            "MESSAGE_TIMESTAMP_BEFORE_COMPLETION"
        )

    result["issues"] = ";".join(issues)

    return result


def main():
    ocr_records = read_predictions(OCR_CSV)
    ai_records = read_predictions(AI_CSV)

    hl7_messages, hl7_errors = parse_hl7_folder(
        HL7_DIR
    )

    if hl7_errors:
        raise ValueError(
            f"HL7 parsing errors: {hl7_errors}"
        )

    rows = []

    for source in sorted(
        set(ocr_records) | set(ai_records)
    ):
        if (
            source not in ocr_records
            or source not in ai_records
        ):
            print(f"Missing extractor output: {source}")
            continue

        rows.append(
            validate_record(
                source,
                ocr_records[source],
                ai_records[source],
                hl7_messages,
            )
        )

    OUTPUT.parent.mkdir(
        parents=True, exist_ok=True
    )

    if not rows:
        print("No records available for validation.")
        return

    with OUTPUT.open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file, fieldnames=list(rows[0].keys())
        )
        writer.writeheader()
        writer.writerows(rows)

    print("\nDocuRecon Cross-Source Validation")
    print("=" * 50)

    for row in rows:
        print(f"\nDocument: {row['document']}")
        print(f"Link status: {row['link_status']}")
        print(f"MRN: {row['mrn_validation']}")
        print(f"Timestamp: {row['timestamp_validation']}")
        print(f"Issues: {row['issues'] or 'None'}")

    print(f"\nResults saved to: {OUTPUT}")


if __name__ == "__main__":
    main()
