# Six-week implementation roadmap

1. Define form fields, match rules, acknowledgment classes, date/time semantics.
2. Implement validated OMH 474/475 scan extraction and HL7/ACK parsers.
3. Reconcile paperwork, messages and acknowledgments, with traceable exceptions.
4. Refine date selector, three-folder input, metrics and Excel export.
5. Add synthetic ground truth and controlled failure cases; measure precision and recall.
6. Publish documentation, reproducible tests, screenshots and research demonstration.

Current status: folder scaffold + initial local Streamlit UI + simple generic HL7 reconciliation engine + four scanned paperwork fixtures. Not a validated facility pilot.

## Step 5 (implemented): Daily reconciliation

The Streamlit main screen now offers a date selector, three folder inputs,
and one Run Daily Reconciliation button. Classification is conservative:
all paperwork comparisons are provisional until extraction is validated.
Input files spanning multiple dates remain in the searched HL7/ACK sets, but
only paperwork for the selected date enters daily reconciliation. A paper with
an unreadable date is explicitly listed as uncertain.
