
"""
DocuRecon - Daily AI Extraction Validation

Compares fresh OCR and AI extraction results.

Synthetic PDFs only.
Does not use ground truth or benchmark CSVs.
Does not determine legal completion.
"""

from pathlib import Path

from experiments.normalize_fields import normalize_field
from docurecon.ai.document_extractor import extract_document
from docurecon.legal_status_resolver import resolve_legal_status


FIELDS = (
    "patient_name",
    "mrn",
    "completion_date",
    "completion_time",
)


def validate_with_ai(ocr_result: dict, pdf_path: Path) -> dict:
    """
    Run AI on a synthetic PDF and compare with OCR.

    Disagreements are flagged, not automatically
    replaced with AI values.
    """

    pdf_path = Path(pdf_path)

    # extract_document independently enforces
    # the synthetic research folder restriction.
    ai_response = extract_document(pdf_path)
    ai_fields = ai_response["extracted_fields"]

    comparisons = {}
    issues = []

    for field in FIELDS:
        ocr_value = normalize_field(
            field, ocr_result.get(field)
        )

        ai_value = normalize_field(
            field, ai_fields.get(field)
        )

        if ocr_value and ai_value:
            status = (
                "AGREE"
                if ocr_value == ai_value
                else "DISAGREE"
            )

        elif ai_value:
            status = "AI_ONLY"

        elif ocr_value:
            status = "OCR_ONLY"

        else:
            status = "BOTH_MISSING"

        comparisons[field] = {
            "ocr": ocr_value,
            "ai": ai_value,
            "status": status,
        }

        if status != "AGREE":
            issues.append(
                f"EXTRACTION_{field.upper()}_{status}"
            )

    legal_result = resolve_legal_status(
        {
            "legal_status": ocr_result.get(
                "form_type"
            )
        },
        ai_fields,
    )

    if not legal_result["legal_status"]:
        issues.append("LEGAL_STATUS_UNRESOLVED")

    return {
        "source": pdf_path.name,
        "model": ai_response["model"],
        "legal_status": legal_result["legal_status"],
        "legal_status_resolution": legal_result[
            "resolution"
        ],
        "comparisons": comparisons,
        "issues": issues,
        "elapsed_seconds": ai_response[
            "elapsed_seconds"
        ],
    }
