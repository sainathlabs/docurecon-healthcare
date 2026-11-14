import sys
from pathlib import Path
from datetime import date
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'src'))
from docurecon.reconciliation.engine import reconcile, decode_ack, decode_hl7


def test_synthetic_example(tmp_path):
    for folder in ('paperwork','hl7','acknowledgements'):
        (tmp_path/folder).mkdir()
    (tmp_path/'paperwork'/'sample.txt').write_text('Patient ID: TEST-001\nEncounter ID: ENC-001\nLegal Status: 9.39\nCompletion Date: 2026-11-12\n')
    (tmp_path/'hl7'/'outbound.hl7').write_text('MSH|^~\\&|SRC|FAC|DEST|FAC|202611122215||ADT^A01|MSG-001|P|2.5\rPID|||TEST-001||TEST^PATIENT\rPV1|||||||||||||||||||ENC-001\rZLS|9.39|2026-11-12\r')
    (tmp_path/'acknowledgements'/'ack.hl7').write_text('MSH|^~\\&|DEST|FAC|SRC|FAC|202611122216||ACK|ACK-001|P|2.5\rMSA|AA|MSG-001\r')
    result = reconcile(tmp_path, date(2026,11,12))
    assert result['paperwork_count'] == 1
    assert result['hl7_count'] == 1
    assert result['ack_count'] == 1
    assert result['matched'] == 1, result
    assert not result['errors']


def test_scanned_fixture_is_not_assumed_parsed():
    # The current generic parser is intentionally not claimed as a validated OMH extraction method.
    sample_dir=Path(__file__).resolve().parents[1]/'sample_data'/'paperwork'
    assert len(list(sample_dir.glob('*.pdf'))) == 4
