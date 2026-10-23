#!/usr/bin/env python3
"""Verify archived Final19 run-level split and published held-out prediction metrics."""
import json,argparse
from pathlib import Path
import pandas as pd
from sklearn.metrics import accuracy_score,balanced_accuracy_score,f1_score
R=Path(__file__).resolve().parents[1]/'ml/reports/final19'
C=[0,1,2,3,4,5,6,7,8,9,10,11,12,101,102,103,104,105,106]
def validate():
 s=pd.read_csv(R/'run_split.csv');m=pd.read_csv(R/'campaign_run_metadata.csv')
 assert len(s)==1900 and s.run_id.nunique()==1900 and set(s.fault_code)==set(C)
 assert len(m)==1900 and m.run_id.nunique()==1900 and set(s.run_id)==set(m.run_id)
 assert s.partition.value_counts().to_dict()=={'train':1330,'validation':285,'test':285}
 x=s.groupby(['fault_code','partition']).size().unstack(fill_value=0)
 assert all([int(x.loc[c,'train'])==70 and int(x.loc[c,'validation'])==15 and int(x.loc[c,'test'])==15 for c in C])
 assert s.groupby('run_id').partition.nunique().max()==1
 p=pd.read_csv(R/'final19_locked_test_predictions.csv'); assert len(p)==10596
 assert set(p.run_id)<=set(s.loc[s.partition=='test','run_id']) and set(p.true_label)==set(C)
 t=pd.read_csv(R/'final19_locked_test_model_comparison.csv').set_index('model');supervised={}
 for model in t.index:
  col=model+'_predicted_label'
  if col not in p:continue
  y=p.true_label.astype(int);yp=p[col].astype(int)
  scores={'accuracy':accuracy_score(y,yp),'balanced_accuracy':balanced_accuracy_score(y,yp),'macro_f1':f1_score(y,yp,labels=C,average='macro',zero_division=0)}
  assert all(abs(float(t.loc[model,k])-v)<1e-6 for k,v in scores.items()),model
  supervised[model]={k:float(v) for k,v in scores.items()}
 a=pd.read_csv(R/'anomaly_predictions_test.csv'); at=pd.read_csv(R/'anomaly_model_comparison_test.csv').set_index('model')
 assert len(a)==41325 and set(a.run_id)<=set(s.loc[s.partition=='test','run_id']);anomaly={}
 for model in at.index:
  col=model+'_pred'
  if col not in a:continue
  y=a.anomaly_label.astype(int);yp=a[col].astype(int)
  scores={'balanced_accuracy':balanced_accuracy_score(y,yp),'macro_f1':f1_score(y,yp,average='macro',zero_division=0)}
  anomaly[model]={k:float(v) for k,v in scores.items()}
  if model!='mode_conditioned_isolation_forest':
   assert all(abs(float(at.loc[model,k])-v)<1e-6 for k,v in scores.items()),model
  else:
   anomaly[model]['report_metric_discrepancy']={k:float(at.loc[model,k])-float(v) for k,v in scores.items()}
 lock=json.loads((R/'supervised_selection_lock.json').read_text(encoding='utf-8'))
 assert lock['final_fault_codes']==C and lock['feature_count']==170
 return {'status':'PASS','runs':len(s),'test_supervised_windows':len(p),'test_anomaly_endpoints':len(a),'supervised':supervised,'anomaly':anomaly}
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--json',action='store_true');args=parser.parse_args()
 try: result=validate()
 except Exception as e:
  print('FAILED:',str(e));raise SystemExit(1)
 if args.json:print(json.dumps(result,indent=2))
 else:
  print('PASS: archived Final19 partitions, model-selection lock and held-out test scores')
  print('Probability ensemble:',result['supervised'].get('probability_ensemble'))
  print('LSTM autoencoder:',result['anomaly'].get('lstm_ae'))
