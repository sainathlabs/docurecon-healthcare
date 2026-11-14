
import os
import json
import base64
import time
from pathlib import Path

import pymupdf
from dotenv import load_dotenv
from openai import OpenAI

# Project configuration
ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / ".env")

client = OpenAI()

MODEL = "gpt-4.1-mini"


def extract_document(pdf_path):
    pdf_path = Path(pdf_path).resolve()
    sample_folder = (ROOT / "sample_data" / "paperwork").resolve()

    # Safety: only use our synthetic research samples
    if (
        not pdf_path.is_relative_to(sample_folder)
        or not pdf_path.name.startswith("DocuRecon_SYNTHETIC_")
    ):
        raise ValueError("Only synthetic research PDFs are permitted.")

    content = [{
        "type": "input_text",
        "text": """
        Extract information from this scanned synthetic OMH form.

        Return a JSON object containing:
        patient_name, mrn, facility, legal_status,
        form_type, completion_date, completion_time.

        Instructions:
        - Read the actual document, not the filename.
        - Do not guess missing information.
        - Use null for unreadable or missing fields.
        - Format dates as YYYY-MM-DD.
        - Format times as HH:MM (24-hour format).
        - For 9.39, use the admitting physician's
          completion date/time in the admission record.
        - For 9.37, use the hospital physician's
          Part C confirmation date/time.
        - Do not use a later examination date or
          unrelated timestamp as the completion date.
        """
    }]

    with pymupdf.open(pdf_path) as pdf:
        for page in pdf:
            pix = page.get_pixmap(
                matrix=pymupdf.Matrix(1.6, 1.6),
                alpha=False
            )
            image = pix.tobytes("png")
            encoded = base64.b64encode(image).decode()

            content.append({
                "type": "input_image",
                "image_url": f"data:image/png;base64,{encoded}",
                "detail": "high"
            })

    start = time.perf_counter()

    response = client.responses.create(
        model=MODEL,
        input=[{"role": "user", "content": content}],
        text={"format": {"type": "json_object"}},
        store=False
    )

    elapsed = round(time.perf_counter() - start, 2)

    result = json.loads(response.output_text)

    return {
        "model": MODEL,
        "source": pdf_path.name,
        "elapsed_seconds": elapsed,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "extracted_fields": result
    }


if __name__ == "__main__":
    sample = ROOT / "sample_data" / "paperwork" / (
        "DocuRecon_SYNTHETIC_939_SYN-939-001.pdf"
    )

    result = extract_document(sample)
    print(json.dumps(result, indent=2))
