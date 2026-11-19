
from docurecon.reconciliation.identity_validation import (
    assess_identity,
)


def test_all_three_sources_agree():
    result = assess_identity(
        "MARTINEZ, ELENA", "SYN-939-001",
        "MARTINEZ, ELENA", "SYN-939-001",
        "MARTINEZ^ELENA", "SYN-939-001",
    )

    assert result["name"]["status"] == "ALL_AGREE"
    assert result["mrn"]["status"] == "ALL_AGREE"
    assert result["identity_review_required"] is False
    assert result["identity_verified"] is False


def test_hl7_name_disagreement():
    result = assess_identity(
        "MARTINEZ, ELENA", "SYN-939-001",
        "MARTINEZ, ELENA", "SYN-939-001",
        "MARTINEZ^ALICIA", "SYN-939-001",
    )

    assert result["name"]["status"] == "CONFLICT"
    assert result["mrn"]["status"] == "ALL_AGREE"
    assert result["identity_review_required"] is True


def test_hl7_mrn_disagreement():
    result = assess_identity(
        "MARTINEZ, ELENA", "SYN-939-004",
        "MARTINEZ, ELENA", "SYN-939-001",
        "MARTINEZ^ELENA", "SYN-939-001",
    )

    assert result["mrn"]["status"] == "CONFLICT"
    assert result["identity_review_required"] is True


def test_missing_ai_evidence_requires_review():
    result = assess_identity(
        "MARTINEZ, ELENA", "SYN-939-001",
        "", "",
        "MARTINEZ^ELENA", "SYN-939-001",
    )

    assert result["name"]["status"] == "PARTIAL_AGREEMENT"
    assert result["mrn"]["status"] == "PARTIAL_AGREEMENT"
    assert result["identity_review_required"] is True


def test_all_identifiers_missing():
    result = assess_identity(
        "", "", "", "", "", "",
    )

    assert result["name"]["status"] == "ALL_MISSING"
    assert result["mrn"]["status"] == "ALL_MISSING"
    assert result["identity_review_required"] is True


def test_pairwise_ocr_name_error():
    result = assess_identity(
        "MRN, SYN", "SYN-002-001",
        "BHAT, NISHA", "SYN-002-001",
        "BHAT^NISHA", "SYN-002-001",
    )

    pairwise = result["name"]["pairwise"]

    assert pairwise["ocr_vs_ai"] == "DISAGREE"
    assert pairwise["ocr_vs_hl7"] == "DISAGREE"
    assert pairwise["ai_vs_hl7"] == "AGREE"

    assert result["name"]["status"] == "CONFLICT"
    assert result["identity_review_required"] is True


def test_pairwise_missing_ocr_name():
    result = assess_identity(
        "", "SYN-002-001",
        "BHAT, NISHA", "SYN-002-001",
        "BHAT^NISHA", "SYN-002-001",
    )

    pairwise = result["name"]["pairwise"]

    assert pairwise["ocr_vs_ai"] == "LEFT_MISSING"
    assert pairwise["ocr_vs_hl7"] == "LEFT_MISSING"
    assert pairwise["ai_vs_hl7"] == "AGREE"

    assert result["name"]["status"] == (
        "PARTIAL_AGREEMENT"
    )


def test_pairwise_hl7_name_disagreement():
    result = assess_identity(
        "BHAT, NISHA", "SYN-002-001",
        "BHAT, NISHA", "SYN-002-001",
        "BHAT^ALICIA", "SYN-002-001",
    )

    pairwise = result["name"]["pairwise"]

    assert pairwise["ocr_vs_ai"] == "AGREE"
    assert pairwise["ocr_vs_hl7"] == "DISAGREE"
    assert pairwise["ai_vs_hl7"] == "DISAGREE"

    assert result["name"]["status"] == "CONFLICT"
    assert result["identity_verified"] is False
