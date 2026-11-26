"""V12.2-F: experimental CRNN with height-aware features. Synthetic memorisation diagnostic only.

Train/evaluate SAME small set to check learning, NOT model accuracy on new data.
Original V12.2-D/E scripts are not modified.
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
from docurecon_v122d_train_crnn import (ALPHABET, H, W, DateImages, collate, load_rows, read_partition)
from docurecon_v122e_diagnose_crnn import evaluate, train_epoch, save_csv


class HeightAwareDateCRNN(nn.Module):
    """Preserve 4 vertical bands rather than mean-pooling all ink across height."""
    def __init__(self, n_classes=len(ALPHABET)+1):
        super().__init__()
        self.cnn = nn.Sequential(
            nn.Conv2d(1, 32, 3, padding=1), nn.BatchNorm2d(32), nn.ReLU(inplace=True), nn.MaxPool2d(2,2),
            nn.Conv2d(32, 64, 3, padding=1), nn.BatchNorm2d(64), nn.ReLU(inplace=True), nn.MaxPool2d(2,2),
            nn.Conv2d(64, 96, 3, padding=1), nn.BatchNorm2d(96), nn.ReLU(inplace=True),
            nn.Conv2d(96, 96, 3, padding=1), nn.BatchNorm2d(96), nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool2d((4, None)),
        )
        self.gru = nn.GRU(96*4, 96, num_layers=2, bidirectional=True, batch_first=True)
        self.fc = nn.Linear(192, n_classes)

    def forward(self, images):
        features = self.cnn(images) # [B,96,4,T]
        batch, channels, bands, steps = features.shape
        features = features.permute(0,3,1,2).reshape(batch, steps, channels*bands)
        seq, _ = self.gru(features)
        return self.fc(seq).log_softmax(dim=2).transpose(0,1)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--images-root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--epochs',type=int,default=150)
    p.add_argument('--batch-size',type=int,default=1)
    p.add_argument('--limit-train',type=int,default=1)
    p.add_argument('--lr',type=float,default=0.001)
    p.add_argument('--device',choices=('cpu','auto'),default='cpu')
    p.add_argument('--overfit',action='store_true',help='Required: identical training/evaluation examples, debugging only')
    p.add_argument('--print-every',type=int,default=10)
    args=p.parse_args()
    if not args.overfit: p.error('Requires --overfit. Do not treat as held-out evaluation.')
    if min(args.epochs,args.batch_size,args.limit_train,args.print_every)<1: p.error('positive arguments required')
    random.seed(123); np.random.seed(123); torch.manual_seed(123)
    torch.set_num_threads(min(4,torch.get_num_threads()))
    all_rows=load_rows(args.manifest)
    rows=read_partition(all_rows,'TRAIN',args.images_root)[:args.limit_train]
    if not rows: p.error('No training examples')
    device='cuda' if args.device=='auto' and torch.cuda.is_available() else 'cpu'
    training=DataLoader(DateImages(rows,args.images_root),batch_size=args.batch_size,shuffle=True,collate_fn=collate,num_workers=0)
    checking=DataLoader(DateImages(rows,args.images_root),batch_size=args.batch_size,shuffle=False,collate_fn=collate,num_workers=0)
    model=HeightAwareDateCRNN().to(device)
    optimizer=torch.optim.AdamW(model.parameters(),lr=args.lr)
    args.out.mkdir(parents=True,exist_ok=True)
    history=[]
    print('V12.2-F HEIGHT-AWARE CRNN. Synthetic memorisation only. Device:',device,'Examples:',len(rows))
    for epoch in range(1,args.epochs+1):
        loss=train_epoch(model,training,device,optimizer)
        stats,predictions=evaluate(model,checking,device)
        history.append({'epoch':epoch,'train_loss':loss,'same_examples':stats})
        if epoch==1 or epoch%args.print_every==0 or stats['exact_accuracy']==1:
            print(f'Epoch {epoch}/{args.epochs}: loss={loss:.4f} same_exact={stats["exact_accuracy"]:.3f} CER={stats["cer"]:.3f} blank_winners={stats["blank_winning_fraction"]:.3f}')
            print('  example:',repr(predictions[0]['truth']),'->',repr(predictions[0]['prediction']))
        if epoch%10==0 or epoch==args.epochs or stats['exact_accuracy']==1:
            torch.save({'model':model.state_dict(),'epoch':epoch,'architecture':'HeightAwareDateCRNN',
                        'alphabet':ALPHABET,'height':H,'width':W,'diagnostic_only':True,
                        'same_example_metrics':stats},args.out/'last_diagnostic.pt')
            save_csv(args.out/'last_predictions.csv',predictions)
            (args.out/'diagnostic_history.json').write_text(json.dumps({
                'warning':'Same examples evaluated as trained; not a held-out benchmark',
                'history':history},indent=2),encoding='utf-8')
        if stats['exact_accuracy']==1:
            print('Memorisation success at epoch',epoch,'(not a generalisation result)')
            break
    print('Final model and predictions:',args.out)
    print('Do not use in clinical workflows.')

if __name__=='__main__': main()
