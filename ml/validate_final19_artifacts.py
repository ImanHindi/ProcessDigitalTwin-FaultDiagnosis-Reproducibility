from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np

from final19_common import (
    FINAL_CODES, PROCESS_CODES, SENSOR_CODES,
    MODEL_DIR, REPORT_DIR, feature_columns, build_or_load_feature_cache,
)

REQUIRED_SUPERVISED = [
    'random_forest.joblib',
    'xgboost.joblib',
    'enhanced_xgboost.joblib',
    'extra_trees.joblib',
    'hierarchical_xgboost.joblib',
    'q1_probability_ensemble.joblib',
]
REQUIRED_ANOMALY = [
    'isolation_forest.joblib',
    'mode_conditioned_isolation_forest.joblib',
]

marker = REPORT_DIR / 'FINAL19_ARTIFACTS_VALIDATED_READY_FOR_PROMOTION.txt'
if marker.exists():
    marker.unlink()

rows = []
def check(name: str, ok: bool, detail: str=''):
    rows.append({'check':name,'pass':bool(ok),'detail':detail})
    print(f'{name:<48} {"PASS" if ok else "FAIL"}  {detail}')

print('='*76)
print('FINAL19 ARTIFACT VALIDATION')
print('='*76)

# Source/feature contract.
try:
    data = build_or_load_feature_cache(rebuild=False)
    fcols = feature_columns(data)
    check('Feature cache has 1900 runs', data.run_id.nunique()==1900, str(data.run_id.nunique()))
    check('Feature contract has 170 features', len(fcols)==170, str(len(fcols)))
except Exception as exc:
    data = None; fcols=[]
    check('Feature cache / contract', False, repr(exc))

for filename in REQUIRED_SUPERVISED + REQUIRED_ANOMALY:
    check(f'Model exists: {filename}', (MODEL_DIR/filename).exists(), str(MODEL_DIR/filename))

# Supervised artifact internals.
for filename in REQUIRED_SUPERVISED[:4]:
    path=MODEL_DIR/filename
    if not path.exists():
        continue
    try:
        p=joblib.load(path)
        classes=np.asarray(p.get('original_classes',[]),dtype=int)
        features=list(p.get('features',[]))
        check(f'{filename}: exact 19 classes', np.array_equal(classes,FINAL_CODES), classes.tolist().__str__())
        check(f'{filename}: 170 features', len(features)==170, str(len(features)))
    except Exception as exc:
        check(f'{filename}: readable', False, repr(exc))

for filename in ['hierarchical_xgboost.joblib','q1_probability_ensemble.joblib']:
    path=MODEL_DIR/filename
    if not path.exists():
        continue
    try:
        p=joblib.load(path)
        classes=np.asarray(p.get('original_classes',[]),dtype=int)
        act=np.asarray(p.get('actuator_codes',[]),dtype=int)
        sen=np.asarray(p.get('sensor_codes',[]),dtype=int)
        check(f'{filename}: exact 19 classes', np.array_equal(classes,FINAL_CODES), classes.tolist().__str__())
        check(f'{filename}: process codes 1..12', np.array_equal(act,PROCESS_CODES), act.tolist().__str__())
        check(f'{filename}: sensor codes 101..106', np.array_equal(sen,SENSOR_CODES), sen.tolist().__str__())
        check(f'{filename}: 170 features', len(p.get('features',[]))==170, str(len(p.get('features',[]))))
        if filename.startswith('q1_'):
            w=tuple(float(x) for x in p.get('weights',()))
            check('Ensemble has three positive weights', len(w)==3 and all(x>0 for x in w), str(w))
    except Exception as exc:
        check(f'{filename}: readable', False, repr(exc))

# Protocol/report locks.
selection_lock=REPORT_DIR/'supervised_selection_lock.json'
test_marker=REPORT_DIR/'FINAL19_SUPERVISED_LOCKED_TEST_COMPLETE.txt'
check('Supervised validation-selection lock exists',selection_lock.exists(),str(selection_lock))
check('Locked supervised test completion marker',test_marker.exists(),str(test_marker))
check('Final supervised comparison exists',(REPORT_DIR/'final19_locked_test_model_comparison.csv').exists(),'')

# LSTM is required for the final comparison package requested by the project.
lstm_path=MODEL_DIR/'lstm.pt'
check('Final19 LSTM artifact exists',lstm_path.exists(),str(lstm_path))
check('LSTM locked-test marker exists',(REPORT_DIR/'FINAL19_LSTM_LOCKED_TEST_COMPLETE.txt').exists(),'')

# Deep anomaly benchmark may select an IF baseline rather than a deep network.
sel=REPORT_DIR/'anomaly_model_selection.json'
check('Anomaly model selection report exists',sel.exists(),str(sel))
if sel.exists():
    try:
        info=json.loads(sel.read_text(encoding='utf-8'))
        selected=str(info.get('selected_model',''))
        deep=bool(info.get('selected_is_deep_model',selected in {'dae','vae','cvae','lstm_ae'}))
        check('Anomaly selected model recorded',bool(selected),selected)
        for name in ['dae','vae','cvae','lstm_ae']:
            check(f'Deep anomaly artifact exists: {name}',(MODEL_DIR/f'anomaly_{name}.pt').exists(),'')
        if deep:
            check('Selected deep deployment artifact exists',(MODEL_DIR/'best_deep_anomaly_detector.pt').exists(),selected)
    except Exception as exc:
        check('Anomaly selection report readable',False,repr(exc))

# Advanced validation reports are required before promotion to serving.
for name in [
    'final19_advanced_probability_metrics.csv',
    'final19_per_class_metrics.csv',
    'final19_fault_detection_delay_by_run.csv',
    'final19_advanced_validation_summary.json',
]:
    check(f'Advanced report exists: {name}',(REPORT_DIR/name).exists(),'')

all_pass=all(r['pass'] for r in rows)
import pandas as pd
pd.DataFrame(rows).to_csv(REPORT_DIR/'final19_artifact_validation.csv',index=False)

print('\n'+'='*76)
if all_pass:
    marker.write_text(
        'Final19 Scientific1900 artifacts passed structural and protocol validation.\n'
        'Promotion to ml/models is permitted.\n',encoding='utf-8')
    print('*** FINAL19 ARTIFACT VALIDATION PASSED — READY FOR PROMOTION ***')
else:
    print('*** FINAL19 ARTIFACT VALIDATION FAILED — DO NOT PROMOTE ***')
    raise SystemExit(2)
print('='*76)
