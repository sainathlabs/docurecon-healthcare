# Synthetic HL7 acknowledgement profile (Step 4)

This document describes the *illustrative* ACK messages shipped with DocuRecon. They are not facility-specific mappings and must not be treated as a validated NICS acknowledgement profile.

- `MSH-9`: `ACK^A01` in this test dataset.
- `MSH-10`: unique identifier of the acknowledgement message itself.
- `MSH-7`: acknowledgement timestamp (`YYYYMMDDHHMMSS`), assumed local time for the sample only.
- `MSA-1`: application acknowledgement code (`AA` accepted, `AE` application error, `AR` rejected).
- `MSA-2`: **original outbound message** `MSH-10` being acknowledged. This is the correlation key.
- `MSA-3`: optional application message text.
- `ERR`: optional error detail; preserved as free text.

## Synthetic scenarios

| Outbound MSH-10 | Expected result | Synthetic ACK file |
| --- | --- | --- |
| `DR-20261112-001` (Elena) | `AA`, application accepted | `SYN-939-001_AA.ack` |
| `DR-20261111-001` (Alicia) | `AE`, application error | `SYN-937-001_AE.ack` |
| `DR-20261110-001` (Jordan) | No ACK file in this limited dataset | None |

No outbound HL7 file exists for Marcus, so no ACK is expected for that missing-message test scenario.

The app's Step 4 section links acknowledgements to messages and flags `NO_ACK_IN_SAMPLE`, duplicate ACKs and orphan ACKs. **This is linkage only, not full daily paperwork-to-HL7-to-ACK reconciliation.** In real interfaces, enhanced-mode acknowledgements (`CA`, `CE`, `CR`) and repeats/multiple `MSA` responses may need additional handling. For the first dataset, only original-mode `AA`, `AE`, `AR` are accepted; other codes produce explicit parsing errors.

An `AA` response is not equivalent to confirmed downstream NICS/regulatory reporting. An absent ACK file is not proof of a missing ACK until the source channel, polling interval, timeout window, and retrieval completeness are established.
