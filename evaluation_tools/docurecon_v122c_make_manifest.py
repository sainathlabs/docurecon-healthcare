"""Create reproducible synthetic development partitions; no writer-independence claim.

Uses V12.2-B audited labels. Never rewrites original images or source labels.
This is NOT a scientifically independent held-out test until generative style provenance is established.
"""
import argparse
import csv
from collections import Counter
from pathlib import Path

ROLE_BY_SET_CLASS = {
    ('S1', 'CLEAN_RECOGNITION_CANDIDATE'): 'TRAIN',
    ('S3', 'CLEAN_RECOGNITION_CANDIDATE'): 'TRAIN',
    ('S4', 'DEVELOPMENT_HOLDOUT_CANDIDATE'): 'DEV_EVAL_NOT_INDEPENDENT',
    ('S2', 'OVERSIZE_CHALLENGE'): 'CHALLENGE_OVERSIZE',
    ('S2', 'INVALID_CALENDAR_CHALLENGE'): 'CHALLENGE_INVALID',
    ('S3', 'INVALID_CALENDAR_CHALLENGE'): 'CHALLENGE_INVALID',
    ('S4', 'INVALID_CALENDAR_CHALLENGE'): 'CHALLENGE_INVALID',
    ('S3', 'BLANK_FIELD'): 'CHALLENGE_BLANK',
    ('S4', 'BLANK_FIELD'): 'CHALLENGE_BLANK',
    ('S3', 'CORRECTION_CHALLENGE'): 'CHALLENGE_CORRECTION',
    ('S4', 'CORRECTION_CHALLENGE'): 'CHALLENGE_CORRECTION',
    ('S3', 'INCOMPLETE_CHALLENGE'): 'CHALLENGE_INCOMPLETE',
    ('S4', 'INCOMPLETE_CHALLENGE'): 'CHALLENGE_INCOMPLETE',
}

def make_partitions(rows, image_root, verify_images=True):
    keys = [r.get('sample_key', '') for r in rows]
    if len(keys) != 8000 or len(set(keys)) != 8000 or not all(keys):
        raise ValueError('Expected exactly 8000 unique nonempty sample keys')
    outputs = []
    for r in rows:
        role = ROLE_BY_SET_CLASS.get((r.get('dataset'), r.get('label_class')))
        if role is None:
            raise ValueError('Unrecognised source/class for ' + r['sample_key'])
        image_rel = r.get('image', '').replace('\\', '/')
        if not image_rel.startswith('images/') or '..' in Path(image_rel).parts:
            raise ValueError('Unsafe image path: ' + image_rel)
        image_path = image_root / image_rel
        if verify_images and not image_path.is_file():
            raise FileNotFoundError(str(image_path))
        label = r.get('label_text_exact', '')
        if role in ('TRAIN','DEV_EVAL_NOT_INDEPENDENT') and not label:
            raise ValueError('Missing recognition label for ' + r['sample_key'])
        result = dict(r)
        result['v122c_role'] = role
        result['v122c_label_to_recognise'] = label if role in ('TRAIN','DEV_EVAL_NOT_INDEPENDENT') else ''
        result['v122c_provenance_warning'] = 'SYNTHETIC_STYLES_NOT_VERIFIED_INDEPENDENT'
        outputs.append(result)
    return outputs

def write_csv(path, rows, fields):
    with path.open('w', newline='', encoding='utf-8-sig') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--audit', required=True, type=Path, help='V12.2-B date_label_audit.csv')
    p.add_argument('--images-root', required=True, type=Path, help='V12.2-A date_crops_v1 folder')
    p.add_argument('--out', required=True, type=Path)
    args = p.parse_args()
    with args.audit.open('r', newline='', encoding='utf-8-sig') as handle:
        rows = list(csv.DictReader(handle))
    output = make_partitions(rows, args.images_root)
    args.out.mkdir(parents=True, exist_ok=True)
    fields = list(output[0].keys())
    write_csv(args.out/'date_development_manifest.csv', output, fields)
    recognition = [r for r in output if r['v122c_role'] in ('TRAIN','DEV_EVAL_NOT_INDEPENDENT')]
    write_csv(args.out/'date_recognition_only.csv', recognition, fields)
    counts=Counter(r['v122c_role'] for r in output)
    with (args.out/'partition_summary.csv').open('w', newline='', encoding='utf-8-sig') as handle:
        writer=csv.writer(handle);writer.writerow(['role','count'])
        writer.writerows(sorted(counts.items()))
    print('Verified', len(output),'source images and labels')
    for role,count in sorted(counts.items()):print(' ',role, count)
    print('Saved:',args.out/'date_development_manifest.csv')
    print('IMPORTANT: Development evaluation is synthetic and NOT writer/style independent.')
    print('No source files or models modified. No actual training performed.')

if __name__ == '__main__':main()
