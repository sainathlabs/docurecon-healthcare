from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from docurecon.parsers.paperwork_parser import extract_folder, _standard_date, _standard_time

ROOT=Path(__file__).resolve().parents[1]

def test_date_and_time_normalization():
    assert _standard_date('Date: 11/12/2026')=='2026-11-12'
    assert _standard_time('Time: 10:12 PM')=='22:12'
    assert _standard_time('no time')==''

def test_all_four_synthetic_scans_open_and_identify():
    result,errors=extract_folder(ROOT/'sample_data'/'paperwork')
    assert not errors
    assert len(result)==4
    assert {x['form_type'] for x in result}=={'9.39','9.37'}
    assert all(x['patient_name'] for x in result)
    assert all(x['extraction_status']=='review_required' for x in result)
