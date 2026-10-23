from __future__ import annotations
import argparse, json
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.metrics import balanced_accuracy_score, f1_score, precision_score, recall_score, roc_auc_score, average_precision_score

from features import CFG
from final19_common import MODEL_DIR, REPORT_DIR, build_or_load_feature_cache, feature_columns

p=argparse.ArgumentParser(); p.add_argument('--n-jobs',type=int,default=int(CFG.get('training_n_jobs',2))); p.add_argument('--rebuild-cache',action='store_true'); a=p.parse_args()
data=build_or_load_feature_cache(rebuild=a.rebuild_cache)
features=feature_columns(data); data[features]=data[features].astype(np.float32)
target_fpr=float(CFG.get('isolation_forest_target_fpr',0.05))

def binary_metrics(y,score,thr):
    y=np.asarray(y,int); score=np.asarray(score,float); pred=(score>=thr).astype(int)
    out={'balanced_accuracy':float(balanced_accuracy_score(y,pred)),'macro_f1':float(f1_score(y,pred,average='macro',zero_division=0)),'fault_precision':float(precision_score(y,pred,zero_division=0)),'fault_recall':float(recall_score(y,pred,zero_division=0)),'specificity':float((pred[y==0]==0).mean()) if np.any(y==0) else np.nan,'threshold':float(thr),'n':int(len(y))}
    if len(np.unique(y))==2:
        out['roc_auc']=float(roc_auc_score(y,score)); out['average_precision']=float(average_precision_score(y,score))
    return out,pred

print('='*68); print('FINAL19 HEALTHY-ONLY ISOLATION-FOREST BASELINES'); print('='*68)
htr=data[(data.partition=='train')&(data.run_target_label==0)]
hv=data[(data.partition=='validation')&(data.run_target_label==0)]
test=data[data.partition=='test']
if min(len(htr),len(hv),len(test))<1: raise RuntimeError('Insufficient healthy train/validation or test data.')

# Global IF
imp=SimpleImputer(strategy='median',keep_empty_features=True)
Xtr=imp.fit_transform(htr[features]).astype(np.float32,copy=False)
model=IsolationForest(n_estimators=int(CFG.get('isolation_forest_n_estimators',400)),max_samples=min(int(CFG.get('isolation_forest_max_samples',4096)),len(Xtr)),contamination='auto',random_state=int(CFG['seed'])+400,n_jobs=a.n_jobs)
model.fit(Xtr)
sv=-model.score_samples(imp.transform(hv[features]).astype(np.float32,copy=False)); thr=float(np.quantile(sv,1-target_fpr))
st=-model.score_samples(imp.transform(test[features]).astype(np.float32,copy=False)); yt=test.anomaly_label.astype(int).to_numpy(); gm,gpred=binary_metrics(yt,st,thr)
joblib.dump({'model':model,'imputer':imp,'threshold':thr,'features':features,'metrics':gm,'training_protocol':'healthy train only; threshold 95th percentile healthy validation'},MODEL_DIR/'isolation_forest.joblib',compress=3)
pd.DataFrame({'run_id':test.run_id,'time_start':test.time_start,'time_end':test.time_end,'true_anomaly':yt,'anomaly_score':st,'predicted_anomaly':gpred}).to_csv(REPORT_DIR/'global_isolation_forest_locked_test_predictions.csv',index=False)
(REPORT_DIR/'global_isolation_forest_metrics.json').write_text(json.dumps(gm,indent=2),encoding='utf-8')
print('Global IF:',gm)

# Mode-conditioned IF
mode_col='process_mode__last'; modes=pd.to_numeric(data[mode_col],errors='coerce').round().fillna(-1).astype(int); data=data.copy(); data['mode_eval']=modes
mode_models={}; rows=[]; all_y=[]; all_p=[]; all_s=[]; pred_parts=[]
for mode in sorted(m for m in data.mode_eval.unique() if 0<=m<=7):
    tr=data[(data.partition=='train')&(data.run_target_label==0)&(data.mode_eval==mode)]
    va=data[(data.partition=='validation')&(data.run_target_label==0)&(data.mode_eval==mode)]
    te=data[(data.partition=='test')&(data.mode_eval==mode)]
    if len(tr)<50 or len(va)<20 or len(te)<20:
        print(f'Mode {mode}: skipped support train={len(tr)} val={len(va)} test={len(te)}'); continue
    im=SimpleImputer(strategy='median',keep_empty_features=True); ztr=im.fit_transform(tr[features]).astype(np.float32,copy=False)
    m=IsolationForest(n_estimators=350,max_samples=min(2048,len(ztr)),contamination='auto',random_state=int(CFG['seed'])+500+mode,n_jobs=a.n_jobs); m.fit(ztr)
    vscore=-m.score_samples(im.transform(va[features]).astype(np.float32,copy=False)); th=float(np.quantile(vscore,1-target_fpr))
    score=-m.score_samples(im.transform(te[features]).astype(np.float32,copy=False)); y=te.anomaly_label.astype(int).to_numpy(); met,pred=binary_metrics(y,score,th); met['process_mode']=int(mode); rows.append(met)
    mode_models[int(mode)]={'imputer':im,'model':m,'threshold':th}; all_y.extend(y); all_p.extend(pred); all_s.extend(score)
    o=te[['run_id','time_start','time_end']].copy(); o['process_mode']=mode; o['true_anomaly']=y; o['anomaly_score']=score; o['predicted_anomaly']=pred; pred_parts.append(o)
all_y=np.asarray(all_y,int); all_p=np.asarray(all_p,int); all_s=np.asarray(all_s,float)
overall={'balanced_accuracy':float(balanced_accuracy_score(all_y,all_p)),'macro_f1':float(f1_score(all_y,all_p,average='macro',zero_division=0)),'fault_precision':float(precision_score(all_y,all_p,zero_division=0)),'fault_recall':float(recall_score(all_y,all_p,zero_division=0)),'specificity':float((all_p[all_y==0]==0).mean()),'roc_auc':float(roc_auc_score(all_y,all_s)) if len(np.unique(all_y))==2 else None,'average_precision':float(average_precision_score(all_y,all_s)) if len(np.unique(all_y))==2 else None,'modes_modelled':sorted(mode_models),'target_healthy_validation_fpr_per_mode':target_fpr}
joblib.dump({'mode_models':mode_models,'features':features,'mode_feature':mode_col,'overall_metrics':overall},MODEL_DIR/'mode_conditioned_isolation_forest.joblib',compress=3)
pd.DataFrame(rows).to_csv(REPORT_DIR/'mode_conditioned_isolation_forest_by_mode.csv',index=False)
pd.concat(pred_parts,ignore_index=True).to_csv(REPORT_DIR/'mode_conditioned_isolation_forest_locked_test_predictions.csv',index=False)
(REPORT_DIR/'mode_conditioned_isolation_forest_summary.json').write_text(json.dumps(overall,indent=2),encoding='utf-8')
print('Mode-conditioned IF:',overall); print('*** FINAL19 ANOMALY BASELINES COMPLETE ***')
