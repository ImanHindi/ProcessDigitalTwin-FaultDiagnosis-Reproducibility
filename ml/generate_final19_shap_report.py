from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import shap

from features import CFG
from final19_common import MODEL_DIR, REPORT_DIR, build_or_load_feature_cache, supervised_frame

model_path=MODEL_DIR/'enhanced_xgboost.joblib'
if not model_path.exists():
    raise SystemExit('Missing enhanced_xgboost.joblib. Run train_final19_supervised.py first.')

package=joblib.load(model_path)
features=list(package['features'])
model=package['model']
data=build_or_load_feature_cache(rebuild=False)
S,_,classes,_=supervised_frame(data)
test=S[S.partition=='test'].copy()
if test.empty:
    raise SystemExit('No locked-test supervised windows available.')

n=min(int(CFG.get('shap_sample_rows',750)),len(test))
sample=test.sample(n=n,random_state=int(CFG['seed'])+1900)
X=sample.reindex(columns=features)
X_values=X.to_numpy(dtype=np.float32)

explainer=shap.TreeExplainer(model)
sv=explainer.shap_values(X_values)
if isinstance(sv,list):
    arr=np.stack(sv,axis=-1)
else:
    arr=np.asarray(sv)

if arr.ndim==3:
    if arr.shape[1]==len(features):
        importance=np.mean(np.abs(arr),axis=(0,2))
    elif arr.shape[2]==len(features):
        importance=np.mean(np.abs(arr),axis=(0,1))
    else:
        raise RuntimeError(f'Unexpected SHAP shape: {arr.shape}')
elif arr.ndim==2:
    importance=np.mean(np.abs(arr),axis=0)
else:
    raise RuntimeError(f'Unexpected SHAP shape: {arr.shape}')

out=pd.DataFrame({'feature':features,'mean_abs_shap':importance}).sort_values('mean_abs_shap',ascending=False)
out.to_csv(REPORT_DIR/'final19_xgboost_shap_importance.csv',index=False)
sample[['run_id','time_start','time_end','class_label']].to_csv(REPORT_DIR/'final19_shap_sample_manifest.csv',index=False)

show=out.head(min(20,len(out))).iloc[::-1]
fig,ax=plt.subplots(figsize=(9,8))
ax.barh(show['feature'],show['mean_abs_shap'])
ax.set_xlabel('Mean absolute SHAP value')
ax.set_ylabel('Feature')
ax.set_title('Final19 enhanced XGBoost global SHAP importance')
fig.tight_layout()
fig.savefig(REPORT_DIR/'final19_xgboost_shap_summary.png',dpi=600,bbox_inches='tight')
fig.savefig(REPORT_DIR/'final19_xgboost_shap_summary.pdf',bbox_inches='tight')
fig.savefig(REPORT_DIR/'final19_xgboost_shap_summary.svg',bbox_inches='tight')
plt.close(fig)

(REPORT_DIR/'final19_shap_metadata.json').write_text(json.dumps({
    'dataset':'FinalScientific_v4.6.3_Scientific1900',
    'model':'enhanced_xgboost',
    'sample_partition':'locked test (post hoc interpretability only; no tuning)',
    'sample_rows':int(n),
    'feature_count':len(features),
    'classes':classes.tolist(),
},indent=2),encoding='utf-8')
print('Saved Final19 SHAP report to',REPORT_DIR)
