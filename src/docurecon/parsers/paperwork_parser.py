"""Experimental OCR for synthetic OMH 474 / 475 samples.

Extracts from pixels, not filenames or ground-truth metadata. Never infer data
from a patient's filename; uncertain fields require human review.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
import io
import re

DATE_RE = re.compile(r'(?<!\d)(\d{1,2}/\d{1,2}/20\d{2})(?!\d)')
TIME_RE = re.compile(
    r'(?<!\d)(\d{1,2}[:-]\d{2}\s*[AP]M)(?!\w)',
    re.I
)
MRN_RE = re.compile(
    r'\b(?:SYN[-– ]?\d{3}[-– ]?\d{3}|SYN[-– ]?PILOT[-– ]?\d{4})\b',
    re.I
)
NAME_RE = re.compile(r'\b[A-Z][A-Z]{2,},\s*[A-Z][A-Z]{2,}\b')


def _page_image(page, region=None, scale=3):
    import pymupdf as fitz
    from PIL import Image
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=fitz.Rect(region) if region else None, alpha=False)
    return Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')


def _ocr(image, psm=6):
    import pytesseract
    return pytesseract.image_to_string(image, config=f'--psm {psm}')


def _match(pattern, text):
    match=pattern.search(text)
    return match.group(0).strip() if match else ''


def _standard_date(text):
    match=DATE_RE.search(text)
    if not match: return ''
    try: return datetime.strptime(match.group(1), '%m/%d/%Y').date().isoformat()
    except ValueError: return ''



def _standard_time(text):
    match = TIME_RE.search(text)

    if not match:
        return ""

    raw_time = match.group(1).upper().strip()

    # OCR can read the colon as a hyphen.
    raw_time = raw_time.replace("-", ":")

    # Standardise spacing before AM/PM.
    raw_time = re.sub(
        r"\s*([AP]M)$",
        r" \1",
        raw_time,
    )

    try:
        return datetime.strptime(
            raw_time,
            "%I:%M %p",
        ).strftime("%H:%M")

    except ValueError:
        return ""



def extract_paperwork(path: str | Path) -> dict:
    """OCR an image-only PDF; return extracted values + review flags.

    Supports the currently included synthetic form layouts only. For §9.37
    completion means Form 475 Part C physician confirmation (page 2 in this
    reduced synthetic packet). For §9.39 completion means admitting physician
    signature date/time on the first page of this reduced packet.
    """
    import fitz
    from PIL import ImageOps, ImageEnhance
    path=Path(path)
    if path.suffix.lower() != '.pdf': raise ValueError('Expected PDF input')
    doc=fitz.open(path)
    if not doc.page_count: raise ValueError('Empty PDF')
    try:
        text0 = _ocr(_page_image(doc[0],scale=2.7),psm=3)
        form = ('9.39' if re.search(r'9[.\s]*39|EMERGENCY ADMISSION',text0,re.I)
                else '9.37' if re.search(r'9[.\s]*37|CERTIFICATE OF A',text0,re.I)
                else '')
        result={'source':path.name,'form_type':form,'patient_name':'','mrn':'','facility':'',
                'completion_date':'','completion_time':'','extraction_status':'review_required',
                'review_reasons':[], 'ocr_pages':doc.page_count}
        if not form:result['review_reasons'].append('FORM_NOT_IDENTIFIED')
        # Use full-page text for labels/names and constrained ROI to reduce OCR noise.

        # First attempt: existing patient-name extraction
        names = NAME_RE.findall(text0)

        result["patient_name"] = (
            names[0].strip().upper()
            if names else ""
        )

        # Fallback: patient name in the admission request.
        # Some scanned OMH forms have an unreadable
        # header but a readable name elsewhere.
        if not result["patient_name"]:
            admission_match = re.search(
                r"hereby\s+request\s+that\s*"
                r"([A-Z][A-Z'-]{1,},\s*[A-Z][A-Z'-]{1,})"
                r"\s+be\s+admitted",
                text0,
                re.I,
            )

            if admission_match:
                result["patient_name"] = (
                    admission_match.group(1)
                    .strip()
                    .upper()
                )
                result["review_reasons"].append(
                    "PATIENT_NAME_FROM_ADMISSION_SECTION"
                )

        mrn=_match(MRN_RE,text0)
        if not mrn:
            crop=_ocr(_page_image(doc[0],(375,105,575,145)),psm=6)
            mrn=_match(MRN_RE,crop)
        result['mrn']=mrn.replace(' ','-').upper() if mrn else ''
        # Filename is NOT used to fill patient data. Use only as a warning
        # when an OCR reading conflicts with a synthetic sample file label.
        filename_id=_match(MRN_RE,path.stem)
        if filename_id and result['mrn'] and result['mrn'] != filename_id:
            result['review_reasons'].append('MRN_CONFLICTS_WITH_SYNTHETIC_FILENAME')


        lines = [
            line.strip()
            for line in text0.splitlines()
            if line.strip()
        ]


        # Facility extraction from the scanned document.
        # Never infer a facility from filename or ground truth.

        facility_patterns = (
            r"RIVERBEND TEST HOSPITAL",
            r"NORTHBRIDGE TEST CENTER",
            r"LAKESIDE TEST MEDICAL CTR",
            r"HUDSON VALLEY TEST HOSPITAL",
            r"SYNTHETIC RESEARCH FACILITY",
        )

        def find_facility(ocr_text):
            for pattern in facility_patterns:
                match = re.search(pattern, ocr_text, re.I)
                if match:
                    return match.group(0).upper()
            return ""

        # First use the existing PSM 3 full-page OCR.
        result["facility"] = find_facility(text0)

        # Try sparse-text OCR if the facility was not found.
        if not result["facility"]:
            sparse_text = _ocr(
                _page_image(doc[0], scale=3),
                psm=11,
            )
            result["facility"] = find_facility(sparse_text)

        # Try PSM 6 and preserve only partial evidence.
        if not result["facility"]:
            block_text = _ocr(
                _page_image(doc[0], scale=3),
                psm=6,
            )

            if re.search(
                r"\bRESEARCH\s+FACILITY\b",
                block_text,
                re.I,
            ):
                result["review_reasons"].append(
                    "PARTIAL_FACILITY_NAME_REQUIRES_REVIEW"
                )


        if form=='9.39':
            # Bottom right: signature row, rather than arrival date.
            roi=_ocr(_page_image(doc[0],(387,678,612,724)),psm=6)
            result['completion_date']=_standard_date(roi)
            result['completion_time']=_standard_time(roi)
        elif form=='9.37':
            # 475 Part C is the second page of our three-page synthetic packet.
            if doc.page_count < 2:result['review_reasons'].append('MISSING_PART_C_PAGE')
            else:
                full=_ocr(_page_image(doc[1],scale=2.7),psm=3)
                roi=_ocr(_page_image(doc[1],(380,677,612,715)),psm=6)
                result['completion_date']=_standard_date(roi) or _standard_date(full.split('Physician',1)[-1])
                # Multiple OCR views must agree. Never treat a misread time
                # (for example 9:42 vs 12:42) as a verified timestamp.
                roi_time=_standard_time(roi)
                full_time=_standard_time(full)
                if roi_time and full_time and roi_time != full_time:
                    result['review_reasons'].append('CONFLICTING_TIME_OCR')
                    result['completion_time']=''
                else:
                    result['completion_time']=roi_time or full_time
        for field in ('patient_name','mrn','completion_date','completion_time','facility'):
            if not result[field]:result['review_reasons'].append('MISSING_OR_UNREADABLE_'+field.upper())
        # OCR is not sufficient evidence of a valid signature or legal completion.
        result['review_reasons'].append('OCR_VALUES_REQUIRE_HUMAN_VERIFICATION')
        result['extraction_status']='review_required' if result['review_reasons'] else 'extracted'
        return result
    finally:doc.close()


def extract_folder(folder: str | Path):
    records=[];errors=[]
    for path in sorted(Path(folder).glob('*.pdf')):
        try: records.append(extract_paperwork(path))
        except Exception as exc: errors.append({'source':path.name,'error':str(exc)})
    return records,errors
