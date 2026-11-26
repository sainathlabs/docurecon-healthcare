"""V12.2-D experimental synthetic date CRNN+CTC, NOT clinical decision support.
Trains only TRAIN partition, evaluates only DEV_EVAL_NOT_INDEPENDENT.
Does not modify the DocuRecon application or source data.
"""
import argparse
import csv
import json
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
import torch
from torch import nn
from torch.utils.data import Dataset, DataLoader

ALPHABET = '0123456789./-'
CHAR_TO_ID = {c: i + 1 for i, c in enumerate(ALPHABET)}
ID_TO_CHAR = {v: k for k, v in CHAR_TO_ID.items()}
H, W = 48, 320


def encode(text):
    if not text or any(c not in CHAR_TO_ID for c in text):
        raise ValueError('Unsupported/empty training text: ' + repr(text))
    return [CHAR_TO_ID[c] for c in text]


def decode_greedy(logits):
    # logits [T,B,C]; CTC remove contiguous repeats before blanks
    best = logits.argmax(dim=2).transpose(0, 1).cpu().tolist()
    predictions = []
    for sequence in best:
        previous = -1
        chars = []
        for i in sequence:
            if i and i != previous:
                chars.append(ID_TO_CHAR[i])
            previous = i
        predictions.append(''.join(chars))
    return predictions


def load_image(path):
    with Image.open(path) as im:
        img = ImageOps.grayscale(im)
        # White background, black ink. Retain aspect ratio with white letterbox.
        scale = min(W / img.width, H / img.height)
        new_size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
        img = img.resize(new_size, Image.Resampling.BILINEAR)
        canvas = Image.new('L', (W, H), 255)
        canvas.paste(img, (0, (H-new_size[1])//2))
        arr = np.asarray(canvas, dtype=np.float32)
    return torch.from_numpy((255.0 - arr)[None, :, :] / 255.0)


class DateImages(Dataset):
    def __init__(self, records, root):
        self.records = records
        self.root = root

    def __len__(self):
        return len(self.records)

    def __getitem__(self, idx):
        row = self.records[idx]
        image_rel = row['image'].replace('\\', '/')
        path = self.root / image_rel
        label = row['v122c_label_to_recognise']
        return load_image(path), torch.tensor(encode(label), dtype=torch.long), label, row['sample_key']


def collate(batch):
    imgs, targets, texts, keys = zip(*batch)
    return (torch.stack(imgs), torch.cat(targets),
            torch.tensor([len(t) for t in targets], dtype=torch.long), texts, keys)


class DateCRNN(nn.Module):
    def __init__(self, n_classes=len(ALPHABET) + 1):
        super().__init__()
        self.cnn = nn.Sequential(
            nn.Conv2d(1, 32, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2, 2),
            nn.Conv2d(32, 64, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2, 2),
            nn.Conv2d(64, 96, 3, padding=1), nn.ReLU(),
            nn.Conv2d(96, 96, 3, padding=1), nn.ReLU(),
        )
        self.gru = nn.GRU(96, 96, num_layers=2, bidirectional=True, batch_first=True)
        self.fc = nn.Linear(192, n_classes)

    def forward(self, images):
        feats = self.cnn(images).mean(dim=2).transpose(1, 2)  # [B,T,96]
        seq, _ = self.gru(feats)
        return self.fc(seq).log_softmax(2).transpose(0, 1)  # [T,B,C]


def load_rows(path):
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    required = {'sample_key','image','v122c_role','v122c_label_to_recognise'}
    if not rows or not required.issubset(rows[0].keys()):
        raise ValueError('Not a V12.2-C date development manifest')
    keys = [r['sample_key'] for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate sample_key values')
    return rows


def read_partition(rows, role, root):
    out = []
    for r in rows:
        if r['v122c_role'] != role:
            continue
        label = r['v122c_label_to_recognise']
        encode(label)
        rel = Path(r['image'].replace('\\','/'))
        if rel.is_absolute() or '..' in rel.parts or rel.parts[0] != 'images':
            raise ValueError('Invalid image path: ' + str(rel))
        if not (root / rel).is_file():
            raise FileNotFoundError(str(root / rel))
        out.append(r)
    if not out:
        raise ValueError('Empty role: ' + role)
    return out


def run_epoch(model, loader, device, optimizer=None, prediction_rows=None):
    training = optimizer is not None
    model.train(training)
    loss_fn = nn.CTCLoss(blank=0, zero_infinity=True)
    total_loss = total_samples = total_correct = 0
    for images, targets, target_lengths, texts, keys in loader:
        images = images.to(device)
        targets = targets.to(device)
        lengths = target_lengths.to(device)
        with torch.set_grad_enabled(training):
            logits = model(images)
            time_lens = torch.full((images.size(0),), logits.size(0), dtype=torch.long)
            loss = loss_fn(logits, targets, time_lens, lengths)
            if training:
                optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 5.)
                optimizer.step()
        predictions = decode_greedy(logits.detach())
        n = len(texts)
        total_samples += n
        total_loss += loss.item() * n
        total_correct += sum(a == b for a,b in zip(predictions, texts))
        if prediction_rows is not None:
            prediction_rows.extend({'sample_key': k, 'truth': t, 'prediction': p, 'exact': int(t == p)}
                                   for k,t,p in zip(keys, texts, predictions))
    return {'loss': round(total_loss / total_samples, 5),
            'exact_accuracy': round(total_correct / total_samples, 5),
            'n': total_samples}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--images-root', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--epochs', type=int, default=8)
    p.add_argument('--batch-size', type=int, default=32)
    p.add_argument('--lr', type=float, default=0.001)
    p.add_argument('--limit-train', type=int, default=0, help='Smoke test only')
    p.add_argument('--limit-eval', type=int, default=0, help='Smoke test only')
    p.add_argument('--device', choices=['cpu','cuda','auto'], default='auto')
    args=p.parse_args()
    if args.epochs < 1 or args.batch_size < 1:
        p.error('epochs and batch size must be >= 1')
    random.seed(123); np.random.seed(123); torch.manual_seed(123)
    rows=load_rows(args.manifest)
    train=read_partition(rows,'TRAIN',args.images_root)
    evaluation=read_partition(rows,'DEV_EVAL_NOT_INDEPENDENT',args.images_root)
    if args.limit_train:
        train=train[:args.limit_train]
    if args.limit_eval:
        evaluation=evaluation[:args.limit_eval]
    device='cuda' if args.device=='auto' and torch.cuda.is_available() else ('cpu' if args.device=='auto' else args.device)
    if device=='cuda' and not torch.cuda.is_available():
        p.error('CUDA was requested but PyTorch CUDA is not available')
    args.out.mkdir(parents=True,exist_ok=True)
    training=DataLoader(DateImages(train,args.images_root), batch_size=args.batch_size,shuffle=True,collate_fn=collate,num_workers=0)
    testing=DataLoader(DateImages(evaluation,args.images_root), batch_size=args.batch_size,shuffle=False,collate_fn=collate,num_workers=0)
    model=DateCRNN().to(device)
    optimizer=torch.optim.AdamW(model.parameters(),lr=args.lr)
    print('Device:',device, '| TRAIN:',len(train),'| synthetic development evaluation:',len(evaluation))
    print('Evaluation is NOT writer/style independent. No real handwriting accuracy claim.')
    history=[]
    best=-1
    for epoch in range(1,args.epochs+1):
        train_stats=run_epoch(model,training,device,optimizer)
        pred=[]
        eval_stats=run_epoch(model,testing,device,prediction_rows=pred)
        history.append({'epoch':epoch,'train':train_stats,'dev_eval':eval_stats})
        print(f'Epoch {epoch}/{args.epochs}: train_loss={train_stats["loss"]:.4f} train_exact={train_stats["exact_accuracy"]:.3f} dev_exact={eval_stats["exact_accuracy"]:.3f}')
        if eval_stats['exact_accuracy']>best:
            best=eval_stats['exact_accuracy']
            torch.save({'model':model.state_dict(),'alphabet':ALPHABET,'height':H,'width':W,'epoch':epoch,'synthetic_dev_exact':best},args.out/'best_synthetic_dev.pt')
            with (args.out/'dev_predictions.csv').open('w',encoding='utf-8-sig',newline='') as f:
                w=csv.DictWriter(f,fieldnames=['sample_key','truth','prediction','exact'])
                w.writeheader();w.writerows(pred)
        with (args.out/'training_history.json').open('w',encoding='utf-8') as f:
            json.dump({'experiment':'synthetic CRNN-CTC baseline; not independently validated','history':history},f,indent=2)
    print('Saved checkpoint and reports:',args.out)
    print('Do not integrate into clinical workflow without independent real-writer testing.')

if __name__=='__main__':
    main()
