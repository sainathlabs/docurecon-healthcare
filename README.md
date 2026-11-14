# DocuRecon

**Healthcare Documentation and HL7 Reconciliation Framework**

Early-stage, synthetic-data-only research prototype to support daily comparisons between scanned involuntary paperwork, outbound HL7 messages, and ACK/NACK responses.

## Repository layout

```text
docurecon-healthcare/
├── app.py
├── src/docurecon/
│   ├── parsers/
│   ├── reconciliation/engine.py
│   └── reports/
├── tests/
├── sample_data/
│   ├── paperwork/         # 4 synthetic OMH scanned PDFs + ground truth
│   ├── hl7/               # 3 synthetic HL7 ADT messages
│   └── acknowledgements/  # 2 synthetic ACKs (AA, AE); one intentionally absent
├── docs/
├── requirements.txt
├── README.md
├── LICENSE
└── .gitignore
```

## Run on Windows

```powershell
cd docurecon-healthcare
py -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
streamlit run app.py
```

Choose the paperwork completion date; the app reads the three sample-data folders. You can also use the three UI file-upload controls to add local files. Click **Run reconciliation** to see a summary and CSV exception output.

## What works now

- Local Streamlit date selection and three folder/file upload inputs.
- Minimal, illustrative HL7 v2 MSH/PID/PV1 + *synthetic custom ZLS* message parser.
- ACK matching via `MSA-2` versus outbound `MSH-10`; basic AA/AE/AR checks.
- Prototype comparison results and CSV download.
- Four **image-only scanned OMH sample PDFs** for subsequent OCR development.

## What does NOT work yet

The included OMH 474 and 475 forms **are not yet supported by the generic document field parser**. Running the current app on only these PDFs will yield parsing errors / zero matched records, not validated reconciliation results. Installing Tesseract only supplies OCR; it does not provide the needed form-specific field mapping. Real HL7 interface mappings, matching policy, time-zone handling, message retries, documentation completion event rules, scanned-form data accuracy and Excel workbook exports are also not implemented. These are planned work, not completed features.

The input date is a **paperwork completion date**, not the date when acknowledgements arrived. The research-specific `ZLS` segment used in the generic engine is **not a standard HL7/NICS interface mapping**. ACK acceptance does not prove successful downstream reporting.

## Test

```bash
python -m pytest -q
```

## Safety and research boundaries

All sample names, MRNs and facilities are fictional. Do not place identifiable patient records, real HL7 messages or restricted employer material in a public repository. The local app is not validated for operational healthcare use. Any future facility evaluation requires authorisation, data handling controls and documented independent validation. The MIT license applies only to code you have rights to distribute; confirm any third-party template reuse rights separately.

## Step 2 update: scanned-paperwork OCR

An experimental parser is included at `src/docurecon/parsers/paperwork_parser.py`.
The Streamlit page offers **Extract fields from paperwork PDFs** and an unverified OCR CSV export. It operates on the image-only synthetic sample PDFs; Tesseract OCR must be installed separately on Windows (`tesseract --version`).

**Do not treat the OCR table as verified.** Some sample identifiers and times are misread. All records are marked `review_required`; this parser is intentionally **not** yet connected to automatic missing-HL7 classifications. See [docs/paperwork_ocr.md](docs/paperwork_ocr.md).

## Step 3: synthetic HL7 ADT parser

Three **fictional, research-only** HL7 v2.5 ADT messages are included under `sample_data/hl7/`. Use the **Parse HL7 files** button in Streamlit to view parsed fields and export a CSV. One of four paper patients deliberately has no message, and one transmitted message deliberately has the wrong legal status. This is a *controlled test design*, not a validated detection result. The `ZLS` segment is a synthetic custom mapping; refer to [docs/synthetic_hl7_profile.md](docs/synthetic_hl7_profile.md).

**Note:** The earlier **Run reconciliation** section still uses the older prototype engine, which cannot reliably map the scanned form images. Do not interpret that section's output as validated discrepancies; the Step 3 parser is independent of OCR and reconciliation.

## Step 4: synthetic ACK/NACK parsing and linkage

The **Parse ACK/NACK files** button reads synthetic acknowledgement messages, classifies `MSA-1` and matches `MSA-2` against outbound `MSH-10`. It flags accepted/error and **no ACK in sample** results separately, and exports parsed ACK and linkage CSV files. The test dataset includes AA for Elena, AE for Alicia, and no ACK file for Jordan. See [docs/synthetic_ack_profile.md](docs/synthetic_ack_profile.md).

These Step 4 results do **not** incorporate unverified OCR and are not regulatory reporting determinations. No mandatory manual verification UI is introduced. The original `Run reconciliation` section is still a legacy prototype and **must not** be treated as a validated workflow.

## Step 5: One-click daily reconciliation (synthetic evaluation)

1. Install requirements: `py -m pip install -r requirements.txt`.
2. Install the Tesseract **executable** and add it to Windows PATH.
3. Run `py -m streamlit run app.py`.
4. Select a **paperwork completion date** (for example, 2026-11-12),
   add PDF/HL7/ACK files to the three folders (or upload them), then click
   **Run Daily Reconciliation**.
5. Review provisional outcomes and download CSV. Use the Developer tools expander
   to inspect intermediate OCR, HL7, and acknowledgement parsing.

**Limitations:** The supplied OMH PDFs are raster scans. OCR is experimental;
its identifiers, dates, and times are NOT considered independently verified.
The daily engine deliberately produces `PROVISIONAL_MATCH`,
`PROVISIONAL_EXCEPTION`, or `OCR_UNCERTAIN`, rather than confirmed regulatory
violations. Empty or incomplete input folders cannot establish missing HL7/ACK.
The matching of names is a *candidate search*, not proof of identity.
This early prototype does not support real facility profiles, regulatory
reporting deadlines, retry windows, or clinical/legal validity checking.
Do not upload real patient or employer data to public GitHub.

The synthetic scenario samples occur on **different paperwork completion dates**.
For example, choose 2026-11-11 for Alicia, 2026-11-12 for Elena,
2026-11-10 for Jordan, and 2026-11-13 for Marcus. This is intentional:
selecting a single date should not count all four paperwork records.
