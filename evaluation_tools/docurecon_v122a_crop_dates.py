"""Extract DocuRecon handwritten-date *PDF-vector* research sheet crops.

PDF text is NEVER used to read the handwritten date; it is used only to find the
sample ID. Labels are copied verbatim from the supplied CSVs. No date normalization.
Preserve original sources and original labels. Synthetic development ONLY.
"""
from __future__ import annotations
import argparse
import csv
from pathlib import Path
import re
from collections import Counter
import fitz

SOURCES = (
    ('S1','DocuRecon_dates_handwritten.pdf','date_labels.csv'),
    ('S2','DocuRecon_dates_set2_large_overlap.pdf','date_labels_set2.csv'),
    ('S3','DocuRecon_dates_set3_mixed.pdf','date_labels_set3.csv'),
    ('S4','DocuRecon_dates_set4_mixed.pdf','date_labels_set4.csv'),
)
ID_PATTERN=re.compile(r'^D\d{4}$')


def read_csv(path):
    with path.open('r',newline='',encoding='utf-8-sig') as f:
        reader=csv.DictReader(f)
        if 'box_id' not in reader.fieldnames or 'page' not in reader.fieldnames:
            raise ValueError(f'Missing box_id/page in {path}')
        rows=list(reader)
    ids=[r['box_id'] for r in rows]
    if len(rows)!=2000 or len(set(ids)) != 2000 or set(ids)!={f'D{i:04d}' for i in range(1,2001)}:
        raise ValueError(f'Expected D0001..D2000 exactly once: {path}')
    return {r['box_id']:r for r in rows}


def find_boxes(page):
    # These are *printed* empty field rectangles. Handwriting vector drawings
    # are NOT selected because their bounds do not match the field geometry.
    boxes=[]
    for drawing in page.get_drawings():
        r=drawing['rect']
        if (len(drawing['items'])==1 and drawing['items'][0][0]=='re' and
           90 < r.width < 130 and 27 < r.height < 30 and
           20 < r.x0 < 550 and 30 < r.y0 < 755):
            boxes.append(r)
    return sorted(boxes,key=lambda r:(round(r.y0,1),r.x0))


def find_id_positions(page):
    ids={}
    for w in page.get_text('words'):
        word=w[4]
        if ID_PATTERN.fullmatch(word):
            if word in ids:
                raise ValueError(f'Duplicate sample ID {word} on page')
            ids[word]=fitz.Rect(w[:4])
    return ids


def box_for_id(id_rect,boxes):
    # IDs are immediately to the right of their corresponding field.
    # Never guess when the geometry doesn't establish one unique match.
    matches=[r for r in boxes if 0 < id_rect.x0-r.x1 < 13 and abs(id_rect.y0-r.y0)<15]
    if len(matches)!=1:
        raise ValueError(f'Expected one box to left of label {id_rect}; got {len(matches)}')
    return matches[0]


def category(row,dataset):
    if dataset in ('S3','S4'):
        return (row.get('category') or 'unspecified').strip().lower()
    return 'large_overlap_challenge' if dataset=='S2' else 'clean_synthetic'


def extract_set(dataset,pdf,labels,out,dpi=200,limit=0):
    rows=read_csv(labels)
    target=out/'images'/dataset
    target.mkdir(parents=True,exist_ok=True)
    results=[]
    visited=set()
    with fitz.open(pdf) as doc:
        if len(doc)!=35:
            raise ValueError(f'Expected 35 pages: {pdf}, found {len(doc)}')
        for page_index,page in enumerate(doc):
            boxes=find_boxes(page)
            ids=find_id_positions(page)
            if len(boxes)!=len(ids):
                raise ValueError(f'{pdf.name} page {page_index+1}: {len(boxes)} boxes, {len(ids)} IDs')
            for sample_id, id_box in sorted(ids.items()):
                if sample_id not in rows:
                    raise ValueError(f'Missing CSV row: {dataset} {sample_id}')
                row=rows[sample_id]
                if int(row['page']) != page_index+1:
                    raise ValueError(f'Page mismatch: {dataset} {sample_id} pdf={page_index+1}, csv={row["page"]}')
                rect=box_for_id(id_box,boxes)
                if rect.intersects(id_box):
                    raise AssertionError(f'ID intrudes into crop: {sample_id}')
                if sample_id in visited:
                    raise ValueError(f'Duplicate sample ID in PDF: {sample_id}')
                visited.add(sample_id)
                # Whole box including its printed Date label. This mirrors a
                # cropped clinical form field. The sample ID is outside.
                crop=fitz.Rect(rect.x0,rect.y0,rect.x1,rect.y1)
                # Small inwards nudge avoids sampling the neighboring row.
                pix=page.get_pixmap(matrix=fitz.Matrix(dpi/72,dpi/72),clip=crop,
                                       colorspace=fitz.csRGB,alpha=False)
                filename=f'{dataset}_{sample_id}.png'
                pix.save(target/filename)
                label=row.get('date_text',row.get('label_text',''))
                results.append(dict(sample_key=f'{dataset}_{sample_id}',dataset=dataset,
                  sample_id=sample_id,pdf=pdf.name,pdf_page=page_index+1,
                  image=f'images/{dataset}/{filename}',label_text_exact=label,
                  category=category(row,dataset),is_blank=row.get('is_blank',''),
                  is_complete=row.get('is_complete',''),
                  requires_manual_crop_check='YES' if dataset=='S2' else 'SPOT_CHECK',
                  train_val_test_split='UNASSIGNED',
                  note='Box crop may lose handwriting outside border' if dataset=='S2' else ''))
                if limit and len(results)>=limit:
                    return results
    if len(visited)!=2000:
        raise ValueError(f'Expected 2000 IDs in {pdf}, got {len(visited)}')
    return results


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True,help='Folder with all four PDFs and four matching CSVs')
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--dpi',type=int,default=200)
    p.add_argument('--limit-per-set',type=int,default=0,help='For first visual smoke test; 0 means all samples')
    args=p.parse_args()
    if not (100<=args.dpi<=400):
        p.error('DPI must be 100..400')
    if args.limit_per_set<0:
        p.error('limit-per-set must be nonnegative')
    args.out.mkdir(parents=True,exist_ok=True)
    all_rows=[]
    for dataset,pdf_name,csv_name in SOURCES:
        pdf=args.source/pdf_name;csv_path=args.source/csv_name
        if not pdf.exists() or not csv_path.exists():
            raise FileNotFoundError(f'Missing {pdf} or {csv_path}')
        rows=extract_set(dataset,pdf,csv_path,args.out,args.dpi,args.limit_per_set)
        all_rows.extend(rows)
        print(f'{dataset}: saved {len(rows)} images')
    dest=args.out/'manifest.csv'
    with dest.open('w',newline='',encoding='utf-8-sig') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(all_rows[0]))
        writer.writeheader();writer.writerows(all_rows)
    print('TOTAL:',len(all_rows),'Manifest:',dest)
    print('NO TRAINING SPLIT ASSIGNED. Synthetic samples; review crops and labels first.')
    print('WARNING: S2 clipped writing is a stress test, not clean recognition training.')

if __name__=='__main__':main()
