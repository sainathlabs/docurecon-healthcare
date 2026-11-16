"""DocuRecon independent synthetic-only dataset generator.

Produces 400 IMAGE-ONLY PDFs on 2026 OMH 474/475 templates, HL7 v2 test
messages and ACKs, ground-truth manifest, hashes, and a protocol. No real PHI.

This tool does NOT run or tune the reconciliation system. Outputs are deterministic
on a fixed version of Pillow/PyMuPDF. Byte hashes can vary across library builds.
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

import pymupdf
from PIL import Image, ImageEnhance, ImageFilter
from io import BytesIO

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'evaluation_dataset' / 'independent_test'
PAPER = OUT / 'paperwork'
HL7 = OUT / 'hl7'
ACK = OUT / 'acknowledgements'
GT = OUT / 'ground_truth'
TEMP = ROOT / 'evaluation_dataset' / 'templates'
T937 = TEMP / 'mhl-9-37-omh475-475a-475b-475c-475d.pdf'
T939 = TEMP / 'mhl-9-39-omh474.pdf'
SEED = 20261115
RNG = random.Random(SEED)
SCENARIOS = [
    ('CLEAN_MATCH', 100),
    ('OCR_SCAN_QUALITY', 80),
    ('INCOMPLETE_DOCUMENTATION', 50),
    ('IDENTIFIER_DISCREPANCY', 50),
    ('COMPLETION_TIME_DISCREPANCY', 40),
    ('MISSING_HL7_OR_ACK', 40),
    ('DUPLICATE_OR_ACK_ERROR', 40),
]
FIRST = ['AARAV','ADITI','ANIKA','ARJUN','ASHWIN','AVANI','DEV','DIYA','EESHA','FARAH',
         'GAURAV','ISHAN','ISHITA','JAI','JAYA','KABIR','KAVYA','KIRAN','LEELA','MANAV',
         'MEERA','MIRA','NAVEEN','NEHA','NIKHIL','OMAR','POOJA','PRIYA','RAHUL','REVA',
         'RISHI','ROHAN','SAHIL','SANA','SARA','SHREYA','TARA','VARUN','VED','ZARA']
LAST = ['AGARWAL','AHMED','BAKSHI','BANERJEE','BOSE','CHANDRA','DAS','DESAI','GILL','GUPTA',
        'IYER','JAIN','JOSHI','KAUR','KHAN','KOHLI','KUMAR','MEHTA','MENON','MISHRA',
        'NAIR','PATEL','RAO','REDDY','ROY','SAXENA','SEN','SHAH','SHARMA','SINGH',
        'SURI','THAKUR','VERMA','WALIA','YADAV']
INK = (0.06,0.18,0.42)
RED = (0.72,0.1,0.11)


def stamp(page, x, y, val, size=8):
    page.insert_text((x,y), str(val), fontsize=size, fontname='helv', color=INK, overlay=True)


def warn(page):
    page.draw_rect(pymupdf.Rect(40,754,573,775), fill=(1,.94,.93), color=RED, width=.6)
    page.insert_text((56,769),'SYNTHETIC RESEARCH SAMPLE - NOT A VALID MEDICAL RECORD',
                     fontsize=9.5, fontname='hebo', color=RED)


def make_pdf(case, filename):
    src = pymupdf.open(T937 if case['legal_status']=='9.37' else T939)
    doc = pymupdf.open()
    for idx in ([2,3] if case['legal_status']=='9.37' else [1,2]):
        doc.insert_pdf(src, from_page=idx, to_page=idx)
    src.close()
    name = case['patient_name']
    mrn = case['mrn']
    when = datetime.fromisoformat(case['completion_date']+'T'+case['completion_time'])
    mode = case['secondary_variation']
    # Incomplete: do not change dates; omitted identity field only. This retains
    # a well-defined date-scoped evaluation and tests cautious matching.
    visible_mrn = '' if mode=='OMIT_MRN' else mrn
    visible_name = '' if mode=='OMIT_NAME' else name
    p0,p1 = doc[0],doc[1]
    if case['legal_status']=='9.37':
        for p in (p0,p1):
            if visible_name: stamp(p,358,65,visible_name,9)
            if visible_mrn: stamp(p,358,124 if p is p0 else 91,visible_mrn,9)
            warn(p)
        if mode!='OMIT_FACILITY':
            stamp(p0,359,141,'Synthetic Research Facility',8)
            stamp(p0,330,210,'Synthetic Research Facility',8)
        if visible_name: stamp(p0,117,180,visible_name,9)
        stamp(p1,44,471,'Simulated physician review for research only.',8)
        stamp(p1,43,707,'SIMULATED SIGNATURE',8)
        stamp(p1,394,707,when.strftime('%m/%d/%Y'),8)
        stamp(p1,488,707,when.strftime('%I:%M %p'),8)
    else:
        for p in (p0,p1):
            if visible_name: stamp(p,357,70,visible_name,9)
            if visible_mrn: stamp(p,380,134,visible_mrn,9)
            if mode!='OMIT_FACILITY': stamp(p,416,151,'Research Facility',8)
            warn(p)
        stamp(p0,45,705,'SIMULATED SIGNATURE',8)
        stamp(p0,263,705,'RESEARCH MD',8)
        stamp(p0,394,705,when.strftime('%m/%d/%Y'),8)
        stamp(p0,492,705,when.strftime('%I:%M %p'),8)
    scan = pymupdf.open()
    quality = case['scan_quality']
    for p in doc:
        dpi = 1.6 if quality == 'clean' else (1.35 if quality == 'moderate' else 1.2)
        pix = p.get_pixmap(matrix=pymupdf.Matrix(dpi,dpi),alpha=False)
        im = Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
        if quality=='moderate':
            im = ImageEnhance.Contrast(im).enhance(.90)
            im = im.filter(ImageFilter.GaussianBlur(radius=.22))
        elif quality=='degraded':
            im = ImageEnhance.Contrast(im).enhance(.76)
            im = ImageEnhance.Brightness(im).enhance(1.07)
            im = im.filter(ImageFilter.GaussianBlur(radius=.65))
        buf=BytesIO();im.save(buf,format='JPEG',quality=80,optimize=False)
        sp=scan.new_page(width=p.rect.width,height=p.rect.height)
        sp.insert_image(sp.rect,stream=buf.getvalue())
    scan.save(filename,deflate=True)
    doc.close();scan.close()


def make_message(case, suffix, mrn, name, when):
    last,first=name.split(', ',1)
    complete=datetime.fromisoformat(case['completion_date']+'T'+case['completion_time'])
    message_time=complete+timedelta(minutes=10)
    cid=f'DR-TEST-{case["case_id"]}-{suffix}'
    lines=[
        f'MSH|^~\\&|DOCURECON|SYNTHETIC_FACILITY|TEST_RECEIVER|TEST|{message_time:%Y%m%d%H%M%S}||ADT^A01|{cid}|P|2.5',
        f'PID|1||{mrn}^^^SYNTHETIC^MR||{last}^{first}',
        f'PV1|1|I|||||||||||||||||ENC-TEST-{case["case_id"]}-{suffix}',
        f'ZLS|{case["legal_status"]}|{when:%Y%m%d}|{when:%H%M}'
    ]
    (HL7/f'TEST-{case["case_id"]}-{suffix}.hl7').write_bytes(('\r'.join(lines)+'\r').encode('ascii'))
    return cid


def make_ack(case, suffix, cid, code):
    complete=datetime.fromisoformat(case['completion_date']+'T'+case['completion_time'])
    when=complete+timedelta(minutes=12)
    desc={'AA':'Application accepted','AE':'Application error','AR':'Application rejected'}[code]
    segments=[
        f'MSH|^~\\&|TEST_RECEIVER|TEST|DOCURECON|SYNTHETIC_FACILITY|{when:%Y%m%d%H%M%S}||ACK^A01|ACK-TEST-{case["case_id"]}-{suffix}|P|2.5',
        f'MSA|{code}|{cid}|{desc}'
    ]
    (ACK/f'TEST-{case["case_id"]}-{suffix}_{code}.ack').write_bytes(('\r'.join(segments)+'\r').encode('ascii'))


def main():
    if not T937.is_file() or not T939.is_file():
        raise FileNotFoundError('Required 2026 form PDFs not found')
    if OUT.exists() and any(OUT.rglob('*.*')):
        raise FileExistsError('Refusing to overwrite existing independent dataset')
    for d in (PAPER,HL7,ACK,GT): d.mkdir(parents=True,exist_ok=True)
    labels=[]
    for key,count in SCENARIOS: labels += [key]*count
    RNG.shuffle(labels)
    # Every group has even counts: balance status across each primary scenario.
    status_by_cat={s:0 for s,_ in SCENARIOS}
    rows=[]
    for i,scenario in enumerate(labels,1):
        status_by_cat[scenario]+=1
        legal='9.37' if status_by_cat[scenario] <= dict(SCENARIOS)[scenario]//2 else '9.39'
        first=FIRST[(i*13)%len(FIRST)]
        last=LAST[(i*17+i//len(LAST))%len(LAST)]
        patient=f'{last}, {first}'
        mrn=f'SYN-{i//1000+1:03d}-{i:03d}'
        when=datetime(2027,1,1,7)+timedelta(days=i-1,hours=RNG.randint(0,10),minutes=RNG.randint(0,59))
        variant='NONE'
        quality='clean'
        if scenario=='OCR_SCAN_QUALITY':
            quality='moderate' if status_by_cat[scenario] <= 40 else 'degraded'
        elif scenario=='INCOMPLETE_DOCUMENTATION':
            variant=['OMIT_MRN','OMIT_NAME','OMIT_FACILITY'][ (status_by_cat[scenario]-1)%3 ]
        elif scenario=='IDENTIFIER_DISCREPANCY':
            variant='HL7_MRN_DIFFERENT' if status_by_cat[scenario]<=25 else 'HL7_NAME_DIFFERENT'
        elif scenario=='COMPLETION_TIME_DISCREPANCY': variant='HL7_TIME_DIFFERENT'
        elif scenario=='MISSING_HL7_OR_ACK': variant='NO_HL7_IN_SAMPLE' if status_by_cat[scenario]<=20 else 'NO_ACK_IN_SAMPLE'
        elif scenario=='DUPLICATE_OR_ACK_ERROR':
            variant='DUPLICATE_HL7' if status_by_cat[scenario]<=16 else ('ACK_AE' if status_by_cat[scenario]<=28 else 'ACK_AR')
        cid=f'{i:04d}'
        filename=f'DocuRecon_SYNTHETIC_TEST_{legal.replace(".","")}_{cid}.pdf'
        row=dict(case_id=cid, document=filename,patient_name=patient,mrn=mrn,legal_status=legal,
                 completion_date=when.strftime('%Y-%m-%d'),completion_time=when.strftime('%H:%M'),
                 completion_rule='PART_C_COMPLETION' if legal=='9.37' else 'FIRST_PHYSICIAN_COMPLETION',
                 primary_scenario=scenario,secondary_variation=variant,scan_quality=quality,synthetic='true',
                 expected_hl7_control_ids='',expected_ack_code='',expected_linkage='',
                 hl7_mrn='',hl7_patient_name='',hl7_completion_time='')
        make_pdf(row,PAPER/filename)
        ids=[];ackcodes=[]
        hl7_mrn=mrn;hl7_patient=patient;hl7_time=when
        if variant=='HL7_MRN_DIFFERENT': hl7_mrn=f'SYN-999-{i:03d}'
        if variant=='HL7_NAME_DIFFERENT': hl7_patient=f'{LAST[(i+13)%len(LAST)]}, {FIRST[(i+7)%len(FIRST)]}'
        if variant=='HL7_TIME_DIFFERENT': hl7_time+=timedelta(minutes=20)
        if variant!='NO_HL7_IN_SAMPLE':
            copies=2 if variant=='DUPLICATE_HL7' else 1
            for n in range(1,copies+1):
                control=make_message(row,n,hl7_mrn,hl7_patient,hl7_time)
                ids.append(control)
                if variant!='NO_ACK_IN_SAMPLE':
                    code='AE' if variant=='ACK_AE' else ('AR' if variant=='ACK_AR' else 'AA')
                    make_ack(row,n,control,code)
                    ackcodes.append(code)
        row['expected_hl7_control_ids']=';'.join(ids)
        row['expected_ack_code']=';'.join(ackcodes)
        row['expected_linkage']= ('NO_CANDIDATE' if variant=='NO_HL7_IN_SAMPLE' else
                                 'AMBIGUOUS' if variant=='DUPLICATE_HL7' else
                                 'IDENTITY_UNCERTAIN' if variant in ('HL7_MRN_DIFFERENT','HL7_NAME_DIFFERENT','OMIT_MRN','OMIT_NAME') else
                                 'CANDIDATE')
        row['hl7_mrn']=hl7_mrn if ids else ''
        row['hl7_patient_name']=hl7_patient if ids else ''
        row['hl7_completion_time']=hl7_time.strftime('%H:%M') if ids else ''
        rows.append(row)
        if i%50==0: print('Generated:',i,flush=True)
    fieldnames=list(rows[0].keys())
    with (GT/'case_ground_truth.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fieldnames,lineterminator='\n');w.writeheader();w.writerows(rows)
    protocol={
        'project':'DocuRecon','protocol_version':'1.0.0',
        'pipeline_tag':'v0.3.0-pilot','pipeline_commit':'2a3ebdd',
        'random_seed':SEED,'total_cases':400,'synthetic_data_only':True,
        'allow_pipeline_tuning_on_test_set':False,
        'primary_scenarios':dict(SCENARIOS),
        'form_types':{'9.37':200,'9.39':200},
        'limitations':['Only two underlying 2026 OMH form families; not unseen layout families',
                       'Artificial scanning variations and simulated signatures',
                       'Custom synthetic ZLS segment, not real-world interface compatibility',
                       'Some primary classes have secondary subtypes and ambiguity rules',
                       'No inference about real reporting compliance from absent sample files'],
        'ground_truth_policy':{'not_provided_to_pipeline':True,'frozen_before_execution':True}
    }
    (GT/'evaluation_protocol.json').write_text(json.dumps(protocol,indent=2)+'\n',encoding='utf-8')
    manifest=[]
    for path in sorted(OUT.rglob('*')):
        if path.is_file() and path.name!='sha256.txt':
            manifest.append(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(ROOT).as_posix()}')
    (GT/'sha256.txt').write_text('\n'.join(manifest)+'\n',encoding='ascii')
    assert len(rows)==400
    assert sum(x['legal_status']=='9.37' for x in rows)==200
    assert len(list(PAPER.glob('*.pdf')))==400
    print('DONE: PDFs=',len(list(PAPER.glob('*.pdf'))),'HL7=',len(list(HL7.glob('*.hl7'))),'ACK=',len(list(ACK.glob('*.ack'))),'hashes=',len(manifest))

if __name__=='__main__': main()
