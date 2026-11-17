
"""
DocuRecon - Hybrid Date Assignment

Classifies OCR and AI date evidence for review.

Never uses AI to verify legal completion.
Never silently overrides OCR dates.
No API calls or ground-truth access.
"""

from datetime import date


def _date_value(value):
    if isinstance(value, date):
        return value.isoformat()
    return str(value or "").strip()


def assess_date_assignment(
    ocr_date,
    ai_date,
    selected_date,
    *,
    ai_attempted=False,
):
    """
    Assess evidence for a selected reporting date.

    Returns a classification and routing decision.
    """
    ocr = _date_value(ocr_date)
    ai = _date_value(ai_date)
    selected = _date_value(selected_date)

    # Preserve the established OCR-only path.
    if not ai_attempted:
        return {
            "classification": (
                "OCR_DATE_MATCH"
                if ocr == selected
                else "OCR_DATE_MISSING"
                if not ocr
                else "OCR_OTHER_DATE"
            ),
            "include_in_daily": ocr == selected,
            "review_required": not bool(ocr),
            "ai_supported_candidate": False,
            "ocr_date": ocr,
            "ai_date": "",
        }

    if ocr == selected and ai == selected:
        classification = "DATE_AGREEMENT"
        include = True
        review = False

    elif ocr == selected:
        classification = (
            "AI_DATE_MISSING"
            if not ai
            else "DATE_CONFLICT"
        )
        include = True
        review = True

    elif ai == selected:
        classification = (
            "OCR_DATE_MISSING_AI_CANDIDATE"
            if not ocr
            else "OCR_OTHER_DATE_AI_CANDIDATE"
        )
        include = False
        review = True

    elif not ocr and not ai:
        classification = "BOTH_DATES_MISSING"
        include = False
        review = True

    elif not ocr:
        classification = "OCR_DATE_MISSING"
        include = False
        review = True

    elif not ai:
        classification = "AI_DATE_MISSING"
        include = False
        review = True

    elif ocr == ai:
        classification = "AGREED_OTHER_DATE"
        include = False
        review = False

    else:
        classification = "DATE_CONFLICT_OTHER_DATE"
        include = False
        review = True

    return {
        "classification": classification,
        "include_in_daily": include,
        "review_required": review,
        "ai_supported_candidate": (
            ai == selected and ocr != selected
        ),
        "ocr_date": ocr,
        "ai_date": ai,
    }
