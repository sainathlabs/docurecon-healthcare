
"""
Patient-name candidate selection from OCR text.

Uses paperwork OCR evidence only.

Does not use HL7, filenames, ground truth,
or AI-generated values to infer patient identity.
"""

import re


NAME_PATTERN = re.compile(
    r"\b([A-Z][A-Z'-]{1,}),\s*([A-Z][A-Z'-]{1,})\b",
    re.I,
)

# Structural tokens that should not become patient names.
NON_NAME_TOKENS = {
    "MRN",
    "SYN",
    "DOB",
    "DATE",
    "TIME",
    "FORM",
    "PAGE",
    "PATIENT",
    "NAME",
    "FACILITY",
    "HOSPITAL",
}


def normalize_candidate(value):
    """Standardise a candidate without correcting spelling."""
    return " ".join(
        (value or "").upper().split()
    )


def is_valid_name_candidate(value):
    """
    Reject obvious form labels.

    Does not attempt to judge whether a person's
    name looks familiar or correctly spelled.
    """
    candidate = normalize_candidate(value)

    match = NAME_PATTERN.fullmatch(candidate)

    if not match:
        return False

    surname, given_name = match.groups()

    if (
        surname in NON_NAME_TOKENS
        or given_name in NON_NAME_TOKENS
    ):
        return False

    return True


def extract_patient_name_candidate(text):
    """
    Select a patient-name candidate from OCR text.

    Priority:
    1. Explicit patient-name label
    2. Admission-request sentence
    3. A single unambiguous unlabelled candidate

    Returns:
        {
            "patient_name": str,
            "source": str,
            "review_required": bool,
        }
    """
    text = text or ""


    # --------------------------------------------------
    # OMH Form 475 (§9.37) header-name extraction
    # --------------------------------------------------
    #
    # Supported synthetic Form 475 layouts may place
    # the patient's name at the end of the application
    # heading, separated by a hyphen or underscore.
    #
    # Only apply this rule in the specific form-heading
    # context. Do not globally reinterpret hyphens
    # inside names.


    # --------------------------------------------------
    # OMH Form 475 (§9.37) header-name extraction
    # --------------------------------------------------
    # Supported synthetic layouts use either:
    #
    # APPLICATION ... OF A | KUMAR, ZARA
    # APPLICATION ... OF A | -KHAN_ISHAN
    #
    # Restrict parsing to the application heading.

    form_475_header = re.search(
        r"^[^\n]*APPLICATION[ \t]+FOR[ \t]+INVOLUNTARY"
        r"[ \t]+ADMISSION[ \t]+ON[ \t]+CERTIFICATE"
        r"[ \t]+OF[ \t]+A"
        r"[^\n]*?[ \t|]+-?[ \t]*"
        r"([A-Z][A-Z'-]{1,})"
        r"[ \t]*[,_-][ \t]*"
        r"([A-Z][A-Z'-]{1,})\b",
        text,
        re.I | re.M,
    )

    if form_475_header:
        surname = form_475_header.group(1).upper()
        given_name = form_475_header.group(2).upper()

        header_name = f"{surname}, {given_name}"

        # Compare against the admission-request sentence
        # if it also contains a readable name.
        admission_evidence = re.search(
            r"\bhereby\s+request\s+that\s*"
            r"""['"‘’“”]*\s*"""
            r"([A-Z][A-Z'-]{1,}),\s*"
            r"([A-Z][A-Z'-]{1,})"
            r"\s+be\s+admitted\b",
            text,
            re.I,
        )

        if (
            is_valid_name_candidate(header_name)
            and admission_evidence
        ):
            admission_surname = (
                admission_evidence.group(1).upper()
            )
            admission_given_name = (
                admission_evidence.group(2).upper()
            )

            # A disagreement in the given name is
            # potentially material. Do not guess
            # which OCR location is correct.
            if given_name != admission_given_name:
                return {
                    "patient_name": "",
                    "source": "CONFLICTING_NAME_EVIDENCE",
                    "review_required": True,
                }

            # A missing leading surname character is
            # common in the observed synthetic OCR.
            # Preserve the header as the extracted
            # candidate, but retain human review.
            #
            # This is NOT independent verification.
            if surname != admission_surname:
                if not surname.endswith(admission_surname):
                    return {
                        "patient_name": "",
                        "source": "CONFLICTING_NAME_EVIDENCE",
                        "review_required": True,
                    }

        if is_valid_name_candidate(header_name):
            return {
                "patient_name": header_name,
                "source": "FORM_475_HEADER",
                "review_required": True,
            }



    # 0. OMH Form 474 (§9.39) heading.
    #
    # In the supported synthetic layout, the patient's
    # name appears on the same OCR line immediately
    # after "EMERGENCY ADMISSION".
    #
    # Require the heading and name on the same line
    # to avoid matching unrelated text elsewhere.

    emergency_heading = re.search(
        r"^[ \t]*EMERGENCY[ \t]+ADMISSION[ \t]+"
        r"([A-Z][A-Z'-]{1,},[ \t]*[A-Z][A-Z'-]{1,})\b",
        text,
        re.I | re.M,
    )

    if emergency_heading:
        candidate = normalize_candidate(
            emergency_heading.group(1)
        )

        if is_valid_name_candidate(candidate):
            return {
                "patient_name": candidate,
                "source": "EMERGENCY_ADMISSION_HEADING",
                "review_required": True,
            }


    # 1. Label-based extraction
    labelled = re.search(
        r"\bPATIENT\s+NAME\s*[:\-]?\s*"
        r"([A-Z][A-Z'-]{1,},\s*[A-Z][A-Z'-]{1,})",
        text,
        re.I,
    )

    if labelled:
        candidate = normalize_candidate(
            labelled.group(1)
        )

        if is_valid_name_candidate(candidate):
            return {
                "patient_name": candidate,
                "source": "PATIENT_NAME_LABEL",
                "review_required": False,
            }

    # 2. Admission-request sentence
    admission = re.search(
        r"\bhereby\s+request\s+that\s*"
        r"([A-Z][A-Z'-]{1,},\s*[A-Z][A-Z'-]{1,})"
        r"\s+be\s+admitted\b",
        text,
        re.I,
    )

    if admission:
        candidate = normalize_candidate(
            admission.group(1)
        )

        if is_valid_name_candidate(candidate):
            return {
                "patient_name": candidate,
                "source": "ADMISSION_REQUEST",
                "review_required": True,
            }

    # 3. Unlabelled names
    candidates = []

    for match in NAME_PATTERN.finditer(text):
        candidate = normalize_candidate(
            match.group(0)
        )

        if (
            is_valid_name_candidate(candidate)
            and candidate not in candidates
        ):
            candidates.append(candidate)


    # A comma-separated phrase appearing inside ordinary
    # narrative text is not sufficient patient-name evidence.
    #
    # Only accept a single unlabelled candidate when it
    # occupies its own OCR line.
    #
    # Otherwise, return missing/ambiguous evidence rather
    # than selecting words from clinical narrative text.

    if len(candidates) == 1:
        candidate = candidates[0]

        standalone = any(
            normalize_candidate(line) == candidate
            for line in text.splitlines()
        )

        if standalone:
            return {
                "patient_name": candidate,
                "source": "SINGLE_UNLABELLED_CANDIDATE",
                "review_required": True,
            }


    # No reliable single candidate.
    return {
        "patient_name": "",
        "source": (
            "AMBIGUOUS_CANDIDATES"
            if candidates
            else "NO_VALID_CANDIDATE"
        ),
        "review_required": True,
    }
