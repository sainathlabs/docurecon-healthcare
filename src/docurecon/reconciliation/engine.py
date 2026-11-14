"""Synthetic-data-first daily 9.39 paperwork / HL7 / ACK reconciliation."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, date
from pathlib import Path
import json, re

DATE_FORMATS = ('%Y%m%d%H%M%S','%Y%m%d%H%M','%Y%m%d','%Y-%m-%d %H:%M:%S','%Y-%m-%d %H:%M','%Y-%m-%d')

def normalize_date(value):
    value = (value or '').strip()
    for fmt in DATE_FORMATS:
        try:
            candidate = datetime.strptime(value, fmt)
            if candidate.strftime(fmt) == value:
                return candidate.date().isoformat()
        except ValueError:
            pass
    return ''

def segments(raw):
    return [line.strip() for line in re.split(r'[\r\n]+', raw) if line.strip()]

def field(fields, pos, default=''):
    return fields[pos] if len(fields)>pos else default

def decode_hl7(path):
    raw=path.read_text(encoding='utf-8-sig',errors='replace')
    rows=[r.split('|') for r in segments(raw)]
    msh=next((r for r in rows if r[0]=='MSH'), None)
    if not msh: raise ValueError('Missing MSH segment')
    pid=next((r for r in rows if r[0]=='PID'), [])
    pv1=next((r for r in rows if r[0]=='PV1'), [])
    zls=next((r for r in rows if r[0]=='ZLS'), [])
    return {'source':path.name,'control_id':field(msh,9), 'message_type':field(msh,8),
            'message_date':normalize_date(field(msh,6)), 'patient_id':field(pid,3).split('^')[0],
            'encounter_id':field(pv1,19).split('^')[0],
            'legal_status':field(zls,1), 'completion_date':normalize_date(field(zls,2)),
            'raw':raw}

def decode_ack(path):
    raw=path.read_text(encoding='utf-8-sig',errors='replace')
    rows=[r.split('|') for r in segments(raw)]
    msa=next((r for r in rows if r[0]=='MSA'),None)
    if not msa: raise ValueError('Missing MSA segment')
    code=field(msa,1).strip()
    return {'source':path.name,'control_id':field(msa,2).strip(), 'ack_code':code,
            'ack_class': {'AA':'ACCEPTED','CA':'ACCEPTED','AE':'ERROR','CE':'ERROR','AR':'REJECTED','CR':'REJECTED'}.get(code,'UNKNOWN')}

def pdf_to_text(path):
    import pymupdf
    doc=pymupdf.open(path)
    text='\n'.join(page.get_text() for page in doc)
    if text.strip(): return text
    # OCR requires locally installed Tesseract. The app will report a parsing error if absent.
    try:
        import pytesseract
        from PIL import Image
        import io
        parts=[]
        for page in doc:
            pix=page.get_pixmap(matrix=pymupdf.Matrix(2,2))
            parts.append(pytesseract.image_to_string(Image.open(io.BytesIO(pix.tobytes('png')))))
        return '\n'.join(parts)
    except Exception as ex:
        raise ValueError('Scanned PDF needs Tesseract OCR installed and accessible: '+str(ex))

def decode_paperwork(path):
    if path.suffix.lower()=='.pdf': raw=pdf_to_text(path)
    elif path.suffix.lower()=='.json': raw=json.dumps(json.loads(path.read_text(encoding='utf-8')),indent=2)
    else: raw=path.read_text(encoding='utf-8-sig',errors='replace')
    def get(key):
        match=re.search(r'^\s*'+re.escape(key)+r'\s*[:=]\s*([^\r\n"},]+)',raw,flags=re.I|re.M)
        if match:return match.group(1).strip(' "')
        # Handle JSON records
        match=re.search(r'"'+re.escape(key)+r'"\s*:\s*"([^"]+)"',raw,re.I)
        return match.group(1).strip() if match else ''
    fields = {'source':path.name,'patient_id':get('Patient ID'),'encounter_id':get('Encounter ID'),
            'legal_status':get('Legal Status'),'completion_date':normalize_date(get('Completion Date'))}
    if not fields['patient_id'] or not fields['completion_date']:
        raise ValueError('Cannot extract required structured fields from this paperwork; OMH 474/475 scanned-form extraction is not implemented yet.')
    return fields

def read_files(folder,fn,suffixes):
    result=[]; errors=[]
    if not folder.exists():return result,errors
    for path in sorted(folder.iterdir()):
        if path.is_file() and path.suffix.lower() in suffixes:
            try: result.append(fn(path))
            except Exception as ex: errors.append({'file':path.name,'folder':folder.name,'error':str(ex)})
    return result,errors

def reconcile(root:Path, selected:date):
    root=Path(root)
    papers,ep=read_files(root/'paperwork',decode_paperwork,{'.pdf','.txt','.json'})
    messages,em=read_files(root/'hl7',decode_hl7,{'.hl7','.txt'})
    acks,ea=read_files(root/'acknowledgements',decode_ack,{'.hl7','.txt','.ack'})
    errors=ep+em+ea
    day=selected.isoformat()
    papers=[p for p in papers if p['completion_date']==day]
    messages_today=[m for m in messages if m['message_date']==day]
    # Keep all messages for paperwork reconciliation: late transmissions may occur after completion.
    ack_map={}
    for ack in acks:ack_map.setdefault(ack['control_id'],[]).append(ack)
    output=[]; used=set()
    for p in papers:
        problems=[]
        if not p['patient_id'] or not p['encounter_id'] or not p['completion_date']:
            problems.append('INCOMPLETE_PAPERWORK')
        candidates=[(i,m) for i,m in enumerate(messages) if m['patient_id']==p['patient_id'] and m['encounter_id']==p['encounter_id'] and p['patient_id'] and p['encounter_id']]
        if not candidates:problems.append('MISSING_HL7')
        if len(candidates)>1:problems.append('MULTIPLE_HL7_MATCHES')
        for idx,m in candidates: used.add(idx)
        match=candidates[0][1] if len(candidates)==1 else None
        code=''; control=''; msgfile=''; ackfile=''
        if match:
            control=match['control_id'];msgfile=match['source']
            if not control:problems.append('MISSING_CONTROL_ID')
            if not match['legal_status'] or match['legal_status'].strip()!=p['legal_status'].strip():problems.append('LEGAL_STATUS_MISMATCH')
            if match['completion_date']!=p['completion_date']:problems.append('COMPLETION_DATE_MISMATCH')
            candidates_ack=ack_map.get(control,[]) if control else []
            if not candidates_ack:problems.append('MISSING_ACK')
            elif len(candidates_ack)>1:problems.append('MULTIPLE_ACKS')
            else:
                a=candidates_ack[0];code=a['ack_code'];ackfile=a['source']
                if a['ack_class'] in ('ERROR','REJECTED'):problems.append('ACK_'+a['ack_class'])
                elif a['ack_class']=='UNKNOWN':problems.append('ACK_UNKNOWN')
        output.append({'patient_id':p['patient_id'],'encounter_id':p['encounter_id'], 'paperwork_file':p['source'],
            'hl7_file':msgfile,'ack_file':ackfile,'control_id':control,'ack_code':code,
            'status':'EXCEPTION' if problems else 'MATCHED','issues':', '.join(problems)})
    unmatched=[m for i,m in enumerate(messages) if i not in used and m['message_date']==day]
    for m in unmatched:
        output.append({'patient_id':m['patient_id'],'encounter_id':m['encounter_id'],'paperwork_file':'',
                       'hl7_file':m['source'],'ack_file':'','control_id':m['control_id'],'ack_code':'',
                       'status':'EXCEPTION','issues':'HL7_WITHOUT_MATCHING_PAPERWORK'})
    return {'date':day,'paperwork_count':len(papers),'hl7_count':len(messages_today),'ack_count':len(acks),
            'matched':sum(r['status']=='MATCHED' for r in output),'exceptions':sum(r['status']=='EXCEPTION' for r in output),
            'records':output,'errors':errors,
            'note':'An AA/CA acknowledgement does not establish successful downstream regulatory reporting. Verify independently.'}
