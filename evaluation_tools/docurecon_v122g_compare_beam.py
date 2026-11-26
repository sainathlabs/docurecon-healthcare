"""V12.2-G: Compare CTC prefix beam search vs greedy on SAME 16 synthetic training images.

DIAGNOSTIC ONLY. No training; no post-hoc year expansion; no clinical use.
"""
import argparse
import csv
import json
import math
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from docurecon_v122d_train_crnn import (
    ALPHABET, DateImages, collate, decode_greedy, load_rows, read_partition
)
from docurecon_v122e_diagnose_crnn import edit_distance
from docurecon_v122f_train_improved import HeightAwareDateCRNN

NEG_INF = float('-inf')


def logsum(a, b):
    """Stable log(exp(a)+exp(b)) including -infinity."""
    return math.logaddexp(a, b) if hasattr(math, 'logaddexp') else (
        b if a == NEG_INF else a if b == NEG_INF else
        max(a, b) + math.log1p(math.exp(-abs(a-b)))
    )


def update(beams, prefix, blank_term=NEG_INF, nonblank_term=NEG_INF):
    pb, pnb = beams.get(prefix, (NEG_INF, NEG_INF))
    beams[prefix] = (logsum(pb, blank_term), logsum(pnb, nonblank_term))


def prefix_beam_search(log_probs, beam_width=10):
    """Unconstrained CTC prefix-beam decoder for log_probs of shape [T, C].

    IDs: 0=blank; 1..len(ALPHABET) are characters. No date-format rules.
    """
    if beam_width < 1:
        raise ValueError('beam_width must be >= 1')
    if log_probs.ndim != 2 or log_probs.shape[1] != len(ALPHABET) + 1:
        raise ValueError('Expected [T, len(ALPHABET)+1] CTC log-probabilities')
    beams = {(): (0.0, NEG_INF)}
    for frame in log_probs:
        next_beams = {}
        blank_score = float(frame[0])
        for prefix, (pb, pnb) in beams.items():
            total = logsum(pb, pnb)
            update(next_beams, prefix, blank_term=total + blank_score)
            for char_id in range(1, len(ALPHABET) + 1):
                score = float(frame[char_id])
                if prefix and prefix[-1] == char_id:
                    # Repeated character without an intervening blank collapses.
                    update(next_beams, prefix, nonblank_term=pnb + score)
                    # Repeated character separated by blank is a new character.
                    update(next_beams, prefix + (char_id,), nonblank_term=pb + score)
                else:
                    update(next_beams, prefix + (char_id,), nonblank_term=total + score)
        beams = dict(sorted(next_beams.items(),
                            key=lambda kv: logsum(*kv[1]), reverse=True)[:beam_width])
    best = max(beams, key=lambda seq: logsum(*beams[seq]))
    return ''.join(ALPHABET[idx - 1] for idx in best)


def metrics(rows, field):
    n = len(rows)
    errors = sum(edit_distance(r['truth'], r[field]) for r in rows)
    chars = sum(len(r['truth']) for r in rows)
    return {'exact':sum(r['truth'] == r[field] for r in rows),
            'total':n,
            'exact_accuracy':sum(r['truth'] == r[field] for r in rows)/n,
            'cer':errors/chars}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', required=True, type=Path)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--images-root', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--limit', type=int, default=16)
    parser.add_argument('--beam-width', type=int, default=10)
    args = parser.parse_args()
    if args.limit < 1 or args.beam_width < 1:
        parser.error('--limit and --beam-width must be positive')
    if not args.checkpoint.is_file():
        parser.error(f'Checkpoint not found: {args.checkpoint}')
    torch.set_num_threads(min(4, torch.get_num_threads()))
    checkpoint = torch.load(args.checkpoint, map_location='cpu', weights_only=True)
    if checkpoint.get('architecture') != 'HeightAwareDateCRNN' or not checkpoint.get('diagnostic_only'):
        parser.error('Expected a V12.2-F diagnostic height-aware CRNN checkpoint')
    if checkpoint.get('alphabet') != ALPHABET:
        parser.error('Checkpoint alphabet does not match code alphabet')
    if checkpoint.get('epoch') != 200:
        print('NOTE: checkpoint epoch is', checkpoint.get('epoch'), '(not necessarily 200)')
    records = read_partition(load_rows(args.manifest), 'TRAIN', args.images_root)[:args.limit]
    loader = DataLoader(DateImages(records, args.images_root), batch_size=1,
                        shuffle=False, collate_fn=collate, num_workers=0)
    model = HeightAwareDateCRNN().cpu().eval()
    model.load_state_dict(checkpoint['model'], strict=True)
    rows=[]
    with torch.no_grad():
        for images, _, _, texts, keys in loader:
            log_probs = model(images)
            greedy = decode_greedy(log_probs)[0]
            beam = prefix_beam_search(log_probs[:, 0, :].cpu().numpy(), args.beam_width)
            rows.append({'sample_key':keys[0], 'truth':texts[0], 'greedy':greedy,
                         'beam':beam, 'greedy_exact':int(greedy == texts[0]),
                         'beam_exact':int(beam == texts[0])})
    result={'experiment':'V12.2-G same-training-samples CTC decoding diagnostic',
            'checkpoint_epoch':checkpoint.get('epoch'),
            'checkpoint':str(args.checkpoint),
            'beam_width':args.beam_width,
            'greedy':metrics(rows,'greedy'),
            'beam':metrics(rows,'beam'),
            'note':'Not writer/style independent; not a generalisation benchmark'}
    args.out.mkdir(parents=True,exist_ok=True)
    with (args.out/'beam_vs_greedy.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    (args.out/'beam_summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('V12.2-G: decoding ONLY, no retraining. Checkpoint epoch:',result['checkpoint_epoch'])
    for row in rows:
        print(f"  {row['sample_key']}  {row['truth']!r} -> greedy {row['greedy']!r} | beam {row['beam']!r}")
    print(f"Greedy: {result['greedy']['exact']}/{len(rows)} exact, CER={result['greedy']['cer']:.3f}")
    print(f"Beam:   {result['beam']['exact']}/{len(rows)} exact, CER={result['beam']['cer']:.3f}")
    print('Saved:', args.out/'beam_vs_greedy.csv')
    print('Synthetic memorisation diagnostic only. Do not use in clinical workflows.')


if __name__ == '__main__':
    main()
