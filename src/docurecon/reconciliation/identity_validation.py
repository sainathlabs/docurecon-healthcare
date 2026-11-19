
"""
DocuRecon - Patient Identity Evidence Assessment

Compares extracted patient identifiers across
OCR paperwork, AI paperwork, and HL7 messages.

Synthetic research prototype only.

Never treats a name or MRN match as independently
verified patient identity.
"""

import re


def normalize_name(value):
    """Normalise common HL7 and paperwork name formats."""
    text = str(value or "").strip().upper()

    if not text:
        return ""

    # Convert HL7 family^given into family, given.
    text = text.replace("^", ",")

    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*,\s*", ", ", text)

    return text.strip()


def normalize_mrn(value):
    """Normalise case and whitespace only."""
    return re.sub(
        r"\s+", "", str(value or "").upper()
    )


def compare_values(ocr, ai, hl7):
    """Compare values without selecting an authoritative source."""
    values = {
        "ocr": ocr,
        "ai": ai,
        "hl7": hl7,
    }

    present = {
        key: value
        for key, value in values.items()
        if value
    }

    if not present:
        status = "ALL_MISSING"

    elif len(present) == 1:
        status = "SINGLE_SOURCE"

    elif len(set(present.values())) == 1:
        status = (
            "ALL_AGREE"
            if len(present) == 3
            else "PARTIAL_AGREEMENT"
        )

    else:
        status = "CONFLICT"

    return {
        "status": status,
        "values": values,
        "review_required": status != "ALL_AGREE",
    }


def compare_pair(left_value, right_value):
    """
    Compare two already-normalised identity values.

    Does not determine which source is correct.
    """
    if left_value and right_value:
        return (
            "AGREE"
            if left_value == right_value
            else "DISAGREE"
        )

    if left_value:
        return "RIGHT_MISSING"

    if right_value:
        return "LEFT_MISSING"

    return "BOTH_MISSING"


def pairwise_identity_evidence(values):
    """
    Record source-specific identity comparisons.

    Missing evidence is not treated as a disagreement.
    """
    return {
        "ocr_vs_ai": compare_pair(
            values["ocr"], values["ai"]
        ),
        "ocr_vs_hl7": compare_pair(
            values["ocr"], values["hl7"]
        ),
        "ai_vs_hl7": compare_pair(
            values["ai"], values["hl7"]
        ),
    }


def assess_identity(
    ocr_name,
    ocr_mrn,
    ai_name,
    ai_mrn,
    hl7_name,
    hl7_mrn,
):
    """Return independent name and MRN comparisons."""
    name = compare_values(
        normalize_name(ocr_name),
        normalize_name(ai_name),
        normalize_name(hl7_name),
    )

    mrn = compare_values(
        normalize_mrn(ocr_mrn),
        normalize_mrn(ai_mrn),
        normalize_mrn(hl7_mrn),
    )


    # Pairwise evidence explains which sources
    # agree, disagree, or are unavailable.
    name["pairwise"] = pairwise_identity_evidence(
        name["values"]
    )

    mrn["pairwise"] = pairwise_identity_evidence(
        mrn["values"]
    )

    return {
        "name": name,
        "mrn": mrn,
        "identity_review_required": (
            name["review_required"]
            or mrn["review_required"]
        ),
        # Extraction agreement is not identity verification.
        "identity_verified": False,
    }
