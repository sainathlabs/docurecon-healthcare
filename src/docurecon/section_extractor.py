
"""
DocuRecon - Section-Level Extraction Adapter

Converts existing OCR predictions into structured
section-specific timestamp candidates.

This module does not verify signatures or
determine legal completeness.

Designed for current synthetic OMH layouts.
"""

from pathlib import Path

from src.docurecon.parsers.paperwork_parser import (
    extract_paperwork,
)


def structure_paperwork_result(result):
    """Convert a baseline OCR result into section data."""

    legal_status = result.get("form_type", "")

    completion_date = result.get(
        "completion_date", ""
    )

    completion_time = result.get(
        "completion_time", ""
    )

    structured = {
        "source": result.get("source", ""),
        "patient_name": result.get(
            "patient_name", ""
        ),
        "mrn": result.get("mrn", ""),
        "facility": result.get("facility", ""),
        "legal_status": legal_status,
        "sections": {
            "part_c": {},
            "physician_signatures": [],
        },
        "review_reasons": list(
            result.get("review_reasons", [])
        ),
    }

    if legal_status == "9.37":

        structured["sections"]["part_c"] = {
            "date": completion_date,
            "time": completion_time,
            "source_page": 2,
            "source_section": (
                "Part C - Physician Confirmation"
            ),
            "signature_present": False,
            "signature_status": "unverified",
            "extraction_method": "tesseract_ocr",
        }

    elif legal_status == "9.39":

        structured["sections"][
            "physician_signatures"
        ].append({
            "date": completion_date,
            "time": completion_time,
            "source_page": 1,
            "source_section": (
                "Physician Signature Row"
            ),
            "signature_present": False,
            "signature_status": "unverified",
            "extraction_method": "tesseract_ocr",
        })

    else:
        structured["review_reasons"].append(
            "UNSUPPORTED_LEGAL_STATUS"
        )

    return structured


def extract_sections(pdf_path):
    """
    Run the existing OCR parser and convert
    its output into section-level data.
    """

    pdf_path = Path(pdf_path)

    result = extract_paperwork(pdf_path)

    return structure_paperwork_result(result)
