from __future__ import annotations
import argparse, joblib, numpy as np, pandas as pd
from sklearn.metrics import accuracy_score,balanced_accuracy_score,f1_score
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier
from features import CFG,load_runs
from final19_common import DATA_DIR,CACHE_DIR,REPORT_DIR,load_locked_split,FINAL_CODES

p=argparse.ArgumentParser();p.add_argument('--windows',nargs='+',type=int,default=[30,60,120]);p.add_argument('--n-jobs',type=int,default=int(CFG.get('training_n_jobs',2)));a=p.parse_args()
split=load_locked_split();part=dict(zip(split.run_id,split.partition)); results=[]
for w in a.windows:
    cache=CACHE_DIR/f'window_sensitivity_final19_w{w}_s{w}.joblib'
    if cache.exists():data=joblib.load(cache)
    else:
        print('Building',w,'s Final19 features...');data=load_runs([DATA_DIR],size=w,step=w);joblib.dump(data,cache,compress=0)
    data=data[data.supervised_usable==1].copy();data['partition']=data.run_id.astype(str).map(part);f=[c for c in data if '__' in c];data[f]=data[f].astype(np.float32)
    classes=np.array(sorted(data.class_label.astype(int).unique()),dtype=int)
    if not np.array_equal(classes,FINAL_CODES):raise RuntimeError(f'Class set wrong for {w}s: {classes.tolist()}')
    enc={int(c):i for i,c in enumerate(classes)}
    tr=data.partition=='train';va=data.partition=='validation';ytr=np.array([enc[int(v)] for v in data.loc[tr,'class_label']],int);yv=np.array([enc[int(v)] for v in data.loc[va,'class_label']],int)
    model=XGBClassifier(objective='multi:softprob',num_class=len(classes),eval_metric='mlogloss',tree_method='hist',max_bin=128,n_estimators=350,max_depth=6,learning_rate=.05,min_child_weight=2,subsample=.90,colsample_bytree=.90,reg_lambda=2.0,random_state=int(CFG['seed']),n_jobs=a.n_jobs)
    model.fit(data.loc[tr,f],ytr,sample_weight=compute_sample_weight('balanced',ytr).astype(np.float32),verbose=False);pred=model.predict(data.loc[va,f]).astype(int)
    row={'window_seconds':w,'step_seconds':w,'train_runs':data.loc[tr,'run_id'].nunique(),'validation_runs':data.loc[va,'run_id'].nunique(),'train_windows':int(tr.sum()),'validation_windows':int(va.sum()),'accuracy':float(accuracy_score(yv,pred)),'balanced_accuracy':float(balanced_accuracy_score(yv,pred)),'macro_f1':float(f1_score(yv,pred,average='macro',zero_division=0))};results.append(row);print(row)
pd.DataFrame(results).to_csv(REPORT_DIR/'final19_window_length_sensitivity_validation.csv',index=False)
print('NOTE: locked TEST was not used in window-length sensitivity.')
