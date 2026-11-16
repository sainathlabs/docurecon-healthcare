from __future__ import annotations
import csv
import hashlib
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "evaluation_dataset" / "independent_test"
manifest = DATA / "ground_truth" / "sha256.txt"
lines = manifest.read_text(encoding="ascii").splitlines()
errors = []
for line in lines:
    expected, relative = line.split(maxsplit=1)
    target = ROOT / relative
    if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest()!=expected:
        errors.append(relative)
with (DATA / "ground_truth" / "case_ground_truth.csv").open(encoding="utf-8", newline="") as f:
    records=list(csv.DictReader(f))
counts = Counter(row["primary_scenario"] for row in records)
print("Ground truth cases:",len(records))
print("Form counts:",dict(Counter(row["legal_status"] for row in records)))
print("Scenario counts:",dict(counts))
print("PDFs:",len(list((DATA/"paperwork").glob("*.pdf"))))
print("HL7:",len(list((DATA/"hl7").glob("*.hl7"))))
print("ACKs:",len(list((DATA/"acknowledgements").glob("*.ack"))))
print("SHA-256 files checked:",len(lines))
print("Checksum mismatches:",len(errors))
if errors: print("MISMATCHES:", errors[:10])
assert len(records)==400 and len(errors)==0
assert sum(row["legal_status"]=="9.37" for row in records)==200
assert sum(row["legal_status"]=="9.39" for row in records)==200
assert len(list((DATA/"paperwork").glob("*.pdf")))==400
assert len(list((DATA/"hl7").glob("*.hl7")))==396
assert len(list((DATA/"acknowledgements").glob("*.ack")))==376
print("Dataset verification: PASSED")
