from __future__ import annotations

import platform
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import sklearn
import joblib
import xgboost
try:
    import torch
except Exception:
    torch = None

from features import ROOT, CFG
from final19_common import (
    DATA_DIR, SPLIT_FILE, READY_FILE, SPLIT_LOCK_FILE,
    FINAL_CODES, load_locked_split, run_files,
)

print('='*68)
print('FINAL19 / SCIENTIFIC1900 TRAINING READINESS')
print('='*68)

checks=[]
def check(name, ok, detail=''):
    checks.append(bool(ok))
    print(f'{name:<42} {"PASS" if ok else "FAIL"}  {detail}')

check('Python >= 3.11', sys.version_info >= (3,11), platform.python_version())
check('Scientific1900 QA marker', READY_FILE.exists(), str(READY_FILE))
check('Locked split file', SPLIT_FILE.exists(), str(SPLIT_FILE))
check('Locked split marker', SPLIT_LOCK_FILE.exists(), str(SPLIT_LOCK_FILE))

try:
    split=load_locked_split()
    check('1900 unique locked runs', len(split)==1900 and split.run_id.nunique()==1900,
          f'{len(split)} rows / {split.run_id.nunique()} unique')
    check('Global split = 1330/285/285',
          split.partition.value_counts().to_dict()=={'train':1330,'validation':285,'test':285},
          str(split.partition.value_counts().to_dict()))
    per=split.groupby(['fault_code','partition']).size().unstack(fill_value=0)
    exact=all(int(per.loc[c,'train'])==70 and int(per.loc[c,'validation'])==15 and int(per.loc[c,'test'])==15 for c in FINAL_CODES)
    check('Each class exactly 70/15/15', exact, '19 classes')
except Exception as exc:
    check('Locked split integrity', False, repr(exc))
    split=None

try:
    files=run_files()
    check('Scientific1900 run CSV count', len(files)==1900, str(len(files)))
    sample=pd.read_csv(files[0], nrows=5)
    needed={
        'time','run_id','target','run_target_label','fault_active','process_mode',
        'temperature_measured_K','level_measured_m','gauge_pressure_measured_Pa',
        'production_mass_flow_measured_kg_s','agitator_speed_measured_rpm',
        'cmd_agitator_rpm','effective_heat_flow_W','prod_inlet_actual_pct',
        'tank_inlet_actual_pct','discharge_actual_pct','cip_inlet_actual_pct','cip_return_actual_pct'
    }
    check('Scientific1900 schema sample', needed.issubset(sample.columns),
          f'{len(sample.columns)} columns')
except Exception as exc:
    check('Scientific1900 source files', False, repr(exc))

check('Feature contract = 17 signals', len(CFG.get('signals',[]))==17, str(len(CFG.get('signals',[]))))
check('Window/step = 60/60 s', int(CFG.get('window_seconds',0))==60 and int(CFG.get('window_step_seconds',0))==60,
      f"{CFG.get('window_seconds')}/{CFG.get('window_step_seconds')}")
check('Final taxonomy = 19 classes', CFG.get('final_fault_codes')==FINAL_CODES.tolist(), str(CFG.get('final_fault_codes')))

print('\nEnvironment versions')
print('  numpy       ', np.__version__)
print('  pandas      ', pd.__version__)
print('  scikit-learn', sklearn.__version__)
print('  xgboost     ', xgboost.__version__)
print('  joblib      ', joblib.__version__)
print('  torch       ', getattr(torch,'__version__','not installed'))

# Reproducibility warning, not a hard failure: train and serve in the same environment.
if sklearn.__version__ != '1.6.1':
    print('\nNOTE: project target was scikit-learn 1.6.1. Retraining can still proceed,')
    print('but serve these newly trained artifacts in the SAME environment/version.')
if xgboost.__version__ != '3.2.0':
    print('NOTE: project target was xgboost 3.2.0. Keep train/serve versions aligned.')

print('\n'+'='*68)
if all(checks):
    print('*** FINAL19 TRAINING READINESS PASSED ***')
    print('Next: python ml/build_final19_feature_cache.py')
else:
    print('*** FINAL19 TRAINING READINESS FAILED ***')
    raise SystemExit(2)
print('='*68)
