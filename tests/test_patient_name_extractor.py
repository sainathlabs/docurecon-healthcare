
from docurecon.parsers.patient_name_extractor import (
    extract_patient_name_candidate,
)


def test_rejects_mrn_syn_and_selects_labelled_name():
    text = """
    MRN,
    SYN
    Patient Name: BHAT, NISHA
    """

    result = extract_patient_name_candidate(text)

    assert result["patient_name"] == "BHAT, NISHA"
    assert result["source"] == "PATIENT_NAME_LABEL"


def test_admission_request_fallback():
    text = (
        "I hereby request that KAUR, VARUN "
        "be admitted to the hospital."
    )

    result = extract_patient_name_candidate(text)

    assert result["patient_name"] == "KAUR, VARUN"
    assert result["source"] == "ADMISSION_REQUEST"


def test_single_unlabelled_candidate():
    text = """
    Patient admission record

    SHAH, KAVYA

    Date of admission: 11/12/2026
    """

    result = extract_patient_name_candidate(text)

    assert result["patient_name"] == "SHAH, KAVYA"
    assert result["source"] == "SINGLE_UNLABELLED_CANDIDATE"
    assert result["review_required"] is True


def test_multiple_unlabelled_candidates_require_review():
    text = """
    Physician: SHAH, KAVYA
    Witness: IYER, ZARA
    """

    result = extract_patient_name_candidate(text)

    assert result["patient_name"] == ""
    assert result["source"] == "AMBIGUOUS_CANDIDATES"
    assert result["review_required"] is True


def test_only_structural_tokens_returns_missing():
    text = "MRN,\nSYN"

    result = extract_patient_name_candidate(text)

    assert result["patient_name"] == ""
    assert result["source"] == "NO_VALID_CANDIDATE"


def test_does_not_autocorrect_misspelled_name():
    text = "Patient Name: AUR, VARUN"

    result = extract_patient_name_candidate(text)

    assert result["patient_name"] == "AUR, VARUN"
    assert result["source"] == "PATIENT_NAME_LABEL"

def test_emergency_admission_heading_martinez():
    text = """
    Office of Mental Health
    OMH Form 474
    Name (Last, First, MI)

    EMERGENCY ADMISSION MARTINEZ, ELENA
    (Mental Hygiene Law 9.39)

    Person was taken into custody, transported,
    or removed to this hospital.
    """

    result = extract_patient_name_candidate(text)

    assert result["patient_name"] == "MARTINEZ, ELENA"
    assert result["source"] == (
        "EMERGENCY_ADMISSION_HEADING"
    )
    assert result["review_required"] is True


def test_emergency_admission_heading_bell():
    text = """
    DOCURECON RESEARCH SAMPLE
    Stare, Mental Health
    Name (Last, First, MI)

    EMERGENCY ADMISSION BELL, MARCUS
    (Mental Hygiene Law 9.39)

    Inability or refusal, due to mental illness,
    to provide essential needs such as food, clothing.
    """

    result = extract_patient_name_candidate(text)

    assert result["patient_name"] == "BELL, MARCUS"
    assert result["source"] == (
        "EMERGENCY_ADMISSION_HEADING"
    )


def test_form_475_header_recovers_khan():
    text = """
    OMH Forms 475, 475A, 475B
    APPLICATION FOR INVOLUNTARY ADMISSION ON CERTIFICATE OF A | -KHAN_ISHAN
    DIRECTOR OF COMMUNITY SERVICES OR DESIGNEE

    I hereby request thatHAN, ISHAN be admitted to
    """

    result = extract_patient_name_candidate(text)

    assert result["patient_name"] == "KHAN, ISHAN"
    assert result["source"] == "FORM_475_HEADER"
    assert result["review_required"] is True


def test_form_475_header_recovers_iyer():
    text = """
    OMH Forms 475, 475A, 475B
    APPLICATION FOR INVOLUNTARY ADMISSION ON CERTIFICATE OF A | IYER-SHREYA
    DIRECTOR OF COMMUNITY SERVICES OR DESIGNEE

    I hereby request that'YER, SHREYA be admitted to
    """

    result = extract_patient_name_candidate(text)

    assert result["patient_name"] == "IYER, SHREYA"
    assert result["source"] == "FORM_475_HEADER"
    assert result["review_required"] is True


def test_header_rule_does_not_match_unrelated_text():
    text = """
    Notes: -KHAN_ISHAN

    Patient transport information:
    Person was taken into custody, transported,
    or removed to this hospital.
    """

    result = extract_patient_name_candidate(text)

    assert result["source"] != "FORM_475_HEADER"
    assert result["patient_name"] == ""


def test_form_475_comma_header_recovers_kumar():
    text = """
    APPLICATION FOR INVOLUNTARY ADMISSION ON CERTIFICATE OF A | KUMAR, ZARA

    I hereby request thatUMAR, ZARA be admitted to
    """

    result = extract_patient_name_candidate(text)

    assert result["patient_name"] == "KUMAR, ZARA"
    assert result["source"] == "FORM_475_HEADER"


def test_form_475_comma_header_recovers_kaur():
    text = """
    APPLICATION FOR INVOLUNTARY ADMISSION ON CERTIFICATE OF A | KAUR, ZARA

    I hereby request that“AUR, ZARA be admitted to
    """

    result = extract_patient_name_candidate(text)

    assert result["patient_name"] == "KAUR, ZARA"
    assert result["source"] == "FORM_475_HEADER"


def test_form_475_conflicting_given_name_requires_review():
    text = """
    APPLICATION FOR INVOLUNTARY ADMISSION ON CERTIFICATE OF A | -WALIA_KAVYVA

    I hereby request thatWALIA, KAVYA be admitted to
    """

    result = extract_patient_name_candidate(text)

    assert result["patient_name"] == ""
    assert result["source"] == "CONFLICTING_NAME_EVIDENCE"
    assert result["review_required"] is True


def test_form_475_conflicting_ocr_character_requires_review():
    text = """
    APPLICATION FOR INVOLUNTARY ADMISSION ON CERTIFICATE OF A | -CHANDRA_SHREVA

    I hereby request that CHANDRA, SHREYA be admitted to
    """

    result = extract_patient_name_candidate(text)

    assert result["patient_name"] == ""
    assert result["source"] == "CONFLICTING_NAME_EVIDENCE"
    assert result["review_required"] is True
