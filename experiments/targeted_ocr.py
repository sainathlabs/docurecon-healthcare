
"""
DocuRecon - Targeted OCR Experiment

Investigates uncertain fields using alternative
Tesseract preprocessing and page segmentation.

Research-only, synthetic documents.
Does not access ground truth or OpenAI predictions.
"""

from pathlib import Path

import pymupdf
import pytesseract
from PIL import ImageEnhance, ImageOps

from src.docurecon.parsers.paperwork_parser import (
    _page_image,
)


ROOT = Path(__file__).resolve().parents[1]
PAPERWORK = ROOT / "sample_data" / "paperwork"


CASES = [
    {
        "label": "Alicia Part C time",
        "filename": (
            "DocuRecon_SYNTHETIC_937_SYN-937-001.pdf"
        ),
        "page_index": 1,
        "region": (360, 650, 612, 740),
    },
    {
        "label": "Elena MRN",
        "filename": (
            "DocuRecon_SYNTHETIC_939_SYN-939-001.pdf"
        ),
        "page_index": 0,
        "region": (340, 85, 612, 165),
    },
]


def examine(case):
    path = PAPERWORK / case["filename"]

    with pymupdf.open(path) as pdf:
        page = pdf[case["page_index"]]

        image = _page_image(
            page,
            region=case["region"],
            scale=4,
        )

    variants = {
        "original": image,
        "grayscale": ImageOps.grayscale(image),
        "contrast": ImageEnhance.Contrast(
            ImageOps.grayscale(image)
        ).enhance(2.0),
    }

    print(f"\n{'=' * 55}")
    print(case["label"])
    print(f"{'=' * 55}")

    for variant_name, variant in variants.items():
        for psm in (6, 7, 11):
            result = pytesseract.image_to_string(
                variant,
                config=f"--psm {psm}",
            ).strip()

            print(
                f"{variant_name:10} "
                f"PSM {psm:2}: {result!r}"
            )


def main():
    for case in CASES:
        examine(case)


if __name__ == "__main__":
    main()
