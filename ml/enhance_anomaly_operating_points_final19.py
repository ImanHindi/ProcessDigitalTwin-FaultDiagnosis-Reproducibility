from __future__ import annotations
import json,numpy as np,pandas as pd
from sklearn.metrics import accuracy_score,balanced_accuracy_score,confusion_matrix,f1_score,precision_score,recall_score,roc_auc_score,average_precision_score,roc_curve
from final19_common import REPORT_DIR
VAL=REPORT_DIR/'anomaly_predictions_validation.csv';TEST=REPORT_DIR/'anomaly_predictions_test.csv';OUT=REPORT_DIR/'anomaly_operating_point_enhancement';OUT.mkdir(exist_ok=True);DEEP=['dae_score','vae_score','cvae_score','lstm_ae_score']
def pct(ref,v):ref=np.sort(np.asarray(ref,float));return np.searchsorted(ref,np.asarray(v,float),side='right')/len(ref)
def met(y,s,t):
 p=(s>=t).astype(int);tn,fp,fn,tp=confusion_matrix(y,p,labels=[0,1]).ravel();return {'accuracy':float(accuracy_score(y,p)),'balanced_accuracy':float(balanced_accuracy_score(y,p)),'macro_f1':float(f1_score(y,p,average='macro',zero_division=0)),'fault_precision':float(precision_score(y,p,zero_division=0)),'fault_recall':float(recall_score(y,p,zero_division=0)),'specificity':float(tn/max(tn+fp,1)),'roc_auc':float(roc_auc_score(y,s)),'average_precision':float(average_precision_score(y,s)),'threshold':float(t)}
def balanced(y,s):fpr,tpr,th=roc_curve(y,s);return float(th[int(np.argmax(tpr-fpr))])
if not VAL.exists() or not TEST.exists():raise SystemExit('Run train_final19_deep_anomaly.py first.')
v=pd.read_csv(VAL);t=pd.read_csv(TEST);yv=v.anomaly_label.to_numpy(int);yt=t.anomaly_label.to_numpy(int);vc=[];tc=[]
for c in DEEP:
 if c not in v or c not in t:continue
 ref=v.loc[yv==0,c].to_numpy(float);vc.append(pct(ref,v[c]));tc.append(pct(ref,t[c]))
if not vc:raise SystemExit('Deep anomaly score columns are unavailable.')
vs=np.mean(vc,0);ts=np.mean(tc,0);thr5=float(np.quantile(vs[yv==0],.95));thrb=balanced(yv,vs);rows=[]
for policy,th in [('healthy_validation_5pct_fpr',thr5),('validation_balanced_accuracy',thrb)]:
 for split,y,s in [('validation',yv,vs),('test',yt,ts)]:rows.append({'model':'equal_weight_deep_score_ensemble','policy':policy,'split':split,**met(y,s,th)})
pd.DataFrame(rows).to_csv(OUT/'deep_score_ensemble_operating_points.csv',index=False);(OUT/'README.json').write_text(json.dumps({'components':[c for c in DEEP if c in v],'normalization':'empirical percentile relative to healthy validation scores','fusion':'unweighted arithmetic mean','note':'secondary operating-point sensitivity; primary benchmark remains validation-fixed healthy FPR'},indent=2));print(pd.DataFrame(rows).to_string(index=False))
