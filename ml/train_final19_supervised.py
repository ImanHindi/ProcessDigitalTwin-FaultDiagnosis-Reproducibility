from __future__ import annotations

import argparse
import gc
import json
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, ExtraTreesClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.metrics import (
    accuracy_score, balanced_accuracy_score, classification_report,
    confusion_matrix, f1_score, log_loss, roc_auc_score,
    top_k_accuracy_score,
)
from sklearn.preprocessing import label_binarize
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier

from features import CFG
from final19_common import (
    FINAL_CODES, PROCESS_CODES, SENSOR_CODES,
    MODEL_DIR, REPORT_DIR,
    build_or_load_feature_cache, supervised_frame,
)

parser=argparse.ArgumentParser()
parser.add_argument('--n-jobs', type=int, default=int(CFG.get('training_n_jobs',2)))
parser.add_argument('--rebuild-cache', action='store_true')
parser.add_argument('--rescore-locked-test', action='store_true',
                    help='Allow regeneration of locked-test reports after the selection lock already exists. Does not change selection.')
args=parser.parse_args()

SELECTION_LOCK=REPORT_DIR/'supervised_selection_lock.json'
TEST_SENTINEL=REPORT_DIR/'FINAL19_SUPERVISED_LOCKED_TEST_COMPLETE.txt'

if TEST_SENTINEL.exists() and not args.rescore_locked_test:
    raise SystemExit(
        'Locked-test scoring was already completed. To protect the final test set, this script will not rerun by default. '
        'If you only need to regenerate identical reports using the frozen selection lock, add --rescore-locked-test.'
    )


def make_xgb(params, n_classes, seed):
    return XGBClassifier(
        objective='multi:softprob',
        num_class=int(n_classes),
        eval_metric='mlogloss',
        tree_method='hist',
        n_jobs=args.n_jobs,
        random_state=int(seed),
        verbosity=1,
        **{k:v for k,v in params.items() if k!='name'},
    )


def safe_auc(y, prob, n_classes):
    try:
        b=label_binarize(y, classes=np.arange(n_classes))
        valid=np.array([len(np.unique(b[:,j]))==2 for j in range(b.shape[1])])
        if valid.sum()<2:
            return np.nan
        return float(roc_auc_score(b[:,valid], prob[:,valid], average='macro', multi_class='ovr'))
    except Exception:
        return np.nan


def expected_calibration_error(y, prob, bins=15):
    conf=prob.max(axis=1)
    pred=prob.argmax(axis=1)
    correct=(pred==y).astype(float)
    edges=np.linspace(0,1,bins+1)
    total=len(y)
    ece=0.0
    for a,b in zip(edges[:-1],edges[1:]):
        idx=(conf>=a)&(conf<(b if b<1 else b+1e-12))
        if idx.any():
            ece += idx.mean()*abs(correct[idx].mean()-conf[idx].mean())
    return float(ece)


def metrics(y, prob):
    pred=prob.argmax(axis=1)
    return {
        'accuracy':float(accuracy_score(y,pred)),
        'balanced_accuracy':float(balanced_accuracy_score(y,pred)),
        'macro_f1':float(f1_score(y,pred,average='macro',zero_division=0)),
        'weighted_f1':float(f1_score(y,pred,average='weighted',zero_division=0)),
        'macro_roc_auc':safe_auc(y,prob,prob.shape[1]),
        'top3_accuracy':float(top_k_accuracy_score(y,prob,k=min(3,prob.shape[1]),labels=np.arange(prob.shape[1]))),
        'log_loss':float(log_loss(y,prob,labels=np.arange(prob.shape[1]))),
        'ece_15bin':expected_calibration_error(y,prob,15),
    }


def family_of_code(code):
    code=int(code)
    if code==0: return 0
    if code in set(PROCESS_CODES.tolist()): return 1
    if code in set(SENSOR_CODES.tolist()): return 2
    raise ValueError(code)


def fit_local_xgb(X, original_y, codes, params, seed):
    codes=np.asarray(codes,dtype=int)
    mask=np.isin(original_y,codes)
    local_map={int(code):i for i,code in enumerate(codes)}
    y=np.array([local_map[int(v)] for v in original_y[mask]],dtype=int)
    model=make_xgb(params,len(codes),seed)
    model.fit(
        X.iloc[np.flatnonzero(mask)],y,
        sample_weight=compute_sample_weight('balanced',y).astype(np.float32),
        verbose=False,
    )
    return model


def compose_hierarchical(family_model, process_model, sensor_model, X, original_classes):
    code_to_col={int(c):i for i,c in enumerate(original_classes)}
    fp=family_model.predict_proba(X)
    pp=process_model.predict_proba(X)
    sp=sensor_model.predict_proba(X)
    out=np.zeros((len(X),len(original_classes)),dtype=np.float32)
    out[:,code_to_col[0]]=fp[:,0]
    for j,code in enumerate(PROCESS_CODES):
        out[:,code_to_col[int(code)]]=fp[:,1]*pp[:,j]
    for j,code in enumerate(SENSOR_CODES):
        out[:,code_to_col[int(code)]]=fp[:,2]*sp[:,j]
    den=out.sum(axis=1,keepdims=True)
    den[den<=0]=1.0
    return out/den


def candidate_weights():
    # Small, explicit validation-only grid; includes legacy 2:1:1 but does not privilege it.
    vals=[1,2,3]
    return [(a,b,c) for a in vals for b in vals for c in vals]


def fit_rf(X,y,seed,trees=None):
    pipe=Pipeline([
        ('imputer',SimpleImputer(strategy='median',keep_empty_features=True)),
        ('model',RandomForestClassifier(
            n_estimators=int(trees or CFG.get('rf_n_estimators',500)),
            max_depth=int(CFG.get('rf_max_depth',24)),
            min_samples_leaf=int(CFG.get('rf_min_samples_leaf',2)),
            max_samples=float(CFG.get('rf_max_samples',0.85)),
            class_weight='balanced_subsample',
            n_jobs=args.n_jobs,random_state=seed,
        )),
    ])
    sw=compute_sample_weight('balanced',y).astype(np.float32)
    pipe.fit(X,y,model__sample_weight=sw)
    return pipe


def fit_extra(X,y,seed,trees=500):
    pipe=Pipeline([
        ('imputer',SimpleImputer(strategy='median',keep_empty_features=True)),
        ('model',ExtraTreesClassifier(
            n_estimators=trees,max_depth=30,min_samples_leaf=1,
            max_features='sqrt',class_weight='balanced',
            n_jobs=args.n_jobs,random_state=seed,
        )),
    ])
    pipe.fit(X,y)
    return pipe


def save_eval(name, y_true, prob, classes, meta):
    pred=prob.argmax(axis=1)
    pred_original=classes[pred]
    true_original=classes[y_true]
    pd.DataFrame(
        confusion_matrix(true_original,pred_original,labels=classes),
        index=classes,columns=classes,
    ).to_csv(REPORT_DIR/f'confusion_{name}.csv')
    (REPORT_DIR/f'class_report_{name}.json').write_text(
        json.dumps(classification_report(true_original,pred_original,labels=classes,output_dict=True,zero_division=0),indent=2),
        encoding='utf-8')
    return {**meta,**metrics(y_true,prob)}


print('='*72)
print('FINAL19 SUPERVISED TRAINING — LOCKED SCIENTIFIC1900 SPLIT')
print('='*72)
data=build_or_load_feature_cache(rebuild=args.rebuild_cache)
S,features,classes,code_to_encoded=supervised_frame(data)
if not np.array_equal(classes,FINAL_CODES):
    raise RuntimeError('Final class order changed unexpectedly.')

idx={p:S.index[S.partition==p] for p in ['train','validation','test']}
Xtr=S.loc[idx['train'],features]
Xv=S.loc[idx['validation'],features]
Xt=S.loc[idx['test'],features]
ytr=S.loc[idx['train'],'encoded_label'].to_numpy(int)
yv=S.loc[idx['validation'],'encoded_label'].to_numpy(int)
yt=S.loc[idx['test'],'encoded_label'].to_numpy(int)
ytr_orig=S.loc[idx['train'],'class_label'].to_numpy(int)
yv_orig=S.loc[idx['validation'],'class_label'].to_numpy(int)

print(f'Features: {len(features)}')
print(f'Supervised windows train/val/test: {len(Xtr):,}/{len(Xv):,}/{len(Xt):,}')
print(f'Independent runs train/val/test: {S.loc[idx["train"],"run_id"].nunique()}/'
      f'{S.loc[idx["validation"],"run_id"].nunique()}/{S.loc[idx["test"],"run_id"].nunique()}')

xgb_candidates=[
    dict(name='balanced_depth6',n_estimators=500,max_depth=6,learning_rate=0.045,min_child_weight=2,gamma=0.0,subsample=0.90,colsample_bytree=0.90,reg_alpha=0.0,reg_lambda=2.0,max_bin=128),
    dict(name='regularized_depth5',n_estimators=600,max_depth=5,learning_rate=0.04,min_child_weight=3,gamma=0.05,subsample=0.90,colsample_bytree=0.85,reg_alpha=0.05,reg_lambda=3.0,max_bin=128),
    dict(name='deeper_depth8',n_estimators=500,max_depth=8,learning_rate=0.035,min_child_weight=2,gamma=0.0,subsample=0.85,colsample_bytree=0.85,reg_alpha=0.02,reg_lambda=3.0,max_bin=128),
    dict(name='conservative_depth4',n_estimators=700,max_depth=4,learning_rate=0.035,min_child_weight=4,gamma=0.10,subsample=0.92,colsample_bytree=0.90,reg_alpha=0.08,reg_lambda=4.0,max_bin=128),
]
baseline_xgb=dict(name='baseline_depth6',n_estimators=int(CFG.get('xgb_n_estimators',500)),max_depth=int(CFG.get('xgb_max_depth',6)),learning_rate=0.05,min_child_weight=2,gamma=0.0,subsample=0.90,colsample_bytree=0.90,reg_alpha=0.0,reg_lambda=2.0,max_bin=int(CFG.get('xgb_max_bin',128)))
family_params=dict(name='family',n_estimators=450,max_depth=5,learning_rate=0.05,min_child_weight=2,gamma=0.05,subsample=0.90,colsample_bytree=0.90,reg_alpha=0.02,reg_lambda=2.0,max_bin=128)

# Selection lock: once written, no hyperparameter/weight selection is repeated.
if SELECTION_LOCK.exists():
    lock=json.loads(SELECTION_LOCK.read_text(encoding='utf-8'))
    best_params=lock['enhanced_xgboost_params']
    weights=tuple(lock['ensemble_weights'])
    print('Using EXISTING frozen validation-selection lock.')
else:
    print('\nValidation-only selection phase (TEST IS NOT TOUCHED)')
    validation_rows=[]

    # Fixed baseline validation evidence.
    t=time.perf_counter(); rf_val=fit_rf(Xtr,ytr,int(CFG['seed'])+1); rf_prob=rf_val.predict_proba(Xv)
    validation_rows.append({'model':'random_forest_baseline',**metrics(yv,rf_prob),'train_seconds':time.perf_counter()-t})
    del rf_val,rf_prob; gc.collect()

    t=time.perf_counter(); bx=make_xgb(baseline_xgb,len(classes),int(CFG['seed'])+2)
    bx.fit(Xtr,ytr,sample_weight=compute_sample_weight('balanced',ytr).astype(np.float32),verbose=False)
    bprob=bx.predict_proba(Xv)
    validation_rows.append({'model':'xgboost_baseline',**metrics(yv,bprob),'train_seconds':time.perf_counter()-t})
    del bx,bprob; gc.collect()

    best=None
    for pars in xgb_candidates:
        model=make_xgb(pars,len(classes),int(CFG['seed'])+10)
        t=time.perf_counter(); model.fit(Xtr,ytr,sample_weight=compute_sample_weight('balanced',ytr).astype(np.float32),verbose=False)
        prob=model.predict_proba(Xv); row={'model':'enhanced_xgb::'+pars['name'],**metrics(yv,prob),'train_seconds':time.perf_counter()-t}
        validation_rows.append(row)
        print(f"  {pars['name']}: validation macro-F1={row['macro_f1']:.4f}")
        if best is None or row['macro_f1']>best[0]: best=(row['macro_f1'],pars.copy())
        del model,prob; gc.collect()
    best_params=best[1]

    # Validation-only ensemble weight selection: all component models fit TRAIN only.
    flat=make_xgb(best_params,len(classes),int(CFG['seed'])+20)
    flat.fit(Xtr,ytr,sample_weight=compute_sample_weight('balanced',ytr).astype(np.float32),verbose=False)
    pflat=flat.predict_proba(Xv)
    extra=fit_extra(Xtr,ytr,int(CFG['seed'])+21,trees=450); pextra=extra.predict_proba(Xv)

    fam_y=np.array([family_of_code(c) for c in ytr_orig],dtype=int)
    fam=make_xgb(family_params,3,int(CFG['seed'])+22)
    fam.fit(Xtr,fam_y,sample_weight=compute_sample_weight('balanced',fam_y).astype(np.float32),verbose=False)
    proc=fit_local_xgb(Xtr,ytr_orig,PROCESS_CODES,family_params,int(CFG['seed'])+23)
    sens=fit_local_xgb(Xtr,ytr_orig,SENSOR_CODES,family_params,int(CFG['seed'])+24)
    phier=compose_hierarchical(fam,proc,sens,Xv,classes)

    # Report individual enhanced validation metrics too.
    validation_rows.append({'model':'extra_trees',**metrics(yv,pextra)})
    validation_rows.append({'model':'hierarchical_xgboost',**metrics(yv,phier)})

    weight_rows=[]; bestw=None
    for w in candidate_weights():
        p=(w[0]*pflat+w[1]*pextra+w[2]*phier)/sum(w)
        m=metrics(yv,p)
        row={'flat_xgb_weight':w[0],'extra_trees_weight':w[1],'hierarchical_weight':w[2],**m}
        weight_rows.append(row)
        # Validation macro-F1 primary; ECE secondary tie breaker.
        key=(m['macro_f1'],-m['ece_15bin'])
        if bestw is None or key>bestw[0]: bestw=(key,w)
    weights=tuple(int(x) for x in bestw[1])
    pd.DataFrame(weight_rows).to_csv(REPORT_DIR/'ensemble_weight_search_validation.csv',index=False)
    pd.DataFrame(validation_rows).to_csv(REPORT_DIR/'supervised_validation_model_comparison.csv',index=False)

    lock={
        'protocol':'Locked run-level split; model/hyperparameter and ensemble-weight selection uses TRAIN+VALIDATION information only; TEST untouched until this file is written.',
        'final_fault_codes':classes.tolist(),
        'process_codes':PROCESS_CODES.tolist(),
        'sensor_codes':SENSOR_CODES.tolist(),
        'feature_count':len(features),
        'enhanced_xgboost_params':best_params,
        'ensemble_weights':list(weights),
        'primary_selection_metric':'validation macro-F1; ECE used only as tie breaker for ensemble weights',
        'baseline_xgboost_params':baseline_xgb,
        'family_params':family_params,
    }
    SELECTION_LOCK.write_text(json.dumps(lock,indent=2),encoding='utf-8')
    print('Wrote frozen selection lock BEFORE test scoring:',SELECTION_LOCK)
    del flat,extra,fam,proc,sens,pflat,pextra,phier; gc.collect()

print('Selected enhanced XGBoost:',best_params['name'])
print('Selected ensemble weights [flat, extra, hierarchical]:',weights)

# Final refit on TRAIN+VALIDATION after choices are frozen.
trainval=S.index[S.partition.isin(['train','validation'])]
Xtv=S.loc[trainval,features]
yt_v=S.loc[trainval,'encoded_label'].to_numpy(int)
yt_v_orig=S.loc[trainval,'class_label'].to_numpy(int)
swtv=compute_sample_weight('balanced',yt_v).astype(np.float32)

print('\nFinal refit on TRAIN+VALIDATION...')
training_times={}
t=time.perf_counter(); rf=fit_rf(Xtv,yt_v,int(CFG['seed'])+101); training_times['random_forest']=time.perf_counter()-t
t=time.perf_counter(); xgb=make_xgb(baseline_xgb,len(classes),int(CFG['seed'])+102); xgb.fit(Xtv,yt_v,sample_weight=swtv,verbose=False); training_times['xgboost']=time.perf_counter()-t
t=time.perf_counter(); enhanced=make_xgb(best_params,len(classes),int(CFG['seed'])+103); enhanced.fit(Xtv,yt_v,sample_weight=swtv,verbose=False); training_times['enhanced_xgboost']=time.perf_counter()-t
t=time.perf_counter(); extra=fit_extra(Xtv,yt_v,int(CFG['seed'])+104,trees=500); training_times['extra_trees']=time.perf_counter()-t

fam_y=np.array([family_of_code(c) for c in yt_v_orig],dtype=int)
t=time.perf_counter(); fam=make_xgb(family_params,3,int(CFG['seed'])+105); fam.fit(Xtv,fam_y,sample_weight=compute_sample_weight('balanced',fam_y).astype(np.float32),verbose=False)
proc=fit_local_xgb(Xtv,yt_v_orig,PROCESS_CODES,family_params,int(CFG['seed'])+106)
sens=fit_local_xgb(Xtv,yt_v_orig,SENSOR_CODES,family_params,int(CFG['seed'])+107)
training_times['hierarchical_xgboost']=time.perf_counter()-t

# Save artifacts before test report generation; no test-dependent changes follow.
base_meta={'features':features,'original_classes':classes,'final_fault_codes':classes.tolist(),'dataset_version':'FinalScientific_v4.6.3_Scientific1900','split':'locked_70_15_15_per_class'}
joblib.dump({**base_meta,'model':rf},MODEL_DIR/'random_forest.joblib',compress=3)
joblib.dump({**base_meta,'model':xgb},MODEL_DIR/'xgboost.joblib',compress=3)
joblib.dump({**base_meta,'model':enhanced,'best_params':best_params},MODEL_DIR/'enhanced_xgboost.joblib',compress=3)
joblib.dump({**base_meta,'model':extra},MODEL_DIR/'extra_trees.joblib',compress=3)
hier_pkg={**base_meta,'family_model':fam,'actuator_model':proc,'sensor_model':sens,'actuator_codes':PROCESS_CODES.tolist(),'sensor_codes':SENSOR_CODES.tolist()}
joblib.dump(hier_pkg,MODEL_DIR/'hierarchical_xgboost.joblib',compress=3)
joblib.dump({**hier_pkg,'flat_xgb':enhanced,'extra_trees':extra,'weights':weights},MODEL_DIR/'q1_probability_ensemble.joblib',compress=3)

print('\nLOCKED TEST evaluation — no model/weight selection occurs below this line.')
probabilities={}
for name,model in [('random_forest',rf),('xgboost',xgb),('enhanced_xgboost',enhanced),('extra_trees',extra)]:
    t=time.perf_counter(); p=model.predict_proba(Xt); infer=(time.perf_counter()-t)/max(1,len(Xt))*1000
    probabilities[name]=p
    print(f'  {name}: {infer:.4f} ms/window')
ph=compose_hierarchical(fam,proc,sens,Xt,classes); probabilities['hierarchical_xgboost']=ph
pe=(weights[0]*probabilities['enhanced_xgboost']+weights[1]*probabilities['extra_trees']+weights[2]*ph)/sum(weights)
probabilities['probability_ensemble']=pe

rows=[]
for name,p in probabilities.items():
    infer_meta={'model':name,'training_seconds':training_times.get(name,np.nan)}
    rows.append(save_eval(name,yt,p,classes,infer_meta))
comparison=pd.DataFrame(rows).sort_values('macro_f1',ascending=False)
comparison.to_csv(REPORT_DIR/'final19_locked_test_model_comparison.csv',index=False)

pred_table=S.loc[idx['test'],['run_id','scenario','time_start','time_end','class_label','run_target_label','fault_window_fraction']].copy()
pred_table.rename(columns={'class_label':'true_label'},inplace=True)
for name,p in probabilities.items():
    pred_table[f'{name}_predicted_label']=classes[p.argmax(axis=1)]
    pred_table[f'{name}_confidence']=p.max(axis=1)
pred_table.to_csv(REPORT_DIR/'final19_locked_test_predictions.csv',index=False)
np.savez_compressed(REPORT_DIR/'final19_locked_test_probabilities.npz',
    original_classes=classes,y_test_encoded=yt,y_test_original=classes[yt],
    test_window_index=idx['test'].to_numpy(int),**{k:v.astype(np.float32) for k,v in probabilities.items()})

metadata={
    'selection_lock':str(SELECTION_LOCK),
    'locked_test_rows':int(len(Xt)),
    'train_rows':int(len(Xtr)),
    'validation_rows':int(len(Xv)),
    'trainval_rows_final_fit':int(len(Xtv)),
    'features':len(features),
    'classes':classes.tolist(),
    'ensemble_weights':list(weights),
    'best_enhanced_xgboost_params':best_params,
    'training_seconds':training_times,
}
(REPORT_DIR/'final19_supervised_training_metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
TEST_SENTINEL.write_text('Locked Scientific1900 test scored only after validation selection lock was written.\n',encoding='utf-8')

print('\nFINAL19 locked-test model comparison')
print(comparison.to_string(index=False))
print('\n*** FINAL19 SUPERVISED TRAINING + LOCKED TEST COMPLETE ***')
print('Models:',MODEL_DIR)
print('Reports:',REPORT_DIR)
