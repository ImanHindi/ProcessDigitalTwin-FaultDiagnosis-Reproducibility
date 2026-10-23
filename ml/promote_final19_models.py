from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

from features import ROOT
from final19_common import MODEL_DIR, REPORT_DIR

p=argparse.ArgumentParser()
p.add_argument('--yes',action='store_true',help='Required safety acknowledgement to promote staged Final19 artifacts.')
a=p.parse_args()

ready=REPORT_DIR/'FINAL19_ARTIFACTS_VALIDATED_READY_FOR_PROMOTION.txt'
if not ready.exists():
    raise SystemExit('Artifact-validation marker is missing. Run ml/validate_final19_artifacts.py first.')
if not a.yes:
    raise SystemExit('Promotion changes the served model files. Re-run with --yes after reviewing final19 reports.')

served=ROOT/'ml'/'models'; served.mkdir(parents=True,exist_ok=True)
stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
backup=served/f'archive_pre_final19_{stamp}'; backup.mkdir(parents=True,exist_ok=False)

promote_names=[
    'random_forest.joblib','xgboost.joblib','enhanced_xgboost.joblib','extra_trees.joblib',
    'hierarchical_xgboost.joblib','q1_probability_ensemble.joblib','lstm.pt',
    'isolation_forest.joblib','mode_conditioned_isolation_forest.joblib',
    'anomaly_dae.pt','anomaly_vae.pt','anomaly_cvae.pt','anomaly_lstm_ae.pt',
    'best_deep_anomaly_detector.pt',
]

manifest=[]
for name in promote_names:
    src=MODEL_DIR/name
    dst=served/name
    if dst.exists():
        shutil.copy2(dst,backup/name)
    if src.exists():
        shutil.copy2(src,dst)
        manifest.append({'artifact':name,'status':'promoted'})
    else:
        # best_deep can legitimately be absent when an IF baseline is validation-selected.
        # Remove a stale previously-served deep candidate after it has been archived.
        if name == 'best_deep_anomaly_detector.pt' and dst.exists():
            dst.unlink()
            manifest.append({'artifact':name,'status':'stale_served_artifact_removed'})
        else:
            manifest.append({'artifact':name,'status':'not_present_in_staging'})

(served/'FINAL19_MODELS_PROMOTED.txt').write_text(
    f'FinalScientific v4.6.3 Scientific1900 Final19 artifacts promoted at {stamp}.\n'
    f'Previous served artifacts archived in: {backup}\n',encoding='utf-8')
(backup/'promotion_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print('*** FINAL19 MODELS PROMOTED ***')
print('Backup:',backup)
print('Served:',served)
for row in manifest:
    print(' ',row['artifact'],row['status'])
