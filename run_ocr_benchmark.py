
import csv
import time
from pathlib import Path

from src.docurecon.parsers.paperwork_parser import extract_paperwork

ROOT = Path(__file__).resolve().parent
PAPERWORK = ROOT / "sample_data" / "paperwork"
OUTPUT = ROOT / "results" / "ocr_baseline.csv"


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    records = []

    pdf_files = sorted(
        PAPERWORK.glob("DocuRecon_SYNTHETIC_*.pdf")
    )

    for pdf in pdf_files:
        print(f"Processing: {pdf.name}", flush=True)

        start = time.perf_counter()

        try:
            result = extract_paperwork(pdf)
            elapsed = round(
                time.perf_counter() - start, 2
            )

            record = {
                "source": pdf.name,
                "method": "tesseract_ocr",
                "elapsed_seconds": elapsed,
                "patient_name": result.get("patient_name", ""),
                "mrn": result.get("mrn", ""),
                "facility": result.get("facility", ""),
                "legal_status": result.get("form_type", ""),
                "completion_date": result.get(
                    "completion_date", ""
                ),
                "completion_time": result.get(
                    "completion_time", ""
                ),
                "extraction_status": result.get(
                    "extraction_status", ""
                ),
                "review_reasons": ";".join(
                    result.get("review_reasons", [])
                ),
                "error": "",
            }

        except Exception as exc:
            record = {
                "source": pdf.name,
                "method": "tesseract_ocr",
                "error": str(exc),
            }
            print(f"ERROR: {exc}")

        records.append(record)

        print(
            "MRN:", record.get("mrn", ""),
            "| Date:", record.get("completion_date", ""),
            "| Time:", record.get("completion_time", ""),
        )

    fields = [
        "source", "method", "elapsed_seconds",
        "patient_name", "mrn", "facility",
        "legal_status", "completion_date",
        "completion_time", "extraction_status",
        "review_reasons", "error",
    ]

    with OUTPUT.open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file, fieldnames=fields
        )
        writer.writeheader()
        writer.writerows(records)

    print(f"\nOCR results saved to: {OUTPUT}")


if __name__ == "__main__":
    main()
