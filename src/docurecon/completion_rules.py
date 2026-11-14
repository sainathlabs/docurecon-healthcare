
"""
DocuRecon - Legal Status Completion Rules

Select the relevant completion timestamp based on
the document's legal admission status.

This module does not perform OCR or AI extraction.
It operates on already-extracted structured data.

All timestamps are assumed to be local facility time.
"""

from datetime import datetime


def parse_timestamp(date_value, time_value):
    """
    Convert ISO date and 24-hour time into datetime.

    Example:
        2026-11-10, 12:42
    """
    if not date_value or not time_value:
        return None

    try:
        return datetime.strptime(
            f"{date_value} {time_value}",
            "%Y-%m-%d %H:%M",
        )
    except (ValueError, TypeError):
        return None


def select_completion_timestamp(legal_status, sections):
    """
    Select the required completion timestamp.

    For 9.37:
        Use Part C physician confirmation.

    For 9.39:
        Select the earliest applicable completed
        physician signature timestamp.

    Expected section structure:

    {
        "part_c": {
            "date": "2026-11-10",
            "time": "12:42",
            "signature_present": True
        },
        "physician_signatures": [
            {
                "date": "2026-11-12",
                "time": "22:12",
                "signature_present": True
            }
        ]
    }
    """

    if legal_status == "9.37":
        part_c = sections.get("part_c", {})

        if not part_c.get("signature_present"):
            return {
                "status": "incomplete",
                "timestamp": None,
                "reason": "Part C physician signature missing",
            }

        timestamp = parse_timestamp(
            part_c.get("date"),
            part_c.get("time"),
        )

        if timestamp is None:
            return {
                "status": "incomplete",
                "timestamp": None,
                "reason": "Part C date or time invalid",
            }

        return {
            "status": "complete",
            "timestamp": timestamp.isoformat(timespec="minutes"),
            "reason": "9.37 Part C physician confirmation",
        }

    if legal_status == "9.39":
        candidates = []

        for signature in sections.get(
            "physician_signatures", []
        ):
            if not signature.get("signature_present"):
                continue

            timestamp = parse_timestamp(
                signature.get("date"),
                signature.get("time"),
            )

            if timestamp is not None:
                candidates.append(timestamp)

        if not candidates:
            return {
                "status": "incomplete",
                "timestamp": None,
                "reason": (
                    "No completed physician signature "
                    "with valid date and time"
                ),
            }

        earliest = min(candidates)

        return {
            "status": "complete",
            "timestamp": earliest.isoformat(timespec="minutes"),
            "reason": "9.39 earliest physician signature",
        }

    return {
        "status": "unsupported",
        "timestamp": None,
        "reason": f"Unsupported legal status: {legal_status}",
    }
