
from src.docurecon.legal_status_resolver import (
    resolve_legal_status,
    status_from_form_type,
)


def test_form_474():
    assert status_from_form_type("OMH Form 474") == "9.39"


def test_form_475():
    assert status_from_form_type("OMH Form 475") == "9.37"


def test_form_475a():
    assert status_from_form_type("OMH Form 475A") == "9.37"


def test_marcus_document():
    ocr = {
        "legal_status": "9.39",
    }

    ai = {
        "legal_status": "Emergency Admission",
        "form_type": "OMH Form 474",
    }

    result = resolve_legal_status(ocr, ai)

    assert result["legal_status"] == "9.39"
    assert result["resolution"] == "OCR_AND_FORM_AGREE"


def test_conflicting_evidence():
    ocr = {
        "legal_status": "9.37",
    }

    ai = {
        "legal_status": "9.39",
        "form_type": "OMH Form 474",
    }

    result = resolve_legal_status(ocr, ai)

    assert result["legal_status"] is None
    assert result["resolution"] == "CONFLICT"


def test_ambiguous_description():
    result = resolve_legal_status(
        {"legal_status": ""},
        {
            "legal_status": "Emergency Admission",
            "form_type": "",
        },
    )

    assert result["legal_status"] is None
    assert result["resolution"] == "UNRESOLVED"
