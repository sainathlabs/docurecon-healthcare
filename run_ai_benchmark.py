
import csv
import json
from pathlib import Path

from src.docurecon.ai.document_extractor import extract_document

ROOT = Path(__file__).resolve().parent
PAPERWORK = ROOT / "sample_data" / "paperwork"
OUTPUT = ROOT / "ai_benchmark_results.csv"

records = []

for pdf in sorted(PAPERWORK.glob("DocuRecon_SYNTHETIC_*.pdf")):
    print(f"Processing: {pdf.name}", flush=True)

    try:
        result = extract_document(pdf)

        record = {
            "source": pdf.name,
            "model": result["model"],
            "elapsed_seconds": result["elapsed_seconds"],
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
            **result["extracted_fields"],
        }

        records.append(record)

        print(json.dumps(record, indent=2))

    except Exception as exc:
        print(f"ERROR processing {pdf.name}: {exc}")

if records:
    fieldnames = list(dict.fromkeys(
        key for record in records for key in record
    ))

    with OUTPUT.open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames
        )
        writer.writeheader()
        writer.writerows(records)

    print(f"\nResults saved to: {OUTPUT}")
