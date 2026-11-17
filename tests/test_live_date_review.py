
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from docurecon.reconciliation.daily_engine import (
    run_daily,
)


ROOT = (
    Path(__file__).resolve().parents[1]
    / "sample_data"
)

DAY = date(2028, 3, 21)


def make_paper(source, completion_date):
    return {
        "source": source,
        "patient_name": "TEST, PATIENT",
        "mrn": "SYN-002-021",
        "form_type": "9.37",
        "completion_date": completion_date,
        "completion_time": "08:00",
        "review_reasons": [],
    }


def run_mock(papers, *, limit, extractor):
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
        patch(
            "docurecon.ai.document_extractor.extract_document",
            side_effect=extractor,
        ) as mocked_ai,
    ):
        result = run_daily(
            ROOT,
            DAY,
            review_excluded_dates_with_ai=True,
            max_date_review_ai_calls=limit,
        )

        return result, mocked_ai.call_count


def test_live_ai_recovers_missing_date_candidate():
    papers = [
        make_paper(
            "DocuRecon_SYNTHETIC_A.pdf", ""
        )
    ]

    result, calls = run_mock(
        papers,
        limit=1,
        extractor=lambda path: {
            "extracted_fields": {
                "completion_date": "2028-03-21"
            }
        },
    )

    assert calls == 1
    assert result["date_review_ai_calls"] == 1
    assert result["paperwork_count"] == 0

    review = result["date_review_queue"][0]

    assert review["classification"] == (
        "OCR_DATE_MISSING_AI_CANDIDATE"
    )
    assert review["included_in_daily"] is False


def test_live_ai_identifies_wrong_ocr_date():
    papers = [
        make_paper(
            "DocuRecon_SYNTHETIC_B.pdf",
            "2028-03-22",
        )
    ]

    result, calls = run_mock(
        papers,
        limit=1,
        extractor=lambda path: {
            "extracted_fields": {
                "completion_date": "2028-03-21"
            }
        },
    )

    assert calls == 1
    assert result["paperwork_count"] == 0
    assert result["rows"] == []

    review = result["date_review_queue"][0]

    assert review["classification"] == (
        "OCR_OTHER_DATE_AI_CANDIDATE"
    )


def test_live_ai_respects_call_limit():
    papers = [
        make_paper(
            f"DocuRecon_SYNTHETIC_{i}.pdf", ""
        )
        for i in range(3)
    ]

    result, calls = run_mock(
        papers,
        limit=1,
        extractor=lambda path: {
            "extracted_fields": {
                "completion_date": "2028-03-21"
            }
        },
    )

    assert calls == 1
    assert result["date_review_ai_calls"] == 1


def test_live_ai_failure_is_recorded():
    papers = [
        make_paper(
            "DocuRecon_SYNTHETIC_ERROR.pdf",
            "",
        )
    ]

    def failing_extractor(path):
        raise RuntimeError("Synthetic test failure")

    result, calls = run_mock(
        papers,
        limit=1,
        extractor=failing_extractor,
    )

    assert calls == 1
    assert len(result["date_review_ai_errors"]) == 1
    assert result["date_review_ai_errors"][0][
        "error_type"
    ] == "RuntimeError"

    assert result["date_review_queue"][0][
        "ai_supported_candidate"
    ] is False


def test_live_ai_requires_positive_limit():
    with pytest.raises(ValueError):
        run_daily(
            ROOT,
            DAY,
            review_excluded_dates_with_ai=True,
            max_date_review_ai_calls=0,
        )
