from __future__ import annotations
from pathlib import Path
import joblib,numpy as np,pandas as pd
from features import ROOT
from final19_common import DATA_DIR,SPLIT_FILE,FINAL_CODES
from predict import predict_csv
ens=ROOT/'ml'/'models'/'q1_probability_ensemble.joblib'
if not ens.exists():raise SystemExit('Promoted ensemble not found. Run promote_final19_models.py --yes first.')
p=joblib.load(ens);classes=np.asarray(p['original_classes'],int)
if not np.array_equal(classes,FINAL_CODES):raise SystemExit(f'Served ensemble classes wrong: {classes.tolist()}')
s=pd.read_csv(SPLIT_FILE);test=s[s['split'].astype(str).str.lower()=='test'];rid=str(test.iloc[0].run_id);files=list(DATA_DIR.glob(f'{rid}.csv'))
if not files:raise SystemExit(f'Could not find CSV for locked-test run {rid}')
out=predict_csv(files[0]);
if out.empty:raise SystemExit('predict_csv returned no windows.')
print(out[['run_id','time_start','time_end','primary_fault_code','primary_confidence','primary_model']].head(10).to_string(index=False))
print('Unique served primary codes:',sorted(out.primary_fault_code.astype(int).unique().tolist()))
print('*** FINAL19 SERVING SMOKE TEST PASSED ***')
