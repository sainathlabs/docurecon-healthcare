
"""
DocuRecon - Legal Status Resolver

Research-only classifier for the current
synthetic OMH document profiles.

Combines explicit legal-status extraction
with supporting form-type evidence.

Does not establish legal admission validity.
"""

import re

from experiments.normalize_fields import (
    normalize_legal_status,
)



def status_from_form_type(form_type):
    """
    Extract legal status from explicit references
    or supported OMH form numbers.

    Conflicting evidence is not resolved automatically.
    """
    if not form_type:
        return None

    text = str(form_type).upper()
    statuses = set()

    # Explicit Mental Hygiene Law references.
    explicit_matches = re.findall(
        r"(?<![\d.])9\s*\.\s*(37|39)(?!\d)",
        text,
    )

    for value in explicit_matches:
        statuses.add(f"9.{value}")

    # Supported OMH form numbers.
    numbers = re.findall(
        r"\b(?:OMH\s*(?:FORM\s*)?)?"
        r"(474|475A?)\b",
        text,
    )

    for number in numbers:
        if number == "474":
            statuses.add("9.39")
        elif number in ("475", "475A"):
            statuses.add("9.37")

    if len(statuses) == 1:
        return next(iter(statuses))

    return None



def resolve_legal_status(ocr_record, ai_record):
    """
    Compare OCR status with AI status/form evidence.

    Never use filenames or ground-truth values.
    """

    ocr_status = normalize_legal_status(
        ocr_record.get("legal_status")
    )

    ai_status = normalize_legal_status(
        ai_record.get("legal_status")
    )

    ai_form_status = status_from_form_type(
        ai_record.get("form_type")
    )

    evidence = {
        "ocr_explicit_status": ocr_status,
        "ai_explicit_status": ai_status,
        "ai_form_status": ai_form_status,
    }

    values = [
        value for value in evidence.values()
        if value is not None
    ]

    if not values:
        return {
            "legal_status": None,
            "resolution": "UNRESOLVED",
            "reason": "No unambiguous status evidence",
            "evidence": evidence,
        }

    if len(set(values)) > 1:
        return {
            "legal_status": None,
            "resolution": "CONFLICT",
            "reason": "Conflicting legal-status evidence",
            "evidence": evidence,
        }

    resolved = values[0]

    if ocr_status and ai_status:
        resolution = "EXPLICIT_AGREEMENT"

    elif ocr_status and ai_form_status:
        resolution = "OCR_AND_FORM_AGREE"

    else:
        resolution = "SINGLE_SOURCE_EVIDENCE"

    return {
        "legal_status": resolved,
        "resolution": resolution,
        "reason": (
            "Consistent status evidence from "
            "available extraction fields"
        ),
        "evidence": evidence,
    }
