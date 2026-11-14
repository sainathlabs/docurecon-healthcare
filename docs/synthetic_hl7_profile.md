# Step 3: Synthetic HL7 ADT profile (research fixture only)

This profile is **not** an official NICS specification or a production HL7 interface mapping. Facility HL7 implementations must be separately documented and validated before any operational deployment.

The sample outbound messages use HL7 v2.5 ER7 syntax with segments separated by carriage returns (`\r`). The demo recognises **one ADT message per file**:

| Field | Meaning |
|---|---|
| `MSH-7` | Outbound message timestamp, `YYYYMMDDHHMMSS` |
| `MSH-9` | `ADT^A01` (synthetic admission event) |
| `MSH-10` | Unique message control identifier for future ACK matching |
| `PID-3` | Synthetic MRN (first CX component) |
| `PID-5` | Synthetic name; display-only, not a primary matching key |
| `PV1-19` | Synthetic encounter number (first CX component) |
| `ZLS-1` | **CUSTOM** legal status `9.39` or `9.37` |
| `ZLS-2` | **CUSTOM** paperwork completion date, `YYYYMMDD` |
| `ZLS-3` | **CUSTOM** paperwork completion time, `HHMM`, local clock time |

`ZLS` is a **fictional research-specific custom Z-segment**. Actual HL7 feeds may represent these fields differently or not at all. Timestamps are local without explicit timezone, and no reporting-timeliness claim is made.

## Controlled scenarios

| Paperwork fixture | HL7 fixture | Expected situation |
|---|---|---|
| `SYN-939-001` Elena Martinez | `SYN-939-001.hl7` | Correct legal status and timestamp |
| `SYN-939-002` Marcus Bell | No HL7 file | Deliberately absent synthetic outbound file |
| `SYN-937-001` Alicia Brooks | `SYN-937-001.hl7` | Deliberate legal-status mismatch: HL7 is `9.39`, paperwork is `9.37` |
| `SYN-937-002` Jordan Ellis | `SYN-937-002.hl7` | Correct legal status and timestamp |

Current OCR errors mean these ground-truth expected scenarios **cannot yet be claimed to have been automatically detected from scanned PDFs**. The standalone parser merely confirms structured HL7 parsing works.

Run tests with `python -m pytest -q`.
