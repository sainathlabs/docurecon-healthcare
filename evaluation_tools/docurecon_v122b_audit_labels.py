"""DocuRecon V12.2-B: reproducible, conservative synthetic date-label audit.

No OCR, no training, no mutation of original manifest, labels, or images.
Day-first dates are validated as day/month/year ONLY for detecting impossible
calendar dates; OCR ground-truth text remains byte-for-byte unchanged.
This dataset does not contain writer/style provenance: no claim of an
independent handwriting validation split is possible.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import date
from pathlib import Path
import re

CSV_SOURCE = {
    'S1': 'date_labels.csv',
    'S2': 'date_labels_set2.csv',
    'S3': 'date_labels_set3.csv',
    'S4': 'date_labels_set4.csv',
}
DATE_PATTERN = re.compile(r'^\s*(\d{1,2})([./-])(\d{1,2})\2(\d{2}|\d{4})\s*$')


def read_csv(path: Path):
    with path.open('r', newline='', encoding='utf-8-sig') as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f'Missing CSV header: {path}')
        return list(reader)


def calendar_check(raw: str) -> str:
    """Validate complete DD-MM-YY[YY] dates without altering the written text."""
    match = DATE_PATTERN.fullmatch(raw)
    if not match:
        return 'NOT_A_COMPLETE_DATE'
    dd, _, mm, yyyy = match.groups()
    year = int(yyyy) if len(yyyy) == 4 else 2000 + int(yyyy)
    try:
        date(year, int(mm), int(dd))
    except ValueError:
        return 'IMPOSSIBLE_CALENDAR_DATE'
    return 'VALID_DAY_FIRST_DATE'


def class_for(r: dict, source: dict) -> tuple[str, str, str]:
    ds = r['dataset']
    raw = r['label_text_exact']
    category = (source.get('category') or r.get('category') or '').strip().lower()
    raw_blank = not raw.strip()
    source_blank = str(source.get('is_blank', '')).strip()
    source_complete = str(source.get('is_complete', '')).strip()
    flags = []
    if source_blank in ('0', '1') and (source_blank == '1') != raw_blank:
        flags.append('SOURCE_BLANK_FLAG_MISMATCH')
    if ds in ('S3', 'S4') and category == 'blank' and not raw_blank:
        flags.append('BLANK_CATEGORY_HAS_TEXT')
    if ds in ('S3', 'S4') and category != 'blank' and raw_blank:
        flags.append('NONBLANK_CATEGORY_MISSING_TEXT')
    if raw_blank:
        return 'BLANK_FIELD', 'NO_DATE', ';'.join(flags)
    if category == 'incomplete' or source_complete == '0':
        return 'INCOMPLETE_CHALLENGE', 'NOT_A_COMPLETE_DATE', ';'.join(flags)
    if category == 'corrected':
        validation = calendar_check(raw)
        return 'CORRECTION_CHALLENGE', validation, ';'.join(flags)

    validation = calendar_check(raw)
    if validation == 'IMPOSSIBLE_CALENDAR_DATE':
        return 'INVALID_CALENDAR_CHALLENGE', validation, ';'.join(flags)
    if validation == 'NOT_A_COMPLETE_DATE':
        return 'FORMAT_REVIEW', validation, ';'.join(flags)
    if ds == 'S2':
        return 'OVERSIZE_CHALLENGE', validation, ';'.join(flags)
    if ds == 'S4':
        return 'DEVELOPMENT_HOLDOUT_CANDIDATE', validation, ';'.join(flags)
    return 'CLEAN_RECOGNITION_CANDIDATE', validation, ';'.join(flags)


def run(manifest_path: Path, sources: Path, out: Path, check_images=True):
    manifest = read_csv(manifest_path)
    if len(manifest) != 8000:
        raise ValueError(f'Expected 8000 cropped records, got {len(manifest)}')
    source_rows = {}
    for dataset, filename in CSV_SOURCE.items():
        entries = read_csv(sources / filename)
        if len(entries) != 2000:
            raise ValueError(f'{filename}: expected 2000 labels, got {len(entries)}')
        ids = [e['box_id'] for e in entries]
        if len(set(ids)) != 2000 or set(ids) != {f'D{i:04d}' for i in range(1, 2001)}:
            raise ValueError(f'{filename}: IDs not unique/complete')
        source_rows[dataset] = {e['box_id']: e for e in entries}

    output = []
    seen = set()
    for r in manifest:
        key, ds, sid = r['sample_key'], r['dataset'], r['sample_id']
        if ds not in source_rows or key != f'{ds}_{sid}' or key in seen:
            raise ValueError(f'Duplicate or invalid manifest key: {key}')
        seen.add(key)
        original = source_rows[ds].get(sid)
        if original is None:
            raise ValueError(f'{key} not in source labels')
        src_label = original.get('date_text', original.get('label_text', ''))
        if src_label != r['label_text_exact']:
            raise ValueError(f'Label mismatch for {key}: manifest={r["label_text_exact"]!r} original={src_label!r}')
        if int(original['page']) != int(r['pdf_page']):
            raise ValueError(f'Page mismatch for {key}')
        img = manifest_path.parent / r['image']
        if check_images and not img.is_file():
            raise FileNotFoundError(f'Missing cropped image {img}')
        cls, validity, flags = class_for(r, original)
        outrow = dict(r)
        outrow.update({
            'source_category': original.get('category', r.get('category', '')),
            'label_class': cls,
            'calendar_validation_day_first': validity,
            'label_warning': flags,
            'proposed_role': (
                'TRAIN_CANDIDATE' if cls == 'CLEAN_RECOGNITION_CANDIDATE'
                else 'DEV_EVALUATION_CANDIDATE' if cls == 'DEVELOPMENT_HOLDOUT_CANDIDATE'
                else 'CHALLENGE_OR_NEGATIVE'
            ),
            'crop_verified': 'NO',
            'train_val_test_split': 'UNASSIGNED',
        })
        output.append(outrow)
    if len(seen) != 8000:
        raise ValueError('Expected 8000 unique keys')
    out.mkdir(parents=True, exist_ok=True)
    audit_path = out / 'date_label_audit.csv'
    with audit_path.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(output[0]))
        writer.writeheader()
        writer.writerows(output)
    counters = Counter((x['dataset'], x['label_class']) for x in output)
    status = Counter(x['label_class'] for x in output)
    warnings = [x for x in output if x['label_warning'] or x['label_class'] in ('FORMAT_REVIEW', 'INVALID_CALENDAR_CHALLENGE')]
    with (out/'label_issues.csv').open('w', newline='', encoding='utf-8-sig') as f:
        cols = ['sample_key','dataset','sample_id','label_text_exact','label_class','calendar_validation_day_first','label_warning']
        writer = csv.DictWriter(f,fieldnames=cols)
        writer.writeheader()
        writer.writerows([{k: x[k] for k in cols} for x in warnings])
    with (out/'classification_summary.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['dataset', 'label_class', 'count'])
        for (ds, cls), num in sorted(counters.items()):
            writer.writerow([ds,cls,num])
    print(f'Validated {len(output)} manifest records against original labels.')
    print('Label classifications:')
    for cls, count in sorted(status.items()):
        print(f'  {cls}: {count}')
    print(f'Issues requiring review: {len(warnings)}')
    print(f'Reports saved to: {out}')
    print('No splits assigned; no originals changed. Calendar interpretation assumes DAY FIRST ONLY for audit.')
    print('Writer/style-separated validation requires independent provenance; this audit does not establish it.')
    return output


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--sources',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--skip-image-check',action='store_true',help='For label-only audits when PNGs are unavailable')
    args=p.parse_args()
    run(args.manifest,args.sources,args.out,check_images=not args.skip_image_check)

if __name__=='__main__':
    main()
