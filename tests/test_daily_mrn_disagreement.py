
"""Regression tests for daily MRN disagreement handling."""

from datetime import date
from unittest.mock import patch

from docurecon.reconciliation.daily_engine import run_daily


def paperwork(mrn):
    return {
        "source": "synthetic_case.pdf",
        "patient_name": "HARRIS, LEENA",
        "mrn": mrn,
        "form_type": "9.37",
        "completion_date": "2026-11-20",
        "completion_time": "15:40",
        "review_reasons": [],
    }


def message(mrn):
    return {
        "source": "synthetic_case.hl7",
        "control_id": "TEST-001",
        "patient_id": mrn,
        "patient_name": "HARRIS^LEENA",
        "legal_status": "9.37",
        "completion_timestamp": "2026-11-20T15:40",
        "transmitted_at": "2026-11-20T15:50",
    }


def run_case(paper_mrn, message_mrn):
    with (
        patch(
            "docurecon.reconciliation.daily_engine.extract_folder",
            return_value=([paperwork(paper_mrn)], []),
        ),
        patch(
            "docurecon.reconciliation.daily_engine.parse_hl7_folder",
            return_value=([message(message_mrn)], []),
        ),
        patch(
            "docurecon.reconciliation.daily_engine.parse_ack_folder",
            return_value=([], []),
        ),
    ):
        return run_daily(
            ".",
            date(2026, 11, 20),
            use_ai=False,
        )["rows"][0]


def test_mrn_disagreement_detected():
    row = run_case(
        "SYN-PILOT-0005",
        "SYN-PILOT-9995",
    )

    assert row["match_method"] == "PATIENT_NAME_ONLY"
    assert row["status"] == "OCR_UNCERTAIN"
    assert "MRN_DISAGREEMENT" in row["issues"]


def test_matching_mrn_not_flagged():
    row = run_case(
        "SYN-PILOT-0005",
        "SYN-PILOT-0005",
    )

    assert row["match_method"] == "MRN"
    assert "MRN_DISAGREEMENT" not in row["issues"]
