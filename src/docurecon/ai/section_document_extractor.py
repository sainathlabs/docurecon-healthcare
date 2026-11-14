
"""
DocuRecon - Section-Aware AI Extraction v2

Extract section-specific timestamp candidates from
synthetic OMH 474 / 475 research PDFs.

This module does not establish legal completeness
or independently verify physician signatures.

The v1 extractor remains unchanged for benchmarking.
"""

import base64
import json
import time
from pathlib import Path

import pymupdf
from dotenv import load_dotenv
from openai import OpenAI

from experiments.normalize_fields import normalize_field


ROOT = Path(__file__).resolve().parents[3]
SAMPLE_FOLDER = (
    ROOT / "sample_data" / "paperwork"
).resolve()

load_dotenv(ROOT / ".env")

MODEL = "gpt-4.1-mini"
client = OpenAI()


EXTRACTION_PROMPT = """
You are extracting structured information from
a SYNTHETIC scanned New York OMH admission document.

Read the document images only.
Never use filenames or external metadata to infer fields.

Return one JSON object with these keys:

{
  "patient_name": null,
  "mrn": null,
  "facility": null,
  "legal_status": null,
  "form_type": null,
  "sections": {
    "part_c": {
      "date": null,
      "time": null,
      "source_page": null,
      "source_section": null,
      "evidence_text": null
    },
    "physician_signatures": []
  }
}

Rules:

1. legal_status must be "9.37", "9.39", or null.

2. Dates must use YYYY-MM-DD.

3. Times must use HH:MM in 24-hour format.

4. source_page must be a 1-based page number
   referring to the supplied PDF images.

5. For MHL 9.37:
   Find Part C, Physician's Confirmation
   for Immediate Hospitalization.

   Extract ONLY the Part C physician confirmation
   date and time into sections.part_c.

   Do not substitute Part A, Part B, the transport
   timestamp, or a later physician examination.

6. For MHL 9.39:
   Locate all applicable admitting physician
   signature date/time entries.

   For each candidate, add an object to
   sections.physician_signatures:

   {
     "date": null,
     "time": null,
     "source_page": null,
     "source_section": null,
     "evidence_text": null
   }

   Do not select the earliest timestamp yourself.
   Return the candidates for deterministic selection.

7. If a value is unreadable, missing or uncertain,
   use null. Never invent a value.

8. evidence_text should briefly identify the
   visible date/time text and nearby field label.
   If that evidence cannot be read, use null.

9. A printed signature label, typed name or
   timestamp is not proof of a valid signature.

10. Some research samples say
    "SIMULATED - NOT SIGNED".
    Do not treat them as legally signed.

11. Do not return explanations outside the JSON.
"""


def validate_synthetic_path(pdf_path):
    pdf_path = Path(pdf_path).resolve()

    if (
        not pdf_path.is_relative_to(SAMPLE_FOLDER)
        or not pdf_path.name.startswith(
            "DocuRecon_SYNTHETIC_"
        )
        or pdf_path.suffix.lower() != ".pdf"
    ):
        raise ValueError(
            "Only synthetic DocuRecon research PDFs "
            "are permitted."
        )

    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)

    return pdf_path


def clean_timestamp_entry(entry, page_count):
    """Normalise a timestamp candidate without guessing."""

    if not isinstance(entry, dict):
        entry = {}

    page_number = entry.get("source_page")

    try:
        page_number = int(page_number)
    except (TypeError, ValueError):
        page_number = None

    if (
        page_number is None
        or not 1 <= page_number <= page_count
    ):
        page_number = None

    date = normalize_field(
        "completion_date",
        entry.get("date"),
    )

    time_value = normalize_field(
        "completion_time",
        entry.get("time"),
    )

    return {
        "date": date,
        "time": time_value,
        "source_page": page_number,
        "source_section": entry.get(
            "source_section"
        ),
        "evidence_text": entry.get(
            "evidence_text"
        ),
        "signature_present": None,
        "signature_status": "unverified",
        "extraction_method": "openai_vision_v2",
    }


def extract_document_v2(pdf_path):
    pdf_path = validate_synthetic_path(pdf_path)

    content = [{
        "type": "input_text",
        "text": EXTRACTION_PROMPT,
    }]

    with pymupdf.open(pdf_path) as pdf:
        page_count = len(pdf)

        if page_count == 0:
            raise ValueError("Empty PDF document.")

        for page in pdf:
            pixmap = page.get_pixmap(
                matrix=pymupdf.Matrix(1.6, 1.6),
                alpha=False,
            )

            encoded = base64.b64encode(
                pixmap.tobytes("png")
            ).decode("ascii")

            content.append({
                "type": "input_image",
                "image_url": (
                    f"data:image/png;base64,{encoded}"
                ),
                "detail": "high",
            })

    start = time.perf_counter()

    response = client.responses.create(
        model=MODEL,
        input=[{
            "role": "user",
            "content": content,
        }],
        text={
            "format": {
                "type": "json_object"
            }
        },
        store=False,
    )

    elapsed = round(
        time.perf_counter() - start,
        2,
    )

    raw = json.loads(response.output_text)

    if not isinstance(raw, dict):
        raise ValueError(
            "AI response must be a JSON object."
        )

    legal_status = normalize_field(
        "legal_status",
        raw.get("legal_status"),
    )

    raw_sections = raw.get("sections") or {}

    if not isinstance(raw_sections, dict):
        raw_sections = {}

    sections = {
        "part_c": {},
        "physician_signatures": [],
    }

    if legal_status == "9.37":
        sections["part_c"] = clean_timestamp_entry(
            raw_sections.get("part_c"),
            page_count,
        )

    elif legal_status == "9.39":
        candidates = raw_sections.get(
            "physician_signatures"
        ) or []

        if not isinstance(candidates, list):
            candidates = []

        sections["physician_signatures"] = [
            clean_timestamp_entry(
                candidate,
                page_count,
            )
            for candidate in candidates
        ]

    review_reasons = [
        "AI_VALUES_REQUIRE_VERIFICATION",
        "SIGNATURE_STATUS_UNVERIFIED",
    ]

    return {
        "source": pdf_path.name,
        "model": MODEL,
        "extraction_version": "v2_section_aware",
        "elapsed_seconds": elapsed,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "patient_name": normalize_field(
            "patient_name",
            raw.get("patient_name"),
        ),
        "mrn": normalize_field(
            "mrn",
            raw.get("mrn"),
        ),
        "facility": normalize_field(
            "facility",
            raw.get("facility"),
        ),
        "legal_status": legal_status,
        "form_type": raw.get("form_type"),
        "sections": sections,
        "review_reasons": review_reasons,
    }


if __name__ == "__main__":
    sample = (
        SAMPLE_FOLDER
        / "DocuRecon_SYNTHETIC_937_SYN-937-002.pdf"
    )

    result = extract_document_v2(sample)

    print(json.dumps(result, indent=2))
