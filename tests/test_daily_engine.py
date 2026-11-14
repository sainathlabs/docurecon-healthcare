from datetime import date
from pathlib import Path
from unittest.mock import patch
from docurecon.reconciliation.daily_engine import run_daily

ROOT = Path(__file__).resolve().parents[1] / 'sample_data'


def paper(name, mrn, form, day, tm='12:42'):
    return {'source':name+'.pdf', 'patient_name':name, 'mrn':mrn,
            'form_type':form, 'completion_date':day, 'completion_time':tm,
            'review_reasons':['OCR_VALUES_REQUIRE_HUMAN_VERIFICATION']}


def msg(name, mrn, control, form, ts):
    return {'source':name+'.hl7','patient_name':name.replace(', ','^'),
            'patient_id':mrn,'control_id':control,'legal_status':form,
            'completion_timestamp':ts,'transmitted_at':ts+':00'}


def ack(control, klass, tm):
    return {'source':control+'.ack','control_id':control,'ack_code':'AA' if klass=='ACCEPTED' else 'AE',
            'ack_class':klass, 'received_at':tm}


def run_mock(papers, messages, acks, selected=date(2026,11,12)):
    with patch('docurecon.reconciliation.daily_engine.extract_folder', return_value=(papers,[])), \
         patch('docurecon.reconciliation.daily_engine.parse_hl7_folder',return_value=(messages,[])), \
         patch('docurecon.reconciliation.daily_engine.parse_ack_folder',return_value=(acks,[])):
        return run_daily(ROOT,selected)


def test_matched_remains_provisional():
    p=[paper('MARTINEZ, ELENA','SYN-939-001','9.39','2026-11-12','22:12')]
    m=[msg('MARTINEZ, ELENA','SYN-939-001','C1','9.39','2026-11-12T22:12')]
    a=[ack('C1','ACCEPTED','2026-11-12T22:26:00')]
    result=run_mock(p,m,a)
    assert result['provisional_matches']==1
    assert result['rows'][0]['status']=='PROVISIONAL_MATCH'


def test_wrong_mrn_name_fallback_not_confirmed_missing():
    p=[paper('MARTINEZ, ELENA','SYN-939-004','9.39','2026-11-12','22:12')]
    m=[msg('MARTINEZ, ELENA','SYN-939-001','C1','9.39','2026-11-12T22:12')]
    result=run_mock(p,m,[])
    assert result['rows'][0]['status']=='OCR_UNCERTAIN'
    assert result['rows'][0]['match_method']=='PATIENT_NAME_ONLY'
    assert 'NO_HL7_CANDIDATE' not in result['rows'][0]['issues']


def test_no_matching_hl7_is_unconfirmed_absence():
    result=run_mock([paper('BELL, MARCUS','SYN-939-002','9.39','2026-11-12')],[],[])
    assert result['rows'][0]['status']=='OCR_UNCERTAIN'
    assert 'NO_HL7_CANDIDATE_IN_SUPPLIED_FILES' in result['rows'][0]['issues']


def test_legal_status_mismatch_and_ack_error():
    p=[paper('BROOKS, ALICIA','SYN-937-001','9.37','2026-11-12','19:35')]
    m=[msg('BROOKS, ALICIA','SYN-937-001','C2','9.39','2026-11-12T19:35')]
    a=[ack('C2','APPLICATION_ERROR','2026-11-12T20:00:00')]
    result=run_mock(p,m,a)
    assert result['provisional_exceptions']==1
    assert 'LEGAL_STATUS_MISMATCH_PROVISIONAL' in result['rows'][0]['issues']
    assert 'APPLICATION_ERROR' in result['rows'][0]['issues']


def test_other_date_paperwork_is_excluded():
    p=[paper('BELL, MARCUS','SYN-939-002','9.39','2026-11-13')]
    result=run_mock(p,[],[])
    assert result['paperwork_count']==0
    assert not result['rows']


def test_unreadable_date_remains_visible():
    p=[paper('BROOKS, ALICIA','SYN-937-001','9.37','')]
    result=run_mock(p,[],[])
    assert result['rows'][0]['status']=='OCR_UNCERTAIN'
    assert result['rows'][0]['issues']=='CANNOT_ASSIGN_PAPERWORK_TO_SELECTED_DATE'
