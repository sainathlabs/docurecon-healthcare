"""Create 10 image-only synthetic records on the supplied OMH 474/475 form layouts.

These are conspicuously marked simulation documents, not authentic completed forms.
Original templates are retained. Run once. Existing output will not be overwritten.
"""
from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

import pymupdf as fitz

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = ROOT / 'evaluation_dataset' / 'templates'
OUT = ROOT / 'evaluation_dataset' / 'pilot_form_based' / 'paperwork'
MANIFEST = ROOT / 'evaluation_dataset' / 'manifests' / 'pilot_form_based_ground_truth.csv'
TEMPLATE_939 = TEMPLATE_DIR / 'mhl-9-39-omh474.pdf'
TEMPLATE_937 = TEMPLATE_DIR / 'mhl-9-37-omh475-475a-475b-475c-475d.pdf'
RNG = random.Random(20261115)
PATIENTS = [
    ('Maya', 'Nolan'), ('Daniel', 'Mercer'), ('Priya', 'Foster'),
    ('Aaron', 'Blake'), ('Leena', 'Harris'), ('Owen', 'Carter'),
    ('Tara', 'Bennett'), ('Noah', 'Reed'), ('Iris', 'Parker'),
    ('Evan', 'Cooper'),
]
INK = (0.06, 0.18, 0.42)
RED = (0.72, 0.10, 0.11)


def write(page, x, y, value, size=8):
    page.insert_text((x, y), str(value), fontname='helv', fontsize=size, color=INK, overlay=True)


def warning(page):
    # Clearly identify the record as synthetic, without obscuring the form fields.
    page.draw_rect(fitz.Rect(40, 754, 573, 775), fill=(1, 0.94, 0.93), color=RED, width=0.6)
    page.insert_text((56, 769), 'SYNTHETIC RESEARCH SAMPLE - NOT A VALID MEDICAL RECORD',
                     fontsize=9.5, fontname='hebo', color=RED)


def stamp_937(p, name, mrn, when):
    # Original template page 3 = Form 475 (Part A); page 4 = Part C.
    part_a, part_c = p[0], p[1]
    for page in (part_a, part_c):
        write(page, 358, 65, name, 9)
        write(page, 358, 124 if page is part_a else 91, mrn, 9)
        warning(page)
    write(part_a, 359, 141, 'Synthetic Research Facility', 8)
    write(part_a, 117, 180, name, 9)
    write(part_a, 330, 210, 'Synthetic Research Facility', 8)
    # Simulated entry in the mandatory physician's Part C confirmation area.
    write(part_c, 44, 471, 'Simulated physician review for research only.', 8)
    write(part_c, 43, 707, 'SIMULATED SIGNATURE', 8)
    write(part_c, 394, 707, when.strftime('%m/%d/%Y'), 8)
    write(part_c, 488, 707, when.strftime('%I:%M %p'), 8)


def stamp_939(p, name, mrn, when):
    # Original template page 2 = admitting physician record; page 3 = confirmation.
    admission, confirmation = p[0], p[1]
    for page in (admission, confirmation):
        write(page, 357, 70, name, 9)
        write(page, 380, 134, mrn, 9)
        write(page, 416, 151, 'Research Facility', 8)
        warning(page)
    # The FIRST physician's completion timestamp is on page 2 (not the 48h confirmation).
    write(admission, 45, 705, 'SIMULATED SIGNATURE', 8)
    write(admission, 263, 705, 'RESEARCH MD', 8)
    write(admission, 394, 705, when.strftime('%m/%d/%Y'), 8)
    write(admission, 492, 705, when.strftime('%I:%M %p'), 8)
    # Do not invent a second physician sign-off; confirmation remains uncompleted.


def main():
    if not TEMPLATE_937.is_file() or not TEMPLATE_939.is_file():
        raise FileNotFoundError('Place the supplied OMH template PDFs in evaluation_dataset/templates/')
    OUT.mkdir(parents=True, exist_ok=True)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    if MANIFEST.exists() or list(OUT.glob('*.pdf')):
        raise FileExistsError('Form-based pilot already exists; will not overwrite it')

    records = []
    for i, (first, last) in enumerate(PATIENTS, 1):
        legal = '9.37' if i <= 5 else '9.39'
        name = f'{last.upper()}, {first.upper()}'
        mrn = f'SYN-PILOT-{i:04d}'
        completed = datetime(2026, 11, 16, 8) + timedelta(days=i-1, hours=RNG.randint(0, 9), minutes=RNG.randint(0, 59))
        filename = f'DocuRecon_SYNTHETIC_FORM_{legal.replace(".", "")}_{i:03d}.pdf'
        source = fitz.open(TEMPLATE_937 if legal == '9.37' else TEMPLATE_939)
        source_indices = [2, 3] if legal == '9.37' else [1, 2]
        doc = fitz.open()
        for idx in source_indices:
            doc.insert_pdf(source, from_page=idx, to_page=idx)
        source.close()
        if legal == '9.37':
            stamp_937(doc, name, mrn, completed)
        else:
            stamp_939(doc, name, mrn, completed)
        # Rasterize edited original-layout pages for the scanned-document benchmark.
        scan = fitz.open()
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            scanpage = scan.new_page(width=page.rect.width, height=page.rect.height)
            scanpage.insert_image(scanpage.rect, stream=pix.tobytes('png'))
        scan.save(OUT / filename, deflate=True)
        scan.close()
        doc.close()
        records.append({'document': filename, 'patient_name': name, 'mrn': mrn,
                        'legal_status': legal, 'completion_date': completed.strftime('%Y-%m-%d'),
                        'completion_time': completed.strftime('%H:%M'),
                        'completion_rule': 'PART_C_COMPLETION' if legal == '9.37' else 'FIRST_PHYSICIAN_COMPLETION',
                        'scenario': 'FORM_LAYOUT_PILOT', 'synthetic': 'true'})
    with MANIFEST.open('w', newline='', encoding='utf-8') as stream:
        w = csv.DictWriter(stream, fieldnames=records[0].keys())
        w.writeheader()
        w.writerows(records)
    print('Generated form-based synthetic PDFs:', len(records))
    print('Output:', OUT)
    print('Ground truth:', MANIFEST)


if __name__ == '__main__':
    main()
