import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from docurecon.parsers.hl7_parser import parse_hl7_file, parse_hl7_folder, parse_hl7_text

ROOT = Path(__file__).resolve().parents[1]


def test_three_synthetic_messages_parse():
    rows, errors = parse_hl7_folder(ROOT / 'sample_data' / 'hl7')
    assert not errors
    assert len(rows) == 3
    assert {row['patient_id'] for row in rows} == {'SYN-939-001', 'SYN-937-001', 'SYN-937-002'}
    assert len({row['control_id'] for row in rows}) == 3


def test_known_intentional_mismatch():
    row = parse_hl7_file(ROOT / 'sample_data' / 'hl7' / 'SYN-937-001.hl7')
    assert row['legal_status'] == '9.39'  # paperwork ground truth: 9.37
    assert row['completion_timestamp'] == '2026-11-11T19:35'
    assert row['encounter_id'] == 'ENC-937-001'


def test_no_message_for_missing_case():
    rows, _ = parse_hl7_folder(ROOT / 'sample_data' / 'hl7')
    assert 'SYN-939-002' not in {row['patient_id'] for row in rows}


def test_invalid_messages_flagged():
    try:
        parse_hl7_text('MSH|^~\\&|SOURCE|FAC|DEST|FAC|202611122225||ADT^A01|X|P|2.5\rPID|||TEST')
    except ValueError as exc:
        assert 'Missing PV1' in str(exc)
    else:
        raise AssertionError('Missing segment not rejected')
