"""V12.2-J: Diagnostic-only synthetic date OCR confidence / selective review audit.

No training, no clinical integration. Confidence statistics are uncalibrated.
The S4 development set is NOT independently writer/style validated.
"""
import argparse
import csv
import json
import math
import re
from collections import Counter
from datetime import date
from pathlib import Path

import torch
from torch.utils.data import DataLoader
from docurecon_v122d_train_crnn import ALPHABET, DateImages, collate, decode_greedy, load_rows, read_partition
from docurecon_v122f_train_improved import HeightAwareDateCRNN

DATE_RE = re.compile(r'^(\d{1,2})([./-])(\d{1,2})([./-])(\d{2}|\d{4})$')


def parse_calendar_day_first(s):
    """Diagnostic convention only; do NOT apply to real US OMH forms."""
    m = DATE_RE.fullmatch((s or '').strip())
    if not m:
        return None
    day, _, month, _, year = m.groups()
    yy = int(year)
    if len(year) == 2:
        yy += 2000  # audit convention; not a clinical century-inference rule
    try:
        return date(yy, int(month), int(day)).isoformat()
    except ValueError:
        return None


def summarise(rows):
    n = len(rows)
    exact = sum(r['exact'] for r in rows)
    cal_comparable = [r for r in rows if r['truth_calendar'] is not None and r['prediction_calendar'] is not None]
    cal_match = sum(r['truth_calendar'] == r['prediction_calendar'] for r in cal_comparable)
    wrong = [r for r in rows if not r['exact']]
    wrong_cal_valid = sum(r['prediction_calendar'] is not None for r in wrong)
    wrong_calendar = sum(r['prediction_calendar'] is not None and r['truth_calendar'] is not None and r['truth_calendar'] != r['prediction_calendar'] for r in rows)
    separator_only = sum(not r['exact'] and r['truth_calendar'] is not None and r['truth_calendar']==r['prediction_calendar'] for r in rows)
    return {'samples':n,'exact':exact,'exact_accuracy':exact/n if n else 0,
            'incorrect':len(wrong),'wrong_calendar_valid':wrong_cal_valid,
            'wrong_calendar_date':wrong_calendar, 'transcription_wrong_but_calendar_same':separator_only,
            'calendar_comparable_count':len(cal_comparable),'calendar_matching_count':cal_match,
            'greedy_beam_disagree':sum(r['disagreement'] for r in rows)}


def score_frames(log_probs):
    """Uncalibrated indicators: max-softmax across frames, character-winning frames only.

    Not P(predicted string correct). They can be high even on wrong dates.
    """
    p=log_probs.exp()
    confidence, winner=p.max(dim=1)
    second=p.topk(2,dim=1).values[:,1]
    nonblank=winner.ne(0)
    return {'mean_top_probability':float(confidence.mean()),
            'mean_nonblank_probability':float(confidence[nonblank].mean()) if bool(nonblank.any()) else 0.,
            'mean_probability_margin':float((confidence-second).mean()),
            'greedy_blank_fraction':float((~nonblank).float().mean())}


def selective_review(rows, thresholds):
    """Purely exploratory thresholds, evaluated on the same development set."""
    out=[]
    for threshold in thresholds:
        accepted=[r for r in rows if r['mean_top_probability']>=threshold and not r['disagreement'] and r['prediction_calendar'] is not None]
        wrong=sum(not r['exact'] for r in accepted)
        wrong_calendar=sum(r['truth_calendar'] is not None and r['prediction_calendar'] != r['truth_calendar'] for r in accepted)
        out.append({'threshold':threshold,'accepted':len(accepted),'reviewed':len(rows)-len(accepted),
                    'coverage':len(accepted)/len(rows) if rows else 0,
                    'wrong_transcriptions_accepted':wrong,'wrong_calendar_dates_accepted':wrong_calendar,
                    'wrong_transcription_rate_among_accepted':wrong/len(accepted) if accepted else None})
    return out


def read_predictions(path):
    with path.open(newline='',encoding='utf-8-sig') as f:
        rows=list(csv.DictReader(f))
    if not rows or not {'sample_key','truth','greedy','beam'}.issubset(rows[0]):
        raise ValueError('Expected V12.2-H best_dev_predictions.csv columns')
    if len(rows)!=len({r['sample_key'] for r in rows}):
        raise ValueError('Duplicate prediction IDs')
    return {r['sample_key']:r for r in rows}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint',type=Path,required=True)
    p.add_argument('--predictions',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--images-root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--batch-size',type=int,default=16)
    p.add_argument('--limit',type=int,default=0,help='Subset smoke test only; 0 means full S4 dev set')
    args=p.parse_args()
    if args.batch_size<1 or args.limit<0:
        p.error('Invalid batch size or limit')
    torch.set_num_threads(min(4,torch.get_num_threads()))
    cp=torch.load(args.checkpoint,map_location='cpu',weights_only=True)
    if cp.get('architecture')!='HeightAwareDateCRNN' or cp.get('alphabet')!=ALPHABET:
        raise ValueError('Checkpoint architecture/alphabet mismatch')
    expected=read_predictions(args.predictions)
    dev=read_partition(load_rows(args.manifest),'DEV_EVAL_NOT_INDEPENDENT',args.images_root)
    if not args.limit and set(expected)!={r['sample_key'] for r in dev}:
        raise ValueError('Predictions do not match full development manifest')
    if args.limit: dev=dev[:args.limit]
    model=HeightAwareDateCRNN().cpu().eval()
    model.load_state_dict(cp['model'],strict=True)
    loader=DataLoader(DateImages(dev,args.images_root),batch_size=args.batch_size,shuffle=False,collate_fn=collate,num_workers=0)
    data=[]
    with torch.no_grad():
        for images, _, _, labels, keys in loader:
            logits=model(images)
            greedy_now=decode_greedy(logits)
            for j,key in enumerate(keys):
                record=expected.get(key)
                if not record or record['truth']!=labels[j]:
                    raise ValueError('Prediction/manifest mismatch for '+key)
                if greedy_now[j]!=record['greedy']:
                    raise ValueError('Checkpoint/greedy predictions mismatch for '+key+'; verify best_dev_loss.pt')
                beam=record['beam']
                stat=score_frames(logits[:,j,:])
                truth_date=parse_calendar_day_first(labels[j]); predicted_date=parse_calendar_day_first(beam)
                data.append({'sample_key':key,'truth':labels[j],'greedy':record['greedy'],'beam':beam,
                            'exact':int(beam==labels[j]),'truth_calendar':truth_date,
                            'prediction_calendar':predicted_date,'calendar_correct':int(truth_date is not None and predicted_date==truth_date),
                            'disagreement':int(beam!=record['greedy']),**stat})
    summary=summarise(data)
    thresholds=[0.0,0.90,0.95,0.98,0.99,0.995]
    selectivity=selective_review(data,thresholds)
    args.out.mkdir(parents=True,exist_ok=True)
    fields=list(data[0])
    with (args.out/'confidence_audit.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(data)
    with (args.out/'review_thresholds.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(selectivity[0]));w.writeheader();w.writerows(selectivity)
    report={'checkpoint_epoch':cp.get('epoch'),'checkpoint_selection':cp.get('selection'),
            'summary':summary,'experimental_thresholds':selectivity,
            'warnings':['NOT real-writer independent','Softmax confidence is NOT calibrated likelihood of correctness',
                        'Thresholds estimated on the SAME synthetic development set; do not deploy or claim test performance',
                        'Calendar interpretation is DAY FIRST with 2-digit years mapped to 2000-2099 only for this audit',
                        'No automatic clinical date acceptance is authorised']}
    (args.out/'summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(f'V12.2-J | checkpoint epoch={cp.get("epoch")} | dev samples={len(data)} | no training')
    print(f'Beam exact: {summary["exact"]}/{summary["samples"]}; wrong: {summary["incorrect"]}')
    print(f'Wrong transcriptions with calendar-valid prediction: {summary["wrong_calendar_valid"]}')
    print(f'Wrong CALENDAR dates: {summary["wrong_calendar_date"]}')
    print(f'Wrong transcription but same calendar date: {summary["transcription_wrong_but_calendar_same"]}')
    print(f'Greedy/beam disagreement: {summary["greedy_beam_disagree"]}')
    print('Uncalibrated confidence thresholds (exploratory only):')
    for r in selectivity:
        print(f'  {r["threshold"]:.3f}  accepted={r["accepted"]} reviewed={r["reviewed"]} wrong_accepted={r["wrong_transcriptions_accepted"]} wrong_calendar_accepted={r["wrong_calendar_dates_accepted"]}')
    print('Saved reports:',args.out)
    print('IMPORTANT: No automatic acceptance; synthetic development audit ONLY.')

if __name__=='__main__':main()
