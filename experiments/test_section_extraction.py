
from pathlib import Path
from pprint import pprint

from src.docurecon.section_extractor import (
    extract_sections,
)

ROOT = Path(__file__).resolve().parents[1]

PDF = (
    ROOT
    / "sample_data"
    / "paperwork"
    / "DocuRecon_SYNTHETIC_937_SYN-937-002.pdf"
)


def main():
    result = extract_sections(PDF)

    print("\nDocuRecon Section-Level Extraction")
    print("----------------------------------")

    pprint(result)


if __name__ == "__main__":
    main()
