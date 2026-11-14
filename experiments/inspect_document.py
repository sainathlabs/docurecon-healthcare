
"""
DocuRecon - Document Image Inspection

Render synthetic PDF pages as high-resolution
PNG images for targeted extraction development.

No OpenAI API calls.
"""

from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:
    import fitz


ROOT = Path(__file__).resolve().parents[1]

PDF_PATH = (
    ROOT
    / "sample_data"
    / "paperwork"
    / "DocuRecon_SYNTHETIC_937_SYN-937-002.pdf"
)

OUTPUT_DIR = ROOT / "results" / "debug" / "jordan"


def main():
    if not PDF_PATH.exists():
        raise FileNotFoundError(PDF_PATH)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with fitz.open(PDF_PATH) as document:
        print(f"\nDocument: {PDF_PATH.name}")
        print(f"Pages: {len(document)}")

        for index, page in enumerate(document):
            pixmap = page.get_pixmap(
                matrix=fitz.Matrix(3, 3),
                alpha=False,
            )

            output = (
                OUTPUT_DIR
                / f"page_{index + 1}.png"
            )

            pixmap.save(str(output))

            print(f"Saved: {output}")

    print("\nDocument rendering complete.")


if __name__ == "__main__":
    main()
