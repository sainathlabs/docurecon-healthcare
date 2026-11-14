
import re
from datetime import datetime


def normalize_name(value):
    if not value:
        return None
    return re.sub(r"\s+", " ", str(value).strip().upper())


def normalize_mrn(value):
    if not value:
        return None
    return str(value).strip().upper().replace(" ", "")



def normalize_legal_status(value):
    """
    Normalise explicit MHL legal-status references.

    Do not infer legal status from generic phrases
    such as 'Emergency Admission'.
    """
    if not value:
        return None

    text = str(value).upper().strip()

    match = re.search(
        r"(?<!\d)9\s*\.\s*(37|39)(?!\d)",
        text,
    )

    if match:
        return f"9.{match.group(1)}"

    return None




def normalize_date(value):
    if value is None:
        return None

    text = str(value).strip()

    if not text or text.lower() in ("none", "null", "nan"):
        return None

    formats = [
        "%Y-%m-%d",  # 2026-11-12
        "%d-%m-%Y",  # 12-11-2026 (DD-MM-YYYY)
        "%m/%d/%Y",  # 11/12/2026 (MM/DD/YYYY)
        "%Y/%m/%d",  # 2026/11/12
    ]

    for fmt in formats:
        try:
            return datetime.strptime(
                text, fmt
            ).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None



def normalize_time(value):
    if not value:
        return None

    text = str(value).strip().upper()

    for fmt in ("%H:%M", "%I:%M %p", "%I:%M%p"):
        try:
            return datetime.strptime(text, fmt).strftime("%H:%M")
        except ValueError:
            continue

    return None


def normalize_field(field, value):
    handlers = {
        "patient_name": normalize_name,
        "mrn": normalize_mrn,
        "legal_status": normalize_legal_status,
        "completion_date": normalize_date,
        "completion_time": normalize_time,
        "facility": normalize_name,
        "form_type": normalize_name,
    }

    return handlers.get(field, lambda x: x)(value)
