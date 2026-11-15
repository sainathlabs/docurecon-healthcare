
"""
DocuRecon synthetic HL7 and ACK pilot generator.

Reads the existing 10-case pilot ground truth.
Generates controlled HL7/ACK scenarios.

All records are fictional.
Research use only.
"""

import csv
from datetime import datetime, timedelta
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[2]

ROOT = PROJECT / "evaluation_dataset" / "pilot_form_based"
HL7_DIR = ROOT / "hl7"
ACK_DIR = ROOT / "acknowledgements"

GROUND_TRUTH = (
    PROJECT / "evaluation_dataset"
    / "manifests"
    / "pilot_form_based_ground_truth.csv"
)

SCENARIO_FILE = (
    PROJECT / "evaluation_dataset"
    / "manifests" / "pilot_reconciliation_scenarios.csv"
)

SCENARIOS = {
    1: ("MATCH_AA", "AA"),
    2: ("MATCH_AA", "AA"),
    3: ("APPLICATION_ERROR", "AE"),
    4: ("NO_HL7_IN_SAMPLE", None),
    5: ("MRN_MISMATCH", "AA"),
    6: ("MATCH_AA", "AA"),
    7: ("NO_ACK_IN_SAMPLE", None),
    8: ("COMPLETION_TIME_MISMATCH", "AA"),
    9: ("DUPLICATE_CANDIDATES", "AA"),
    10: ("APPLICATION_REJECTED", "AR"),
}


def hl7_timestamp(value):
    return value.strftime("%Y%m%d%H%M%S")


def build_hl7(case, control_id, variant=1):
    patient = case["patient_name"]
    last, first = [
        value.strip()
        for value in patient.split(",", 1)
    ]

    number = int(case["mrn"].split("-")[-1])

    completed = datetime.strptime(
        case["completion_date"] + " "
        + case["completion_time"],
        "%Y-%m-%d %H:%M",
    )

    message_time = completed + timedelta(minutes=10)
    recorded_completion = completed

    if number == 8:
        recorded_completion += timedelta(minutes=20)

    mrn = case["mrn"]

    if number == 5:
        mrn = "SYN-PILOT-9995"

    control_id = str(control_id)

    segments = [
        (
            "MSH|^~\\&|DOCURECON|SYNTHETIC_FACILITY|"
            "TEST_RECEIVER|TEST|"
            f"{hl7_timestamp(message_time)}||ADT^A01|"
            f"{control_id}|P|2.5"
        ),
        (
            "PID|1||"
            f"{mrn}^^^SYNTHETIC^MR||{last}^{first}"
        ),
        (
            "PV1|1|I|||||||||||||||||"
            f"ENC-PILOT-{number:04d}-{variant}"
        ),
        (
            f"ZLS|{case['legal_status']}|"
            f"{recorded_completion:%Y%m%d}|"
            f"{recorded_completion:%H%M}"
        ),
    ]

    return "\r".join(segments) + "\r"


def build_ack(control_id, code, completed, sequence):
    descriptions = {
        "AA": "Application accepted",
        "AE": "Application error",
        "AR": "Application rejected",
    }

    ack_time = completed + timedelta(minutes=12)

    segments = [
        (
            "MSH|^~\\&|TEST_RECEIVER|TEST|"
            "DOCURECON|SYNTHETIC_FACILITY|"
            f"{hl7_timestamp(ack_time)}||ACK^A01|"
            f"ACK-PILOT-{sequence:04d}|P|2.5"
        ),
        (
            f"MSA|{code}|{control_id}|"
            f"{descriptions[code]}"
        ),
    ]

    return "\r".join(segments) + "\r"


def main():
    if not GROUND_TRUTH.is_file():
        raise FileNotFoundError(
            f"Ground truth not found: {GROUND_TRUTH}"
        )

    with GROUND_TRUTH.open(
        newline="", encoding="utf-8-sig"
    ) as file:
        cases = list(csv.DictReader(file))

    if len(cases) != 10:
        raise ValueError(
            f"Expected 10 pilot cases, found {len(cases)}"
        )

    HL7_DIR.mkdir(parents=True, exist_ok=True)
    ACK_DIR.mkdir(parents=True, exist_ok=True)

    # Never overwrite existing research outputs.
    if (
        list(HL7_DIR.iterdir())
        or list(ACK_DIR.iterdir())
        or SCENARIO_FILE.exists()
    ):
        raise FileExistsError(
            "Pilot HL7/ACK output already exists. "
            "Preserve existing research samples."
        )

    summary = []
    ack_sequence = 1

    for index, case in enumerate(cases, start=1):
        expected_mrn = f"SYN-PILOT-{index:04d}"

        if case["mrn"] != expected_mrn:
            raise ValueError(
                f"Unexpected MRN for case {index}"
            )

        scenario, ack_code = SCENARIOS[index]

        completed = datetime.strptime(
            case["completion_date"] + " "
            + case["completion_time"],
            "%Y-%m-%d %H:%M",
        )

        controls = []

        if index != 4:
            variants = 2 if index == 9 else 1

            for variant in range(1, variants + 1):
                control_id = (
                    f"DR-PILOT-{index:04d}-{variant}"
                )

                controls.append(control_id)

                hl7_file = (
                    HL7_DIR
                    / f"PILOT-{index:04d}-{variant}.hl7"
                )

                hl7_file.write_bytes(
                    build_hl7(
                        case, control_id, variant
                    ).encode("utf-8")
                )

                if ack_code:
                    ack_file = (
                        ACK_DIR
                        / f"PILOT-{index:04d}-{variant}_{ack_code}.ack"
                    )

                    ack_file.write_bytes(
                        build_ack(
                            control_id,
                            ack_code,
                            completed,
                            ack_sequence,
                        ).encode("utf-8")
                    )

                    ack_sequence += 1

        summary.append({
            "case_id": f"PILOT-{index:04d}",
            "document": case["document"],
            "scenario": scenario,
            "paperwork_mrn": case["mrn"],
            "hl7_control_ids": ";".join(controls),
            "expected_ack_code": ack_code or "",
            "expected_link": (
                "NO_CANDIDATE"
                if index == 4
                else "AMBIGUOUS"
                if index == 9
                else "NAME_ONLY_UNCERTAIN"
                if index == 5
                else "CANDIDATE"
            ),
        })

    SCENARIO_FILE.parent.mkdir(
        parents=True, exist_ok=True
    )

    with SCENARIO_FILE.open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(summary[0].keys()),
        )
        writer.writeheader()
        writer.writerows(summary)

    print("\nDocuRecon HL7/ACK pilot generated")
    print("=" * 45)
    print("Pilot cases:", len(cases))
    print("HL7 messages:", len(list(HL7_DIR.glob("*.hl7"))))
    print("ACK files:", len(list(ACK_DIR.glob("*.ack"))))
    print("Scenario manifest:", SCENARIO_FILE)


if __name__ == "__main__":
    main()
