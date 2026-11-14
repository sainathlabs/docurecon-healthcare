# Synthetic paperwork fixtures

Four **image-only PDFs** based on the user's supplied New York OMH form layouts.

- Two 9.39 / OMH 474 examples (two scanned pages each).
- Two 9.37 / OMH 475 + 475A examples (three scanned pages each).
- `ground_truth.csv` records known synthetic identities, legal status and completion timestamps.

All names, MRNs, clinicians, hospitals and narratives are fictional. Any signature is marked simulated/not signed. These are research fixtures, **not usable clinical or legal documents**.

The current application does **not yet decode these scanned form layouts reliably**. This is the next development task. Do not calculate reconciliation recall from these fixtures until an independently verified extraction and source-to-HL7 mapping exists.
