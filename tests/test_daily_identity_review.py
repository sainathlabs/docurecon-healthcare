
from datetime import date
from pathlib import Path
from unittest.mock import patch

from docurecon.reconciliation.daily_engine import run_daily


ROOT = Path(__file__).resolve().parents[1] / "sample_data"
DAY = date(2026, 11, 12)


def make_paper():
    return {
        "source": "DocuRecon_SYNTHETIC_TEST.pdf",
        "patient_name": "MARTINEZ, ELENA",
        "mrn": "SYN-939-001",
        "form_type": "9.39",
        "completion_date": "2026-11-12",
        "completion_time": "22:12",
        "review_reasons": [],
    }


def make_message(name):
    return {
        "source": "SYN-939-001.hl7",
        "patient_name": name,
        "patient_id": "SYN-939-001",
        "control_id": "TEST-C1",
        "legal_status": "9.39",
        "completion_timestamp": "2026-11-12T22:12",
        "transmitted_at": "2026-11-12T22:13",
    }


def make_ai_result():
    return {
        "model": "mock-model",
        "legal_status": "9.39",
        "issues": [],
        "comparisons": {
            "patient_name": {
                "ocr": "MARTINEZ, ELENA",
                "ai": "MARTINEZ, ELENA",
                "status": "AGREE",
            },
            "mrn": {
                "ocr": "SYN-939-001",
                "ai": "SYN-939-001",
                "status": "AGREE",
            },
        },
    }


def run_case(hl7_name, use_ai=True):
    with (
        patch(
            "docurecon.reconciliation.daily_engine.extract_folder",
            return_value=([make_paper()], []),
        ),
        patch(
            "docurecon.reconciliation.daily_engine.parse_hl7_folder",
            return_value=([make_message(hl7_name)], []),
        ),
        patch(
            "docurecon.reconciliation.daily_engine.parse_ack_folder",
            return_value=([], []),
        ),
        patch(
            "docurecon.reconciliation.daily_engine.validate_with_ai",
            return_value=make_ai_result(),
        ) as mock_ai,
    ):
        result = run_daily(
            ROOT,
            DAY,
            use_ai=use_ai,
        )

        return result, mock_ai.call_count


def test_hl7_name_conflict_is_detected():
    result, calls = run_case("MARTINEZ^ALICIA")

    assert calls == 1
    assert len(result["daily_rows"]) == 1

    row = result["daily_rows"][0]

    assert row["match_method"] == "MRN"
    assert row["identity_name_status"] == "CONFLICT"
    assert row["identity_mrn_status"] == "ALL_AGREE"
    assert row["identity_review_required"] is True
    assert row["identity_verified"] is False

    assert "PATIENT_NAME_EVIDENCE_CONFLICT" in row["issues"]


def test_matching_names_do_not_create_identity_conflict():
    result, calls = run_case("MARTINEZ^ELENA")

    assert calls == 1

    row = result["daily_rows"][0]

    assert row["identity_name_status"] == "ALL_AGREE"
    assert row["identity_mrn_status"] == "ALL_AGREE"
    assert row["identity_review_required"] is False
    assert "PATIENT_NAME_EVIDENCE_CONFLICT" not in row["issues"]


def test_ocr_only_behaviour_is_preserved():
    result, calls = run_case(
        "MARTINEZ^ALICIA",
        use_ai=False,
    )

    assert calls == 0

    row = result["daily_rows"][0]

    assert "identity_name_status" not in row
    assert "PATIENT_NAME_EVIDENCE_CONFLICT" not in row["issues"]



def test_name_conflict_prevents_provisional_match():
    """
    An HL7 name conflict must remain visible
    even when the MRN matches.
    """
    result, calls = run_case("MARTINEZ^ALICIA")

    assert calls == 1

    row = result["daily_rows"][0]

    assert row["status"] != "PROVISIONAL_MATCH"
    assert "PATIENT_NAME_EVIDENCE_CONFLICT" in row["issues"]
    assert row["identity_review_required"] is True
    assert row["identity_verified"] is False


def test_failed_ai_validation_is_not_identity_verified():
    """
    A failed AI call must not produce an
    apparently successful identity assessment.
    """
    with (
        patch(
            "docurecon.reconciliation.daily_engine.extract_folder",
            return_value=([make_paper()], []),
        ),
        patch(
            "docurecon.reconciliation.daily_engine.parse_hl7_folder",
            return_value=(
                [make_message("MARTINEZ^ELENA")],
                [],
            ),
        ),
        patch(
            "docurecon.reconciliation.daily_engine.parse_ack_folder",
            return_value=([], []),
        ),
        patch(
            "docurecon.reconciliation.daily_engine.validate_with_ai",
            side_effect=RuntimeError(
                "Synthetic AI validation failure"
            ),
        ),
    ):
        result = run_daily(
            ROOT,
            DAY,
            use_ai=True,
        )

    row = result["daily_rows"][0]

    assert row["ai_validation"] == "FAILED"
    assert row["identity_name_status"] == "NOT_EVALUATED"
    assert row["identity_mrn_status"] == "NOT_EVALUATED"
    assert row["identity_review_required"] is True
    assert row["identity_verified"] is False
    assert row["status"] != "PROVISIONAL_MATCH"


def test_pairwise_hl7_name_conflict_in_report():
    """
    OCR and AI agree, but HL7 contains
    a different patient name.
    """
    result, calls = run_case("MARTINEZ^ALICIA")

    assert calls == 1

    row = result["daily_rows"][0]

    assert row["identity_name_ocr_vs_ai"] == "AGREE"
    assert row["identity_name_ocr_vs_hl7"] == "DISAGREE"
    assert row["identity_name_ai_vs_hl7"] == "DISAGREE"

    assert row["identity_mrn_ocr_vs_ai"] == "AGREE"
    assert row["identity_mrn_ocr_vs_hl7"] == "AGREE"
    assert row["identity_mrn_ai_vs_hl7"] == "AGREE"

    assert row["identity_review_required"] is True
    assert row["identity_verified"] is False


def test_pairwise_matching_identity_in_report():
    """
    All three sources provide matching
    names and MRNs.
    """
    result, calls = run_case("MARTINEZ^ELENA")

    assert calls == 1

    row = result["daily_rows"][0]

    for field in ("name", "mrn"):
        for comparison in (
            "ocr_vs_ai",
            "ocr_vs_hl7",
            "ai_vs_hl7",
        ):
            assert row[
                f"identity_{field}_{comparison}"
            ] == "AGREE"

    assert row["identity_review_required"] is False
    assert row["identity_verified"] is False


def test_pairwise_columns_not_added_in_ocr_only_mode():
    """
    OCR-only output remains backward compatible.
    """
    result, calls = run_case(
        "MARTINEZ^ELENA",
        use_ai=False,
    )

    assert calls == 0

    row = result["daily_rows"][0]

    assert "identity_name_ocr_vs_ai" not in row
    assert "identity_mrn_ai_vs_hl7" not in row


def test_missing_hl7_candidate_has_no_verified_identity():
    """
    AI extraction may succeed, but without an HL7
    candidate a three-source assessment is unavailable.
    """

    with (
        patch(
            "docurecon.reconciliation.daily_engine.extract_folder",
            return_value=([make_paper()], []),
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
            "docurecon.reconciliation.daily_engine.validate_with_ai",
            return_value=make_ai_result(),
        ),
    ):
        result = run_daily(
            ROOT,
            DAY,
            use_ai=True,
        )

    assert len(result["daily_rows"]) == 1

    row = result["daily_rows"][0]

    assert row["match_method"] == "NONE"
    assert row["identity_name_status"] == "NOT_EVALUATED"
    assert row["identity_mrn_status"] == "NOT_EVALUATED"

    for field in ("name", "mrn"):
        for comparison in (
            "ocr_vs_ai",
            "ocr_vs_hl7",
            "ai_vs_hl7",
        ):
            assert row[
                f"identity_{field}_{comparison}"
            ] == "NOT_EVALUATED"

    assert row["identity_review_required"] is True
    assert row["identity_verified"] is False
    assert row["status"] == "OCR_UNCERTAIN"



def test_ocr_only_mrn_match_name_difference_requires_review():
    """
    Matching MRNs must not hide differing patient names.

    No AI call is required to identify conflicting
    OCR and HL7 evidence.
    """
    result, calls = run_case(
        "MARTINEZ^ALICIA",
        use_ai=False,
    )

    assert calls == 0

    row = result["daily_rows"][0]

    assert row["match_method"] == "MRN"

    # Desired behaviour, not yet implemented.
    assert (
        "PAPERWORK_HL7_NAME_DISAGREEMENT"
        in row["issues"]
    )

    assert row["status"] != "PROVISIONAL_MATCH"


def test_ocr_only_matching_names_no_disagreement():
    """
    Matching paperwork and HL7 names should not
    generate a name-disagreement issue.
    """
    result, calls = run_case(
        "MARTINEZ^ELENA",
        use_ai=False,
    )

    assert calls == 0

    row = result["daily_rows"][0]

    assert row["match_method"] == "MRN"

    assert (
        "PAPERWORK_HL7_NAME_DISAGREEMENT"
        not in row["issues"]
    )




def test_ocr_only_missing_paperwork_name_requires_review():
    """
    Regression test for the missing-name problem
    identified in synthetic retrospective case 0312.

    The paperwork MRN matches the HL7 MRN, but
    the OCR patient name is empty.

    The engine must flag missing identity evidence,
    rather than treating it as a provisional match.
    """

    paper = make_paper()
    paper["patient_name"] = ""

    with (
        patch(
            "docurecon.reconciliation.daily_engine.extract_folder",
            return_value=([paper], []),
        ),
        patch(
            "docurecon.reconciliation.daily_engine.parse_hl7_folder",
            return_value=(
                [make_message("MARTINEZ^ELENA")],
                [],
            ),
        ),
        patch(
            "docurecon.reconciliation.daily_engine.parse_ack_folder",
            return_value=([], []),
        ),
        patch(
            "docurecon.reconciliation.daily_engine.validate_with_ai",
            side_effect=AssertionError(
                "AI must not run in OCR-only mode"
            ),
        ) as mock_ai,
    ):
        result = run_daily(
            ROOT,
            DAY,
            use_ai=False,
        )

    mock_ai.assert_not_called()

    assert len(result["daily_rows"]) == 1

    row = result["daily_rows"][0]

    # MRN-based candidate selection still works.
    assert row["match_method"] == "MRN"
    assert row["control_id"] == "TEST-C1"

    # Missing OCR evidence must be clearly recorded.
    assert (
        "PAPERWORK_PATIENT_NAME_MISSING"
        in row["issues"]
    )

    assert (
        "PAPERWORK_PATIENT_NAME_UNREADABLE"
        in row["uncertainty_reasons"]
    )

    # Missing name is not a confirmed name disagreement.
    assert (
        "PAPERWORK_HL7_NAME_DISAGREEMENT"
        not in row["issues"]
    )

    # Missing evidence prevents a provisional match.
    assert row["status"] == "PROVISIONAL_EXCEPTION"
