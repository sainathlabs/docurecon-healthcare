"""Conservative daily reconciliation for the DocuRecon synthetic research profile.

This is NOT a production compliance determination. Paperwork OCR is unverified,
therefore findings involving paperwork are explicitly provisional. The engine
never fills missing document values from filenames or synthetic ground truth.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
import re
from docurecon.parsers.paperwork_parser import extract_folder
from docurecon.parsers.hl7_parser import parse_hl7_folder
from docurecon.parsers.ack_parser import parse_ack_folder


def _normal_name(value: str) -> str:
    pieces = re.split(r'[\^,\s]+', (value or '').upper())
    return ' '.join(sorted(p for p in pieces if p))


def _date(value: str) -> str:
    return (value or '')[:10]


def _ack_state(found: list[dict]) -> str:
    if not found: return 'NO_ACK_IN_SUPPLIED_FILES'
    if len(found) != 1: return 'MULTIPLE_ACKS'
    return found[0]['ack_class']


def run_daily(root: Path, selected: date | str, *, source_mode='folder', uploads=None) -> dict:
    """Scan all three sources and report provisional exceptions for selected date.

    All HL7 files are searched regardless of transmission date to catch late
    reporting. Other-day paperwork is excluded. Unreadable paperwork is listed
    as a parsing error and never converted into a missing-HL7 determination.
    """
    root = Path(root)
    day = selected.isoformat() if isinstance(selected, date) else str(selected)
    datetime.strptime(day, '%Y-%m-%d')
    papers, paper_errors = extract_folder(root / 'paperwork')
    messages, hl7_errors = parse_hl7_folder(root / 'hl7')
    acks, ack_errors = parse_ack_folder(root / 'acknowledgements')
    errors = ([{'folder':'paperwork', **e} for e in paper_errors] +
              [{'folder':'hl7', **e} for e in hl7_errors] +
              [{'folder':'acknowledgements', **e} for e in ack_errors])
    ack_by_id = defaultdict(list)
    for ack in acks: ack_by_id[ack['control_id']].append(ack)
    ids = Counter(m['control_id'] for m in messages)
    rows = []
    covered_messages = set()
    selected_papers = [p for p in papers if p.get('completion_date') == day]
    excluded_missing_date = [p for p in papers if not p.get('completion_date')]

    for p in selected_papers:
        reasons = list(p.get('review_reasons') or [])
        mrn = (p.get('mrn') or '').upper()
        name = _normal_name(p.get('patient_name', ''))
        exact = [m for m in messages if mrn and m['patient_id'].upper() == mrn]
        by_name = [m for m in messages if name and _normal_name(m.get('patient_name','')) == name]
        # If OCR identifier conflicts with name evidence, do not force an exact
        # MRN match. Keep the record uncertain even when a candidate exists.
        if exact and by_name and set(m['control_id'] for m in exact) != set(m['control_id'] for m in by_name):
            candidates = []
            reasons.append('CONFLICTING_PATIENT_MATCH_EVIDENCE')
        else:
            candidates = exact or by_name
        method = 'MRN' if exact and candidates else 'PATIENT_NAME_ONLY' if candidates else 'NONE'
        if method == 'PATIENT_NAME_ONLY': reasons.append('MATCHED_BY_NAME_NOT_VERIFIED_MRN')
        control = ''; hl7_file = ''; ack_file = ''; ack_code = ''; ack_status = 'NOT_APPLICABLE'
        issues=[]
        if len(candidates) > 1:
            issues.append('AMBIGUOUS_MULTIPLE_HL7_CANDIDATES')
            for m in candidates: covered_messages.add(m['control_id'])
        elif not candidates:
            # Filename and OCR alone are insufficient for definitive missing HL7.
            issues.append('NO_HL7_CANDIDATE_IN_SUPPLIED_FILES')
            reasons.append('UNCONFIRMED_ABSENCE_REQUIRES_COMPLETE_SOURCE_EXPORT')
        else:
            m = candidates[0]
            covered_messages.add(m['control_id'])
            control = m['control_id']; hl7_file = m['source']
            if m['legal_status'] != p.get('form_type'):
                issues.append('LEGAL_STATUS_MISMATCH_PROVISIONAL')
            if _date(m['completion_timestamp']) != day:
                issues.append('COMPLETION_DATE_MISMATCH_PROVISIONAL')
            if p.get('completion_time') and m['completion_timestamp'][11:16] != p['completion_time']:
                issues.append('COMPLETION_TIME_MISMATCH_PROVISIONAL')
            elif not p.get('completion_time'):
                reasons.append('COMPLETION_TIME_NOT_COMPARABLE')
            found = ack_by_id.get(control, [])
            ack_status = _ack_state(found)
            ack_file = ', '.join(a['source'] for a in found)
            ack_code = ', '.join(a['ack_code'] for a in found)
            if ids[control] > 1: issues.append('DUPLICATE_CONTROL_ID')
            if ack_status != 'ACCEPTED':
                issues.append(ack_status)
            if found and any(a['received_at'] < m['transmitted_at'] for a in found):
                issues.append('ACK_BEFORE_TRANSMISSION_TIMESTAMP')
        # We do not call any paperwork-derived match VERIFIED or CONFIRMED.
        status = ('OCR_UNCERTAIN' if not candidates or len(candidates)>1 or method=='PATIENT_NAME_ONLY'
                  else 'PROVISIONAL_EXCEPTION' if issues else 'PROVISIONAL_MATCH')
        rows.append({'paperwork_file':p['source'],'patient_name':p.get('patient_name',''),
                     'ocr_mrn':mrn,'legal_status_paperwork':p.get('form_type',''),
                     'completion_date':day,'completion_time_ocr':p.get('completion_time',''),
                     'match_method':method,'hl7_file':hl7_file,'control_id':control,
                     'ack_file':ack_file,'ack_code':ack_code,'ack_status':ack_status,
                     'status':status,'issues':'; '.join(issues),
                     'uncertainty_reasons':'; '.join(dict.fromkeys(reasons))})

    for p in excluded_missing_date:
        rows.append({'paperwork_file':p['source'],'patient_name':p.get('patient_name',''),
                     'ocr_mrn':p.get('mrn',''),'legal_status_paperwork':p.get('form_type',''),
                     'completion_date':'','completion_time_ocr':p.get('completion_time',''),
                     'match_method':'NONE','hl7_file':'','control_id':'','ack_file':'',
                     'ack_code':'','ack_status':'NOT_EVALUATED','status':'OCR_UNCERTAIN',
                     'issues':'CANNOT_ASSIGN_PAPERWORK_TO_SELECTED_DATE',
                     'uncertainty_reasons':'; '.join(p.get('review_reasons') or [])})

    # Orphan ACK and duplicate messages are technical input diagnostics, not
    # medical/legal paperwork outcomes. Do not add unmatched HL7 from other days
    # as missing-paperwork findings: the upload may span multiple dates.
    orphan_acks=[a for a in acks if a['control_id'] not in ids]
    counts=Counter(r['status'] for r in rows)
    return {'date':day,'paperwork_count':len(selected_papers),
            'hl7_count':len(messages),'ack_count':len(acks),
            'provisional_matches':counts['PROVISIONAL_MATCH'],
            'provisional_exceptions':counts['PROVISIONAL_EXCEPTION'],
            'ocr_uncertain':counts['OCR_UNCERTAIN'],
            'rows':rows,'parse_errors':errors,'orphan_acks':orphan_acks,
            'note':('All paperwork results are provisional because the scanned-document '
                    'OCR has not been independently validated. Missing files in supplied '
                    'folders are not proof of missing regulatory reports. AA is application '
                    'acceptance, not proof of downstream regulatory reporting.')}
