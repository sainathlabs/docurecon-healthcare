"""V12.2-E experimental CRNN diagnostics, synthetic only, never clinical use.
Import the unchanged V12.2-D network/preprocessing. Saves final epoch even if 0% exact.
"""
import argparse
import csv
import json
import random
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader

from docurecon_v122d_train_crnn import (
    DateCRNN, DateImages, collate, decode_greedy, load_rows, read_partition,
    ALPHABET, H, W,
)


def edit_distance(a, b):
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(cur[-1] + 1, prev[j] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def evaluate(model, loader, device, collect_predictions=True):
    model.eval()
    criterion = nn.CTCLoss(blank=0, zero_infinity=False)
    total_loss = n = exact = errors = chars = blank_wins = timesteps = 0
    blank_sum = 0.0
    rows = []
    with torch.no_grad():
        for images, targets, lengths, texts, keys in loader:
            images, targets = images.to(device), targets.to(device)
            logits = model(images)
            t = logits.shape[0]
            if t < 2 * int(lengths.max()) - 1:
                # Conservative enough for repeated adjacent tokens; exact feasibility checked below.
                pass
            min_steps = [len(s) + sum(s[i] == s[i-1] for i in range(1,len(s))) for s in texts]
            if any(t < m for m in min_steps):
                raise ValueError(f'CTC sequence too short: available {t}, required max {max(min_steps)}')
            input_lengths = torch.full((images.size(0),), t, dtype=torch.long)
            loss = criterion(logits, targets, input_lengths, lengths)
            if not torch.isfinite(loss):
                raise ValueError('Non-finite CTC loss; check targets and sequence length')
            guesses = decode_greedy(logits)
            winners = logits.argmax(2)
            blank_wins += int((winners == 0).sum().item())
            timesteps += winners.numel()
            blank_sum += logits.exp()[:, :, 0].sum().item()
            total_loss += float(loss.item()) * len(texts)
            for key, truth, guess in zip(keys,texts,guesses):
                n += 1; exact += int(truth == guess)
                errors += edit_distance(truth, guess)
                chars += len(truth)
                if collect_predictions:
                    rows.append({'sample_key':key,'truth':truth,'prediction':guess,'exact':int(truth==guess)})
    return ({'loss':total_loss/n,'exact_accuracy':exact/n,'cer':errors/chars,
             'blank_winning_fraction':blank_wins/timesteps,
             'mean_blank_probability':blank_sum/timesteps,
             'n':n},rows)


def train_epoch(model, loader, device, optimizer):
    model.train()
    criterion = nn.CTCLoss(blank=0, zero_infinity=False)
    total = n = 0
    for images, targets, lengths, texts, _ in loader:
        images, targets = images.to(device), targets.to(device)
        logits = model(images)
        t = logits.shape[0]
        min_steps = [len(s)+sum(s[i]==s[i-1] for i in range(1,len(s))) for s in texts]
        if any(t < m for m in min_steps):
            raise ValueError(f'CTC infeasible: timesteps={t}, minimum needed={max(min_steps)}')
        input_lengths = torch.full((images.size(0),), t, dtype=torch.long)
        loss = criterion(logits, targets, input_lengths, lengths)
        if not torch.isfinite(loss):
            raise ValueError('Non-finite CTC loss detected')
        optimizer.zero_grad(); loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 5.)
        optimizer.step()
        total += float(loss.item()) * len(texts); n += len(texts)
    return total / n


def save_csv(path, rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['sample_key','truth','prediction','exact'])
        writer.writeheader();writer.writerows(rows)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--images-root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--epochs',type=int,default=30)
    p.add_argument('--batch-size',type=int,default=8)
    p.add_argument('--limit-train',type=int,default=16)
    p.add_argument('--lr',type=float,default=0.001)
    p.add_argument('--device',choices=('cpu','auto'),default='cpu')
    p.add_argument('--overfit',action='store_true',help='Evaluate the SAME training examples for debugging, not an independent evaluation')
    p.add_argument('--eval-limit',type=int,default=16)
    args=p.parse_args()
    if args.epochs<1 or args.batch_size<1 or args.limit_train<1:
        p.error('epochs, batch-size and limit-train must be >= 1')
    if not args.overfit:
        p.error('This V12.2-E diagnostic requires --overfit; do not report results as generalisation.')
    random.seed(123);np.random.seed(123);torch.manual_seed(123)
    torch.set_num_threads(min(4,torch.get_num_threads()))
    src=load_rows(args.manifest)
    all_train=read_partition(src,'TRAIN',args.images_root)
    train=all_train[:args.limit_train]
    if not train: p.error('No eligible training data')
    # ALL evaluation samples are from exactly the same training subset: intentional overfitting diagnostic.
    dev=train[:min(len(train),args.eval_limit)]
    dev_keys={r['sample_key'] for r in dev}
    if not dev_keys.issubset({r['sample_key'] for r in train}):
        raise AssertionError('Memorisation-eval samples must be a subset of training samples')
    device='cpu' if args.device=='cpu' or not torch.cuda.is_available() else 'cuda'
    loader=DataLoader(DateImages(train,args.images_root),batch_size=args.batch_size,shuffle=True,collate_fn=collate,num_workers=0)
    # Evaluate the whole same train set, with separate small preview of errors.
    inspect_loader=DataLoader(DateImages(train,args.images_root),batch_size=args.batch_size,shuffle=False,collate_fn=collate,num_workers=0)
    model=DateCRNN().to(device)
    optim=torch.optim.AdamW(model.parameters(),lr=args.lr)
    args.out.mkdir(parents=True,exist_ok=True)
    history=[]
    print(f'DIAGNOSTIC ONLY: training and evaluating the SAME {len(train)} examples. Device: {device}.')
    print('V12.2-D architecture and image preprocessing unchanged. No real-writer accuracy claims.')
    for epoch in range(1,args.epochs+1):
        loss=train_epoch(model,loader,device,optim)
        stats, predictions=evaluate(model,inspect_loader,device)
        history.append({'epoch':epoch,'train_batch_loss':loss,'same_samples_evaluation':stats})
        print(f'Epoch {epoch}/{args.epochs}: loss={loss:.4f} same_exact={stats["exact_accuracy"]:.3f} CER={stats["cer"]:.3f} blank_winners={stats["blank_winning_fraction"]:.3f}')
        # Crucial: save final model and predictions, regardless of exact accuracy.
        torch.save({'model':model.state_dict(),'alphabet':ALPHABET,'height':H,'width':W,
                    'epoch':epoch,'same_sample_metrics':stats,'diagnostic_only':True},args.out/'last_diagnostic.pt')
        save_csv(args.out/'last_predictions.csv',predictions)
        (args.out/'diagnostic_history.json').write_text(json.dumps({
            'warning':'SAME samples evaluated as trained; memorisation test ONLY, not held-out accuracy',
            'history':history},indent=2),encoding='utf-8')
    print('Saved final epoch:',epoch,'to:',args.out/'last_diagnostic.pt')
    print('Sample predictions (truth -> guess):')
    for r in predictions[:8]:
        print(f'  {r["sample_key"]}: {r["truth"]!r} -> {r["prediction"]!r}')
    print('Do not integrate this experimental model into clinical workflows.')

if __name__=='__main__':
    main()
