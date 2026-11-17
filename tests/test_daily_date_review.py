
from datetime import date
from pathlib import Path
from unittest.mock import patch

from docurecon.reconciliation.daily_engine import run_daily


ROOT = Path(__file__).resolve().parents[1] / "sample_data"
DAY = date(2028, 3, 21)


def make_paper(ocr_date):
    return {
        "source": "DocuRecon_SYNTHETIC_TEST.pdf",
        "patient_name": "TEST, PATIENT",
        "mrn": "SYN-002-021",
        "form_type": "9.37",
        "completion_date": ocr_date,
        "completion_time": "08:00",
        "review_reasons": [
            "OCR_VALUES_REQUIRE_HUMAN_VERIFICATION"
        ],
    }


def run_case(ocr_date, ai_date=None):
    papers = [make_paper(ocr_date)]

    evidence = (
        {
            papers[0]["source"]: {
                "completion_date": ai_date
            }
        }
        if ai_date is not None
        else None
    )

    with (
        patch(
            "docurecon.reconciliation.daily_engine.extract_folder",
            return_value=(papers, []),
        ),
        patch(
            "docurecon.reconciliation.daily_engine.parse_hl7_folder",
            return_value=([], []),
        ),
        patch(
            "docurecon.reconciliation.daily_engine.parse_ack_folder",
            return_value=([], []),
        ),
    ):
        return run_daily(
            ROOT,
            DAY,
            date_ai_evidence=evidence,
        )


def test_missing_ocr_date_creates_review_candidate():
    result = run_case("", "2028-03-21")

    assert result["paperwork_count"] == 0
    assert len(result["date_review_queue"]) == 1

    review = result["date_review_queue"][0]

    assert review["classification"] == (
        "OCR_DATE_MISSING_AI_CANDIDATE"
    )
    assert review["ai_supported_candidate"] is True
    assert review["included_in_daily"] is False

    # Existing uncertain-row behaviour remains.
    assert len(result["rows"]) == 1
    assert result["rows"][0]["status"] == "OCR_UNCERTAIN"


def test_incorrect_ocr_date_creates_review_candidate():
    result = run_case(
        "2028-03-22",
        "2028-03-21",
    )

    assert result["paperwork_count"] == 0
    assert result["rows"] == []

    review = result["date_review_queue"][0]

    assert review["classification"] == (
        "OCR_OTHER_DATE_AI_CANDIDATE"
    )
    assert review["ocr_date"] == "2028-03-22"
    assert review["ai_date"] == "2028-03-21"
    assert review["included_in_daily"] is False


def test_ocr_only_other_date_remains_excluded():
    result = run_case("2028-03-22")

    assert result["paperwork_count"] == 0
    assert result["rows"] == []
    assert result["date_review_queue"] == []


def test_matching_date_does_not_require_date_review():
    result = run_case(
        "2028-03-21",
        "2028-03-21",
    )

    assert result["paperwork_count"] == 1
    assert result["date_review_queue"] == []
