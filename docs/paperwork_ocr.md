# Step 2: Synthetic paperwork OCR

The early parser reads the supplied image-only scanned PDFs with PyMuPDF and Tesseract. It recognizes reduced synthetic OMH 474 (MHL §9.39) and OMH 475 Part A / Part C / OMH 475A (MHL §9.37) examples, then extracts provisional patient name, MRN, facility, legal status, and physician completion timestamp. This is NOT yet a general-purpose official OMH parser.

- 9.39: admission record's *admitting physician* date/time; not arrival date or later psychiatrist confirmation.
- 9.37: *Form 475 Part C physician confirmation* date/time; not DCS/designee application or Form 475A date/time.
- OCR can misread identifiers and timestamps. Results always state `review_required` and must not be automatically passed to HL7 matching.
- No physician signature authenticity or clinical/legal correctness checks are implemented.
- A missing form, poor scan, or unreadable region is an OCR review task, not proof that reporting was missed.
- The sample ground truth is *evaluation-only*. The parser reads the pixels and does not use the ground-truth CSV or filenames to fill fields.

## Windows Tesseract installation

Install the open-source **Tesseract OCR executable** in addition to `pip install -r requirements.txt`. Add its installation directory to Windows PATH. Run `tesseract --version` in a new terminal to verify. No cloud OCR or remote patient-data upload is used.

## How to test

Run `python -m pytest -q`, then `streamlit run app.py`. Click **Extract fields from paperwork PDFs** and inspect the table, including the review flags. The application saves nothing to GitHub automatically.

## Next improvements before real pilot

Form-aligned OCR region detection, repeated OCR voting, explicit field-level confidence, independent OCR validation against the synthetic ground truth, multi-page packet identity checking, date/time semantics, manual verification UI, audit logging and authorisation/security controls.
