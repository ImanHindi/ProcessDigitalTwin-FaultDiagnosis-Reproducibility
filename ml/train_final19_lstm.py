from __future__ import annotations

import argparse
import json
import time
import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import Dataset, DataLoader
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score, confusion_matrix, classification_report

from features import CFG, enrich, numeric_series, window_labels
from final19_common import DATA_DIR, FINAL_CODES, MODEL_DIR, REPORT_DIR, load_locked_split, run_files

p=argparse.ArgumentParser()
p.add_argument('--n-jobs',type=int,default=int(CFG.get('training_n_jobs',2)))
p.add_argument('--epochs',type=int,default=int(CFG.get('lstm_epochs',35)))
p.add_argument('--rescore-locked-test',action='store_true')
a=p.parse_args()

sentinel=REPORT_DIR/'FINAL19_LSTM_LOCKED_TEST_COMPLETE.txt'
if sentinel.exists() and not a.rescore_locked_test:
    raise SystemExit('Final19 LSTM locked test was already scored. Use --rescore-locked-test only to reproduce the frozen evaluation.')

torch.set_num_threads(max(1,a.n_jobs))
np.random.seed(int(CFG['seed']))
torch.manual_seed(int(CFG['seed']))
device=torch.device('cuda' if torch.cuda.is_available() else 'cpu')

split=load_locked_split()
partition_by_run=dict(zip(split.run_id.astype(str),split.partition.astype(str)))
files=run_files()
signals=list(CFG['signals'])
length=int(CFG['window_seconds']); step=int(CFG['window_step_seconds'])

seqs=[]; labels=[]; partitions=[]; run_ids=[]; tstarts=[]; tends=[]
print('Building Final19 raw 60-s supervised sequences...')
for k,path in enumerate(files,1):
    d=enrich(pd.read_csv(path))
    rid=str(d['run_id'].iloc[0])
    partition=partition_by_run.get(rid)
    if partition is None: raise RuntimeError(f'Run missing from locked split: {rid}')
    for start in range(0,len(d)-length+1,step):
        w=d.iloc[start:start+length]
        meta=window_labels(w)
        if meta['supervised_usable']!=1: continue
        cols=[numeric_series(w,s,np.nan).to_numpy(np.float32) for s in signals]
        seqs.append(np.column_stack(cols).astype(np.float32,copy=False))
        labels.append(int(meta['class_label'])); partitions.append(partition); run_ids.append(rid)
        tstarts.append(float(w['time'].iloc[0])); tends.append(float(w['time'].iloc[-1]))
    if k%100==0: print(f'  processed {k}/1900 files')

if not seqs: raise SystemExit('No supervised LSTM sequences created.')
X=np.stack(seqs).astype(np.float32,copy=False); del seqs
y_orig=np.asarray(labels,dtype=np.int16); partitions=np.asarray(partitions)
classes=np.array(sorted(np.unique(y_orig)),dtype=int)
if not np.array_equal(classes,FINAL_CODES): raise RuntimeError(f'LSTM classes incorrect: {classes.tolist()}')
enc={int(c):i for i,c in enumerate(classes)}
y=np.asarray([enc[int(v)] for v in y_orig],dtype=np.int64)
train_idx=np.flatnonzero(partitions=='train'); val_idx=np.flatnonzero(partitions=='validation'); test_idx=np.flatnonzero(partitions=='test')
print(f'Sequences train/val/test: {len(train_idx):,}/{len(val_idx):,}/{len(test_idx):,}')
print(f'Raw sequence array: {X.nbytes/1024**2:.1f} MiB')

# Train-only streaming normalization.
nf=X.shape[2]; sx=np.zeros(nf,np.float64); sx2=np.zeros(nf,np.float64); cnt=np.zeros(nf,np.float64)
for start in range(0,len(train_idx),512):
    ch=X[train_idx[start:start+512]]; mask=np.isfinite(ch); v=np.where(mask,ch,0.0)
    sx+=v.sum((0,1)); sx2+=(v.astype(np.float64)**2).sum((0,1)); cnt+=mask.sum((0,1))
mean=sx/np.maximum(cnt,1); var=sx2/np.maximum(cnt,1)-mean**2; scale=np.sqrt(np.maximum(var,1e-8)); scale[scale<1e-6]=1.0
for start in range(0,len(X),512):
    stop=min(start+512,len(X)); ch=X[start:stop]
    for j in range(nf):
        col=ch[:,:,j]; col[~np.isfinite(col)]=mean[j]; col[:]=(col-mean[j])/scale[j]
    X[start:stop]=ch

class IndexedDataset(Dataset):
    def __init__(self,X,y,idx): self.X=X; self.y=y; self.idx=np.asarray(idx,dtype=np.int64)
    def __len__(self): return len(self.idx)
    def __getitem__(self,i):
        j=int(self.idx[i]); return torch.from_numpy(self.X[j]),torch.tensor(self.y[j],dtype=torch.long)

bs=int(CFG.get('lstm_batch_size',128))
train_loader=DataLoader(IndexedDataset(X,y,train_idx),batch_size=bs,shuffle=True,num_workers=0)
val_loader=DataLoader(IndexedDataset(X,y,val_idx),batch_size=bs,shuffle=False,num_workers=0)
test_loader=DataLoader(IndexedDataset(X,y,test_idx),batch_size=bs,shuffle=False,num_workers=0)

counts=np.bincount(y[train_idx],minlength=len(classes)).astype(float); weights=counts.sum()/np.maximum(counts,1); weights/=weights.mean()
class_weights=torch.tensor(weights,dtype=torch.float32,device=device)

class Net(nn.Module):
    def __init__(self):
        super().__init__(); h=int(CFG.get('lstm_hidden_size',64)); nl=int(CFG.get('lstm_num_layers',2))
        self.lstm=nn.LSTM(input_size=nf,hidden_size=h,num_layers=nl,batch_first=True,dropout=0.25 if nl>1 else 0.0)
        self.head=nn.Sequential(nn.Linear(h,64),nn.ReLU(),nn.Dropout(0.25),nn.Linear(64,len(classes)))
    def forward(self,x): out,_=self.lstm(x); return self.head(out[:,-1])

model=Net().to(device); opt=torch.optim.AdamW(model.parameters(),lr=1e-3,weight_decay=1e-4); loss_fn=nn.CrossEntropyLoss(weight=class_weights)

def eval_loss(loader):
    model.eval(); total=0.; n=0
    with torch.no_grad():
        for xb,yb in loader:
            xb=xb.to(device); yb=yb.to(device); loss=loss_fn(model(xb),yb); total+=float(loss.item())*len(xb); n+=len(xb)
    return total/max(n,1)

best=float('inf'); best_state=None; wait=0; history=[]
for epoch in range(1,a.epochs+1):
    model.train(); tr=0.; n=0
    for xb,yb in train_loader:
        xb=xb.to(device); yb=yb.to(device); opt.zero_grad(set_to_none=True); loss=loss_fn(model(xb),yb); loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(),5.0); opt.step(); tr+=float(loss.item())*len(xb); n+=len(xb)
    vl=eval_loss(val_loader); tl=tr/max(n,1); history.append({'epoch':epoch,'train_loss':tl,'validation_loss':vl})
    print(f'Epoch {epoch:02d}: train={tl:.5f} validation={vl:.5f}')
    if vl<best-1e-4:
        best=vl; best_state={k:v.detach().cpu().clone() for k,v in model.state_dict().items()}; wait=0
    else: wait+=1
    if wait>=7: print('Early stopping.'); break
if best_state is None: raise RuntimeError('No valid LSTM checkpoint.')

pd.DataFrame(history).to_csv(REPORT_DIR/'lstm_training_history.csv',index=False)
model.load_state_dict(best_state); model.to(device); model.eval()
# Locked test only after validation-selected epoch is fixed.
pred=[]; probs=[]; t0=time.perf_counter()
with torch.no_grad():
    for xb,_ in test_loader:
        pr=torch.softmax(model(xb.to(device)),dim=1); probs.append(pr.cpu().numpy()); pred.extend(pr.argmax(1).cpu().numpy().tolist())
infer_ms=(time.perf_counter()-t0)/max(1,len(test_idx))*1000
pred=np.asarray(pred,dtype=int); prob=np.vstack(probs); true=y_orig[test_idx]; pred_orig=classes[pred]
metrics={
    'accuracy':float(accuracy_score(true,pred_orig)),
    'balanced_accuracy':float(balanced_accuracy_score(true,pred_orig)),
    'macro_f1':float(f1_score(true,pred_orig,average='macro',zero_division=0)),
    'inference_ms_per_window':float(infer_ms),'best_validation_loss':float(best),
    'epochs_completed':len(history),'device':str(device),'classes':classes.tolist(),
    'protocol':'training only; validation early stopping; locked test scored after checkpoint frozen',
}

model_pkg={'state_dict':model.cpu().state_dict(),'signals':signals,'classes':classes.tolist(),'input_size':nf,'hidden_size':int(CFG.get('lstm_hidden_size',64)),'num_layers':int(CFG.get('lstm_num_layers',2)),'scaler_mean':mean.astype(np.float32),'scaler_scale':scale.astype(np.float32),'window_seconds':length,'window_step_seconds':step,'dataset_version':'FinalScientific_v4.6.3_Scientific1900'}
torch.save(model_pkg,MODEL_DIR/'lstm.pt')
(REPORT_DIR/'lstm_metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
pd.DataFrame(confusion_matrix(true,pred_orig,labels=classes),index=classes,columns=classes).to_csv(REPORT_DIR/'confusion_lstm.csv')
(REPORT_DIR/'class_report_lstm.json').write_text(json.dumps(classification_report(true,pred_orig,labels=classes,output_dict=True,zero_division=0),indent=2),encoding='utf-8')
pd.DataFrame({'run_id':np.asarray(run_ids)[test_idx],'time_start':np.asarray(tstarts)[test_idx],'time_end':np.asarray(tends)[test_idx],'true_label':true,'predicted_label':pred_orig,'confidence':prob.max(axis=1)}).to_csv(REPORT_DIR/'lstm_locked_test_predictions.csv',index=False)
sentinel.write_text('Validation-selected LSTM checkpoint scored on locked Scientific1900 test.\n',encoding='utf-8')
print(metrics); print('*** FINAL19 LSTM LOCKED TEST COMPLETE ***')
