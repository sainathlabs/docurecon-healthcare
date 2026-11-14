import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from docurecon.parsers.ack_parser import parse_ack_text, parse_ack_folder, link_acknowledgements
from docurecon.parsers.hl7_parser import parse_hl7_folder

ROOT = Path(__file__).resolve().parents[1]

def test_two_synthetic_acks():
    rows, errors = parse_ack_folder(ROOT / 'sample_data' / 'acknowledgements')
    assert errors == []
    assert len(rows) == 2
    assert {r['ack_code'] for r in rows} == {'AA', 'AE'}
    assert next(r for r in rows if r['ack_code'] == 'AE')['error_details']

def test_correlation_and_missing_scenario():
    messages, me = parse_hl7_folder(ROOT / 'sample_data' / 'hl7')
    acks, ae = parse_ack_folder(ROOT / 'sample_data' / 'acknowledgements')
    assert not (me or ae)
    links = link_acknowledgements(messages, acks)
    statuses = {r['outbound_control_id']: r['link_status'] for r in links}
    assert statuses == {'DR-20261112-001': 'ACCEPTED',
                        'DR-20261111-001': 'APPLICATION_ERROR',
                        'DR-20261110-001': 'NO_ACK_IN_SAMPLE'}

def test_unmatched_ack_flagged():
    messages, _ = parse_hl7_folder(ROOT / 'sample_data' / 'hl7')
    rows = link_acknowledgements(messages, [{'control_id':'UNKNOWN', 'source':'orphan.ack','ack_code':'AA'}])
    assert any(r['link_status'] == 'ORPHAN_ACK_NO_OUTBOUND_MESSAGE' for r in rows)

def test_duplicate_ack_flagged():
    messages, _ = parse_hl7_folder(ROOT / 'sample_data' / 'hl7')
    duplicate = [{'control_id':'DR-20261112-001','source':f'{i}.ack','ack_code':'AA'} for i in (1,2)]
    assert 'MULTIPLE_ACKS_FOR_CONTROL_ID' in {r['link_status'] for r in link_acknowledgements(messages,duplicate)}

@pytest.mark.parametrize('code',['AR','AE','AA'])
def test_codes(code):
    sample = f'MSH|^~\\&|A|B|C|D|20261114120000||ACK^A01|ACK1|P|2.5\rMSA|{code}|ORIGINAL123\r'
    assert parse_ack_text(sample)['ack_code'] == code

@pytest.mark.parametrize('raw', [
    'MSA|AA|ORIGINAL123',
    'MSH|^~\\&|A|B|C|D|20261114120000||ACK^A01|ACK1|P|2.5',
    'MSH|^~\\&|A|B|C|D|20261114120000||ADT^A01|X|P|2.5\rMSA|AA|ABC',
    'MSH|^~\\&|A|B|C|D|20261114120000||ACK^A01|X|P|2.5\rMSA|BAD|ABC',
    'MSH|^~\\&|A|B|C|D|20261114120000||ACK^A01|X|P|2.5\rMSA|AA|',
])
def test_bad_acks_rejected(raw):
    with pytest.raises(ValueError):
        parse_ack_text(raw)
