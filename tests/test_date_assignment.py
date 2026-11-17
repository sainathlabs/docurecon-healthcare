
import pytest

from docurecon.reconciliation.date_assignment import (
    assess_date_assignment,
)

DAY = "2028-03-21"
OTHER = "2028-03-22"


@pytest.mark.parametrize(
    "ocr,ai,attempted,classification,include,review",
    [
        (
            DAY, "", False,
            "OCR_DATE_MATCH", True, False,
        ),
        (
            "", "", False,
            "OCR_DATE_MISSING", False, True,
        ),
        (
            OTHER, "", False,
            "OCR_OTHER_DATE", False, False,
        ),
        (
            DAY, DAY, True,
            "DATE_AGREEMENT", True, False,
        ),
        (
            "", DAY, True,
            "OCR_DATE_MISSING_AI_CANDIDATE",
            False, True,
        ),
        (
            OTHER, DAY, True,
            "OCR_OTHER_DATE_AI_CANDIDATE",
            False, True,
        ),
        (
            DAY, OTHER, True,
            "DATE_CONFLICT", True, True,
        ),
        (
            DAY, "", True,
            "AI_DATE_MISSING", True, True,
        ),
        (
            "", "", True,
            "BOTH_DATES_MISSING", False, True,
        ),
        (
            OTHER, OTHER, True,
            "AGREED_OTHER_DATE", False, False,
        ),
        (
            OTHER, "", True,
            "AI_DATE_MISSING", False, True,
        ),
        (
            OTHER, "2028-03-23", True,
            "DATE_CONFLICT_OTHER_DATE", False, True,
        ),
    ],
)
def test_date_assignment(
    ocr, ai, attempted,
    classification, include, review,
):
    result = assess_date_assignment(
        ocr, ai, DAY,
        ai_attempted=attempted,
    )

    assert result["classification"] == classification
    assert result["include_in_daily"] is include
    assert result["review_required"] is review

    assert result["ai_supported_candidate"] is (
        attempted and ai == DAY and ocr != DAY
    )


def test_ai_candidate_does_not_override_ocr_date():
    result = assess_date_assignment(
        OTHER, DAY, DAY,
        ai_attempted=True,
    )

    assert result["ocr_date"] == OTHER
    assert result["ai_date"] == DAY
    assert result["include_in_daily"] is False
    assert result["review_required"] is True
