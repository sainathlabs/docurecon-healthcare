
"""
DocuRecon - Daily Reconciliation Engine

Synthetic research prototype only.

Features:
- Tesseract OCR paperwork extraction
- Optional OpenAI-assisted validation
- HL7 ADT message parsing
- ACK/NACK reconciliation
- MRN disagreement detection
- Legal-status comparison
- Completion date/time comparison
- Exception and uncertainty reporting

Important:
- Paperwork findings are provisional.
- AI never silently replaces OCR values.
- Patient-name-only matches are uncertain.
- Missing source files are not proof of reporting failures.
- This module does not determine legal document validity.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
import re

from docurecon.parsers.paperwork_parser import extract_folder
from docurecon.parsers.hl7_parser import parse_hl7_folder
from docurecon.parsers.ack_parser import parse_ack_folder

from docurecon.reconciliation.daily_ai_validation import (
    validate_with_ai,
)

from docurecon.reconciliation.identity_validation import (
    assess_identity,
)

from docurecon.reconciliation.date_assignment import (
    assess_date_assignment,
)

# --------------------------------------------------
# Helper functions
# --------------------------------------------------

def _normal_name(value: str) -> str:
    """Normalise patient names for provisional matching."""

    pieces = re.split(
        r"[\^,\s]+",
        (value or "").upper(),
    )

    return " ".join(
        sorted(p for p in pieces if p)
    )


def _date(value: str) -> str:
    """Return ISO date portion of a timestamp."""

    return (value or "")[:10]


def _ack_state(found: list[dict]) -> str:
    """Classify supplied application ACK messages."""

    if not found:
        return "NO_ACK_IN_SUPPLIED_FILES"

    if len(found) != 1:
        return "MULTIPLE_ACKS"

    return found[0]["ack_class"]


def _unique(values: list[str]) -> list[str]:
    """Remove duplicate reasons while preserving order."""

    return list(dict.fromkeys(values))


# --------------------------------------------------
# Daily reconciliation
# --------------------------------------------------

def run_daily(
    root: Path,
    selected: date | str,
    *,
    source_mode="folder",
    uploads=None,
    use_ai=False,
    date_ai_evidence=None,
    review_excluded_dates_with_ai=False,
    max_date_review_ai_calls=0,
) -> dict:
    """
    Run daily reconciliation using supplied folders.

    The selected date refers to the paperwork
    completion date extracted by OCR.

    Searches all supplied HL7 messages, including
    those whose message timestamps are on other days.

    AI extraction is optional and restricted by the
    AI extractor to approved synthetic research PDFs.
    """

    root = Path(root)

    day = (
        selected.isoformat()
        if isinstance(selected, date)
        else str(selected)
    )

    datetime.strptime(day, "%Y-%m-%d")

    # --------------------------------------------------
    # 1. Extract all three input sources
    # --------------------------------------------------

    papers, paper_errors = extract_folder(
        root / "paperwork"
    )

    messages, hl7_errors = parse_hl7_folder(
        root / "hl7"
    )

    acks, ack_errors = parse_ack_folder(
        root / "acknowledgements"
    )

    errors = (
        [
            {"folder": "paperwork", **error}
            for error in paper_errors
        ]
        + [
            {"folder": "hl7", **error}
            for error in hl7_errors
        ]
        + [
            {"folder": "acknowledgements", **error}
            for error in ack_errors
        ]
    )

    # --------------------------------------------------
    # 2. Prepare HL7 and ACK indexes
    # --------------------------------------------------

    ack_by_id = defaultdict(list)

    for ack in acks:
        ack_by_id[ack["control_id"]].append(ack)

    control_counts = Counter(
        message["control_id"]
        for message in messages
    )

    rows = []

    # --------------------------------------------------
    # 3. Select paperwork for the requested date
    # --------------------------------------------------

    selected_papers = [
        paper
        for paper in papers
        if paper.get("completion_date") == day
    ]

    excluded_missing_date = [
        paper
        for paper in papers
        if not paper.get("completion_date")
    ]

     # Do not mutate the caller's evidence dictionary.
    date_ai_evidence = dict(date_ai_evidence or {})

    date_review_ai_errors = []
    date_review_ai_calls = 0

    if not isinstance(max_date_review_ai_calls, int):
        raise ValueError(
            "max_date_review_ai_calls must be an integer"
        )

    if max_date_review_ai_calls < 0:
        raise ValueError(
            "max_date_review_ai_calls cannot be negative"
        )

    if review_excluded_dates_with_ai:
        if max_date_review_ai_calls == 0:
            raise ValueError(
                "Set a positive max_date_review_ai_calls "
                "to enable live AI date review."
            )

        from docurecon.ai.document_extractor import (
            extract_document,
        )

        # Only OCR-excluded paperwork is considered.
        # Existing daily rows are not changed.
        excluded_papers = [
            paper
            for paper in papers
            if paper.get("completion_date") != day
        ]

        for paper in excluded_papers:
            if (
                date_review_ai_calls
                >= max_date_review_ai_calls
            ):
                break

            source = paper["source"]

            # Reuse supplied evidence when available.
            if source in date_ai_evidence:
                continue

            pdf_path = root / "paperwork" / source

            # Counts attempted API calls, including failures.
            date_review_ai_calls += 1

            try:
                ai_response = extract_document(
                    pdf_path
                )

                ai_fields = ai_response.get(
                    "extracted_fields", {}
                )

                if not isinstance(ai_fields, dict):
                    raise ValueError(
                        "Invalid AI extraction response"
                    )

                date_ai_evidence[source] = {
                    "completion_date": (
                        ai_fields.get(
                            "completion_date"
                        ) or ""
                    )
                }

            except Exception as exc:
                date_review_ai_errors.append({
                    "paperwork_file": source,
                    "error_type": (
                        type(exc).__name__
                    ),
                    "error": str(exc),
                })

    date_review_queue = []


    for paper in papers:
        source = paper["source"]
        ocr_date = paper.get("completion_date") or ""

        evidence = date_ai_evidence.get(source)
        ai_attempted = isinstance(evidence, dict)

        ai_date = (
            evidence.get("completion_date") or ""
            if ai_attempted
            else ""
        )

        assessment = assess_date_assignment(
            ocr_date,
            ai_date,
            day,
            ai_attempted=ai_attempted,
        )

        # Include unassigned paperwork and relevant
        # disagreements involving the requested date.
        relevant = (
            not ocr_date
            or (
                ai_attempted
                and assessment["review_required"]
                and (
                    ocr_date == day
                    or ai_date == day
                )
            )
        )

        if relevant:
            date_review_queue.append({
                "paperwork_file": source,
                "selected_date": day,
                "ocr_date": ocr_date,
                "ai_date": ai_date,
                "classification": assessment[
                    "classification"
                ],
                "review_required": assessment[
                    "review_required"
                ],
                "ai_supported_candidate": assessment[
                    "ai_supported_candidate"
                ],
                "included_in_daily": assessment[
                    "include_in_daily"
                ],
                "reason": (
                    "Date evidence requires review; "
                    "legal completion is not verified."
                ),
            })


    # --------------------------------------------------
    # 4. Optional live AI validation
    # --------------------------------------------------

    ai_checks = {}

    if use_ai:

        for paper in selected_papers:

            pdf_path = (
                root
                / "paperwork"
                / paper["source"]
            )

            try:
                ai_checks[paper["source"]] = (
                    validate_with_ai(
                        paper,
                        pdf_path,
                    )
                )

            except Exception as exc:

                ai_checks[paper["source"]] = {
                    "issues": ["AI_EXTRACTION_FAILED"],
                    "error": str(exc),
                    "comparisons": {},
                    "legal_status": None,
                }

    # --------------------------------------------------
    # 5. Reconcile each selected paperwork record
    # --------------------------------------------------

    for paper in selected_papers:

        source = paper["source"]

        reasons = list(
            paper.get("review_reasons") or []
        )

        issues = []

        ai_check = ai_checks.get(source, {})
                # Identity assessment is populated only when
        # successful AI evidence and an HL7 candidate exist.
        identity_assessment = None

        # Preserve AI extraction disagreements.
        if use_ai:

            for ai_issue in ai_check.get(
                "issues", []
            ):

                reasons.append(ai_issue)

                if ai_issue not in issues:
                    issues.append(ai_issue)

            if ai_check.get("error"):
                reasons.append(
                    "AI_VALIDATION_UNAVAILABLE"
                )

        # ----------------------------------------------
        # Patient identifiers
        # ----------------------------------------------

        mrn = (
            paper.get("mrn") or ""
        ).strip().upper()

        name = _normal_name(
            paper.get("patient_name", "")
        )

        # Match by OCR MRN.
        exact = [
            message
            for message in messages
            if (
                mrn
                and message["patient_id"].upper()
                == mrn
            )
        ]

        # Independent name-based candidate search.
        by_name = [
            message
            for message in messages
            if (
                name
                and _normal_name(
                    message.get(
                        "patient_name", ""
                    )
                ) == name
            )
        ]

        # ----------------------------------------------
        # Candidate matching
        # ----------------------------------------------

        exact_ids = {
            message["control_id"]
            for message in exact
        }

        name_ids = {
            message["control_id"]
            for message in by_name
        }

        if (
            exact
            and by_name
            and exact_ids != name_ids
        ):
            candidates = []

            reasons.append(
                "CONFLICTING_PATIENT_MATCH_EVIDENCE"
            )

            issues.append(
                "CONFLICTING_PATIENT_MATCH_EVIDENCE"
            )

        else:
            candidates = exact or by_name

        if exact and candidates:
            method = "MRN"

        elif candidates:
            method = "PATIENT_NAME_ONLY"

        else:
            method = "NONE"

        if method == "PATIENT_NAME_ONLY":

            reasons.append(
                "MATCHED_BY_NAME_NOT_VERIFIED_MRN"
            )

            reasons.append(
                "PATIENT_IDENTIFIER_REQUIRES_VALIDATION"
            )

        # ----------------------------------------------
        # Default HL7 and ACK fields
        # ----------------------------------------------

        control = ""
        hl7_file = ""
        ack_file = ""
        ack_code = ""
        ack_status = "NOT_APPLICABLE"

        # ----------------------------------------------
        # Evaluate HL7 candidates
        # ----------------------------------------------

        if len(candidates) > 1:

            issues.append(
                "AMBIGUOUS_MULTIPLE_HL7_CANDIDATES"
            )

        elif not candidates:

            issues.append(
                "NO_HL7_CANDIDATE_IN_SUPPLIED_FILES"
            )

            reasons.append(
                "UNCONFIRMED_ABSENCE_REQUIRES_COMPLETE_SOURCE_EXPORT"
            )

        else:

            message = candidates[0]


            # ------------------------------------------
            # OCR vs HL7 patient-name consistency
            # ------------------------------------------
            #
            # Perform this check even when AI is disabled.
            # A matching MRN does not establish that the
            # patient names are consistent.
            #
            # This is an evidence discrepancy, not proof
            # that the HL7 patient name is incorrect.

            paperwork_name = _normal_name(
                paper.get("patient_name", "")
            )

            hl7_patient_name = _normal_name(
                message.get("patient_name", "")
            )

            if paperwork_name and hl7_patient_name:
                if paperwork_name != hl7_patient_name:
                    issues.append(
                        "PAPERWORK_HL7_NAME_DISAGREEMENT"
                    )

                    reasons.append(
                        "PATIENT_NAME_REQUIRES_HUMAN_REVIEW"
                    )

            elif not paperwork_name and hl7_patient_name:
                reasons.append(
                    "PAPERWORK_PATIENT_NAME_UNREADABLE"
                )

            elif paperwork_name and not hl7_patient_name:
                reasons.append(
                    "HL7_PATIENT_NAME_MISSING"
                )



            # ------------------------------------------
            # OCR / AI / HL7 identity consistency
            # ------------------------------------------
            #
            # Only evaluate the three-source comparison
            # when AI validation has succeeded.
            #
            # This does not verify patient identity.
            # It only identifies conflicting evidence.

            if (
                use_ai
                and not ai_check.get("error")
                and ai_check.get("comparisons")
            ):
                comparisons = ai_check["comparisons"]

                ai_name = (
                    comparisons.get(
                        "patient_name", {}
                    ).get("ai") or ""
                )

                ai_mrn = (
                    comparisons.get(
                        "mrn", {}
                    ).get("ai") or ""
                )

                identity_assessment = assess_identity(
                    ocr_name=paper.get(
                        "patient_name", ""
                    ),
                    ocr_mrn=paper.get("mrn", ""),
                    ai_name=ai_name,
                    ai_mrn=ai_mrn,
                    hl7_name=message.get(
                        "patient_name", ""
                    ),
                    hl7_mrn=message.get(
                        "patient_id", ""
                    ),
                )

                # A name discrepancy is important even
                # when the paperwork and HL7 MRNs match.
                if (
                    identity_assessment["name"]["status"]
                    == "CONFLICT"
                ):
                    issues.append(
                        "PATIENT_NAME_EVIDENCE_CONFLICT"
                    )
                    reasons.append(
                        "PATIENT_NAME_REQUIRES_HUMAN_REVIEW"
                    )

                # MRN disagreement is also handled by the
                # existing engine. Avoid duplicate issue codes.
                if (
                    identity_assessment["mrn"]["status"]
                    == "CONFLICT"
                    and "MRN_DISAGREEMENT" not in issues
                ):
                    issues.append(
                        "PATIENT_MRN_EVIDENCE_CONFLICT"
                    )
                    reasons.append(
                        "PATIENT_IDENTITY_REQUIRES_HUMAN_REVIEW"
                    )


            control = message["control_id"]
            hl7_file = message["source"]

                        # Compare the two identifiers without treating
            # a name-only candidate as a verified identity.
            hl7_mrn = (
                message.get("patient_id") or ""
            ).strip().upper()

            if mrn and hl7_mrn and mrn != hl7_mrn:
                issues.append("MRN_DISAGREEMENT")
                reasons.append(
                    "PATIENT_IDENTITY_REQUIRES_HUMAN_REVIEW"
                )

            # ------------------------------------------
            # Legal status comparison
            # ------------------------------------------

            if (
                message["legal_status"]
                != paper.get("form_type")
            ):

                issues.append(
                    "LEGAL_STATUS_MISMATCH_PROVISIONAL"
                )

            # ------------------------------------------
            # Completion date comparison
            # ------------------------------------------

            if (
                _date(
                    message["completion_timestamp"]
                ) != day
            ):

                issues.append(
                    "COMPLETION_DATE_MISMATCH_PROVISIONAL"
                )

            # ------------------------------------------
            # Completion time comparison
            # ------------------------------------------

            paperwork_time = paper.get(
                "completion_time"
            )

            hl7_time = (
                message["completion_timestamp"][11:16]
            )

            if paperwork_time:

                if paperwork_time != hl7_time:

                    issues.append(
                        "COMPLETION_TIME_MISMATCH_PROVISIONAL"
                    )

            else:

                reasons.append(
                    "COMPLETION_TIME_NOT_COMPARABLE"
                )

            # ------------------------------------------
            # ACK/NACK matching
            # ------------------------------------------

            found = ack_by_id.get(
                control, []
            )

            ack_status = _ack_state(found)

            ack_file = ", ".join(
                ack["source"]
                for ack in found
            )

            ack_code = ", ".join(
                ack["ack_code"]
                for ack in found
            )

            if control_counts[control] > 1:

                issues.append(
                    "DUPLICATE_CONTROL_ID"
                )

            if ack_status != "ACCEPTED":

                issues.append(ack_status)

            # These are message timestamps,
            # not verified transport receipt times.
            if found and any(
                ack["received_at"]
                < message["transmitted_at"]
                for ack in found
            ):

                issues.append(
                    "ACK_BEFORE_TRANSMISSION_TIMESTAMP"
                )

        # ----------------------------------------------
        # Determine provisional outcome
        # ----------------------------------------------

        uncertain_linkage = (
            not candidates
            or len(candidates) > 1
            or method == "PATIENT_NAME_ONLY"
        )

        if uncertain_linkage:
            status = "OCR_UNCERTAIN"

        elif issues:
            status = "PROVISIONAL_EXCEPTION"

        else:
            status = "PROVISIONAL_MATCH"

        # ----------------------------------------------
        # Build reconciliation row
        # ----------------------------------------------

        row = {
            "paperwork_file": source,
            "patient_name": paper.get(
                "patient_name", ""
            ),
            "ocr_mrn": mrn,
            "legal_status_paperwork": paper.get(
                "form_type", ""
            ),
            "completion_date": day,
            "completion_time_ocr": paper.get(
                "completion_time", ""
            ),
            "match_method": method,
            "hl7_file": hl7_file,
            "control_id": control,
            "ack_file": ack_file,
            "ack_code": ack_code,
            "ack_status": ack_status,
            "status": status,
            "issues": "; ".join(
                _unique(issues)
            ),
            "uncertainty_reasons": "; ".join(
                _unique(reasons)
            ),
        }

        # ----------------------------------------------
        # 6. Add AI results when enabled
        # ----------------------------------------------

        if use_ai:

            if ai_check.get("error"):
                row["ai_validation"] = "FAILED"

            elif ai_check.get("issues"):
                row["ai_validation"] = (
                    "DISAGREEMENT"
                )

            else:
                row["ai_validation"] = "AGREEMENT"

            row["ai_issues"] = "; ".join(
                _unique(
                    ai_check.get("issues", [])
                )
            )

            row["resolved_legal_status"] = (
                ai_check.get(
                    "legal_status"
                ) or ""
            )

            # OCR vs AI MRN comparison.
            mrn_comparison = (
                ai_check.get(
                    "comparisons", {}
                ).get("mrn", {})
            )

            row["ai_mrn"] = (
                mrn_comparison.get("ai") or ""
            )

            row["ocr_ai_mrn_agreement"] = (
                mrn_comparison.get("status")
                or "NOT_EVALUATED"
            )


            # Preserve the identity assessment in the
            # reconciliation result for audit and review.
            if identity_assessment is not None:
                row["identity_name_status"] = (
                    identity_assessment["name"]["status"]
                )

                row["identity_mrn_status"] = (
                    identity_assessment["mrn"]["status"]
                )

                row["identity_review_required"] = (
                    identity_assessment[
                        "identity_review_required"
                    ]
                )

                row["identity_verified"] = False


                # Preserve pairwise evidence in the report.
                # These comparisons describe agreement,
                # not independently verified identity.
                for field in ("name", "mrn"):
                    pairwise = identity_assessment[
                        field
                    ]["pairwise"]

                    for comparison in (
                        "ocr_vs_ai",
                        "ocr_vs_hl7",
                        "ai_vs_hl7",
                    ):
                        row[
                            f"identity_{field}_{comparison}"
                        ] = pairwise[comparison]


            else:
                row["identity_name_status"] = "NOT_EVALUATED"
                row["identity_mrn_status"] = "NOT_EVALUATED"
                row["identity_review_required"] = True
                row["identity_verified"] = False


                # No three-source comparison was performed.
                for field in ("name", "mrn"):
                    for comparison in (
                        "ocr_vs_ai",
                        "ocr_vs_hl7",
                        "ai_vs_hl7",
                    ):
                        row[
                            f"identity_{field}_{comparison}"
                        ] = "NOT_EVALUATED"



            # Preserve HL7/ACK exceptions.
            # An AI disagreement must not erase them.
            if (
                ai_check.get("issues")
                and row["status"]
                == "PROVISIONAL_MATCH"
            ):
                row["status"] = "OCR_UNCERTAIN"

        rows.append(row)

    # --------------------------------------------------
    # 7. Handle paperwork with unreadable dates
    # --------------------------------------------------

    for paper in excluded_missing_date:

        rows.append({
            "paperwork_file": paper["source"],
            "patient_name": paper.get(
                "patient_name", ""
            ),
            "ocr_mrn": paper.get("mrn", ""),
            "legal_status_paperwork": paper.get(
                "form_type", ""
            ),
            "completion_date": "",
            "completion_time_ocr": paper.get(
                "completion_time", ""
            ),
            "match_method": "NONE",
            "hl7_file": "",
            "control_id": "",
            "ack_file": "",
            "ack_code": "",
            "ack_status": "NOT_EVALUATED",
            "status": "OCR_UNCERTAIN",
            "issues": (
                "CANNOT_ASSIGN_PAPERWORK_TO_SELECTED_DATE"
            ),
            "uncertainty_reasons": "; ".join(
                paper.get("review_reasons") or []
            ),
        })


    # --------------------------------------------------
    # Separate daily and unassigned reporting views.
    #
    # Keep the original "rows" unchanged for backward
    # compatibility with existing tests and consumers.
    # --------------------------------------------------

    daily_rows = [
        row
        for row in rows
        if row.get("completion_date") == day
    ]

    unassigned_paperwork = [
        {
            "paperwork_file": paper["source"],
            "patient_name": paper.get(
                "patient_name", ""
            ),
            "ocr_mrn": paper.get("mrn", ""),
            "legal_status_paperwork": paper.get(
                "form_type", ""
            ),
            "ocr_completion_date": "",
            "review_required": True,
            "reason": (
                "OCR completion date unreadable; "
                "date assignment requires review."
            ),
        }
        for paper in excluded_missing_date
    ]


    # --------------------------------------------------
    # 8. Identify orphan ACK messages
    # --------------------------------------------------

    orphan_acks = [
        ack
        for ack in acks
        if ack["control_id"]
        not in control_counts
    ]

    # --------------------------------------------------
    # 9. Summary metrics
    # --------------------------------------------------

    counts = Counter(
        row["status"]
        for row in rows
    )

    return {
        "date": day,

        "paperwork_count": len(
            selected_papers
        ),

        "hl7_count": len(messages),

        "ack_count": len(acks),

        "provisional_matches": counts[
            "PROVISIONAL_MATCH"
        ],

        "provisional_exceptions": counts[
            "PROVISIONAL_EXCEPTION"
        ],

        "ocr_uncertain": counts[
            "OCR_UNCERTAIN"
        ],

       "rows": rows,
       "daily_rows": daily_rows,

        "unassigned_paperwork": unassigned_paperwork,

        "unassigned_paperwork_count": len(
            unassigned_paperwork
        ),

        "date_review_queue": date_review_queue,
        "date_review_ai_calls": date_review_ai_calls,

        "date_review_ai_errors": date_review_ai_errors,

        "parse_errors": errors,

        "orphan_acks": orphan_acks,

        "note": (
            "All paperwork results are provisional "
            "because scanned-document extraction "
            "has not been independently verified. "
            "Missing messages or acknowledgements "
            "in supplied folders do not prove "
            "regulatory reporting failures. "
            "AA indicates application acceptance, "
            "not confirmed downstream reporting."
        ),
    }
