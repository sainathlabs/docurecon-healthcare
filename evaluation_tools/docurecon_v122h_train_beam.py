"""V12.2-H: Height-aware CRNN full synthetic training and held-out synthetic decoding.

Train only TRAIN role. Select best checkpoint by development CTC loss (not exact accuracy).
For speed, use greedy diagnostics each epoch; compute beam decoding on all development
samples at the end for both best and final checkpoints. NOT writer/style independent.
Never for clinical use.
"""
import argparse
import csv
import json
import random
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

from docurecon_v122d_train_crnn import ALPHABET, H, W, DateImages, collate, load_rows, read_partition, decode_greedy
from docurecon_v122e_diagnose_crnn import train_epoch, evaluate, edit_distance
from docurecon_v122f_train_improved import HeightAwareDateCRNN
from docurecon_v122g_compare_beam import prefix_beam_search


def select_partitions(manifest, root, limit_train=0, limit_eval=0):
    rows = load_rows(manifest)
    train = read_partition(rows, 'TRAIN', root)
    dev = read_partition(rows, 'DEV_EVAL_NOT_INDEPENDENT', root)
    if limit_train:
        train = train[:limit_train]
    if limit_eval:
        dev = dev[:limit_eval]
    train_keys = {r['sample_key'] for r in train}
    dev_keys = {r['sample_key'] for r in dev}
    if train_keys & dev_keys:
        raise ValueError('TRAIN and DEV sample keys overlap')
    return train, dev


def assess_model(model, loader, device, beam_width=10):
    model.eval()
    rows = []
    with torch.no_grad():
        for images, _, _, texts, keys in loader:
            log_probs = model(images.to(device))
            greedy = decode_greedy(log_probs)
            for j, (key, truth) in enumerate(zip(keys, texts)):
                beam = prefix_beam_search(log_probs[:,j,:].cpu().numpy(),beam_width=beam_width)
                rows.append({'sample_key':key, 'truth':truth, 'greedy':greedy[j], 'beam':beam,
                             'greedy_exact':int(greedy[j]==truth), 'beam_exact':int(beam==truth)})
    def score(field):
        errors=sum(edit_distance(r['truth'], r[field]) for r in rows)
        characters=sum(len(r['truth']) for r in rows)
        matches=sum(r['truth']==r[field] for r in rows)
        return {'exact_count':matches,'total':len(rows),'exact_accuracy':matches/len(rows),
                'cer':errors/characters}
    return {'greedy':score('greedy'),'beam':score('beam')}, rows


def write_predictions(path, rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['sample_key','truth','greedy','beam','greedy_exact','beam_exact'])
        writer.writeheader();writer.writerows(rows)


def make_checkpoint(model, epoch, metrics, label):
    return {'model':model.state_dict(), 'epoch':epoch, 'architecture':'HeightAwareDateCRNN',
            'alphabet':ALPHABET, 'height':H, 'width':W, 'synthetic_only':True,
            'selection':label, 'dev_greedy':metrics}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--images-root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--epochs',type=int,default=16)
    p.add_argument('--batch-size',type=int,default=32)
    p.add_argument('--lr',type=float,default=0.001)
    p.add_argument('--beam-width',type=int,default=10)
    p.add_argument('--limit-train',type=int,default=0)
    p.add_argument('--limit-eval',type=int,default=0)
    p.add_argument('--print-every',type=int,default=1)
    p.add_argument('--device',choices=['cpu','auto'],default='cpu')
    args=p.parse_args()
    if min(args.epochs,args.batch_size,args.beam_width,args.print_every)<1 or args.lr<=0:
        p.error('Epochs, batch size, beam width, print frequency and lr must be positive')
    if min(args.limit_train,args.limit_eval)<0:
        p.error('Sample limits cannot be negative')
    random.seed(123);np.random.seed(123);torch.manual_seed(123)
    torch.set_num_threads(min(4,torch.get_num_threads()))
    train,dev=select_partitions(args.manifest,args.images_root,args.limit_train,args.limit_eval)
    device='cuda' if args.device=='auto' and torch.cuda.is_available() else 'cpu'
    train_loader=DataLoader(DateImages(train,args.images_root),batch_size=args.batch_size,shuffle=True,
                            collate_fn=collate,num_workers=0)
    dev_loader=DataLoader(DateImages(dev,args.images_root),batch_size=args.batch_size,shuffle=False,
                          collate_fn=collate,num_workers=0)
    model=HeightAwareDateCRNN().to(device)
    optimizer=torch.optim.AdamW(model.parameters(),lr=args.lr)
    args.out.mkdir(parents=True,exist_ok=True)
    best_loss=float('inf');best_epoch=0;history=[]
    print(f'V12.2-H: device={device}, TRAIN={len(train)}, synthetic DEV={len(dev)}, epochs={args.epochs}')
    print('Development data are NOT writer/style independent; no real-handwriting accuracy claim.')
    for epoch in range(1,args.epochs+1):
        train_loss=train_epoch(model,train_loader,device,optimizer)
        dev_stats,_=evaluate(model,dev_loader,device,collect_predictions=False)
        history.append({'epoch':epoch,'train_loss':train_loss,'dev_greedy':dev_stats})
        if epoch==1 or epoch%args.print_every==0 or epoch==args.epochs:
            print(f'Epoch {epoch}/{args.epochs}: train_loss={train_loss:.4f} dev_loss={dev_stats["loss"]:.4f} '
                  f'dev_greedy_exact={dev_stats["exact_accuracy"]:.3f} dev_greedy_CER={dev_stats["cer"]:.3f}')
        if dev_stats['loss']<best_loss:
            best_loss=dev_stats['loss'];best_epoch=epoch
            torch.save(make_checkpoint(model,epoch,dev_stats,'best_dev_ctc_loss'),args.out/'best_dev_loss.pt')
        if epoch==args.epochs:
            torch.save(make_checkpoint(model,epoch,dev_stats,'last_epoch'),args.out/'last_epoch.pt')
        (args.out/'training_history.json').write_text(json.dumps({
            'warning':'synthetic development only; style/writer independence unknown',
            'train_count':len(train),'dev_count':len(dev),'history':history},indent=2),encoding='utf-8')

    # Decode both final and best checkpoints; preserve both without claiming generalisation.
    summaries={}
    for tag,filename in [('final','last_epoch.pt'),('best','best_dev_loss.pt')]:
        cp=torch.load(args.out/filename,map_location=device,weights_only=True)
        model.load_state_dict(cp['model'])
        stats,predictions=assess_model(model,dev_loader,device,args.beam_width)
        write_predictions(args.out/f'{tag}_dev_predictions.csv',predictions)
        summaries[tag]={'epoch':cp['epoch'],'metrics':stats}
        print(f'{tag.upper()} Epoch {cp["epoch"]}: greedy {stats["greedy"]["exact_count"]}/{len(dev)} '
              f'CER={stats["greedy"]["cer"]:.3f}; beam {stats["beam"]["exact_count"]}/{len(dev)} '
              f'CER={stats["beam"]["cer"]:.3f}')
    summary={'experiment':'V12.2-H synthetic development only', 'train_count':len(train),
             'dev_count':len(dev),'beam_width':args.beam_width,'best_epoch_by_dev_loss':best_epoch,
             'models':summaries,'warning':'NOT independently writer/style validated; not for clinical use'}
    (args.out/'comparison_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print('Reports:',args.out)
    print('NOT for clinical use; keep V10/V11 benchmark untouched.')


if __name__=='__main__':main()
