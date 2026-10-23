from __future__ import annotations

from pathlib import Path
import json
import os
import joblib
import numpy as np
import pandas as pd

from features import ROOT, CFG, load_runs

FINAL_CODES = np.array([0,1,2,3,4,5,6,7,8,9,10,11,12,101,102,103,104,105,106], dtype=int)
PROCESS_CODES = np.arange(1, 13, dtype=int)
SENSOR_CODES = np.arange(101, 107, dtype=int)

DATA_DIR = ROOT / 'ml' / 'data' / 'final_scientific_v4_6_3' / 'scientific1900'
SPLIT_FILE = DATA_DIR / 'scientific1900_LOCKED_run_split.csv'
READY_FILE = DATA_DIR / 'SCIENTIFIC1900_VALIDATED_READY_FOR_MODELING.txt'
SPLIT_LOCK_FILE = DATA_DIR / 'LOCKED_SPLIT_CREATED_DO_NOT_CHANGE.txt'

MODEL_DIR = ROOT / 'ml' / 'models' / 'final19'
REPORT_DIR = ROOT / 'ml' / 'reports' / 'final19'
CACHE_DIR = ROOT / 'ml' / 'cache'
MODEL_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

CACHE_FILE = CACHE_DIR / 'window_features_w60_s60_v463_1900.joblib'
CACHE_META = CACHE_DIR / 'window_features_w60_s60_v463_1900.json'
NORMALIZED_SPLIT = REPORT_DIR / 'run_split.csv'


def feature_columns(frame: pd.DataFrame) -> list[str]:
    cols = [c for c in frame.columns if '__' in c]
    if len(cols) != 170:
        raise RuntimeError(f'Expected exactly 170 engineered features; found {len(cols)}.')
    return cols


def load_locked_split() -> pd.DataFrame:
    for p, label in [
        (READY_FILE, 'Scientific1900 QA marker'),
        (SPLIT_FILE, 'locked run-level split'),
        (SPLIT_LOCK_FILE, 'split lock marker'),
    ]:
        if not p.exists():
            raise SystemExit(f'{label} is missing: {p}')

    s = pd.read_csv(SPLIT_FILE)
    required = {'run_id','fault_code','split'}
    missing = required - set(s.columns)
    if missing:
        raise SystemExit(f'Locked split is missing columns: {sorted(missing)}')

    s = s.copy()
    s['run_id'] = s['run_id'].astype(str)
    s['fault_code'] = pd.to_numeric(s['fault_code'], errors='raise').astype(int)
    s['partition'] = s['split'].astype(str).str.strip().str.lower().replace({'val':'validation'})

    if len(s) != 1900 or s['run_id'].nunique() != 1900:
        raise SystemExit(f'Locked split must contain exactly 1900 unique runs; got rows={len(s)}, unique={s.run_id.nunique()}.')

    if set(s['fault_code'].unique()) != set(FINAL_CODES.tolist()):
        raise SystemExit(f'Locked split class codes differ from final 19-class taxonomy: {sorted(s.fault_code.unique())}')

    expected_global = {'train':1330, 'validation':285, 'test':285}
    actual = s['partition'].value_counts().to_dict()
    if actual != expected_global:
        raise SystemExit(f'Locked split counts changed. Expected {expected_global}, got {actual}.')

    counts = s.groupby(['fault_code','partition']).size().unstack(fill_value=0)
    for code in FINAL_CODES:
        row = counts.loc[int(code)]
        if int(row.get('train',0)) != 70 or int(row.get('validation',0)) != 15 or int(row.get('test',0)) != 15:
            raise SystemExit(f'Class {code} is not exactly 70/15/15: {row.to_dict()}')

    s[['run_id','fault_code','partition']].to_csv(NORMALIZED_SPLIT, index=False)
    return s


def run_files() -> list[Path]:
    files = sorted(DATA_DIR.glob('v463_sci1900_fc*_rep*.csv'))
    if len(files) != 1900:
        raise SystemExit(f'Expected 1900 Scientific1900 run CSVs in {DATA_DIR}; found {len(files)}.')
    return files


def source_signature(files: list[Path]) -> dict:
    import hashlib
    return {
        'dataset_version': CFG.get('dataset_version'),
        'n_files': len(files),
        'total_bytes': int(sum(p.stat().st_size for p in files)),
        'latest_mtime_ns': int(max(p.stat().st_mtime_ns for p in files)),
        'window_seconds': int(CFG['window_seconds']),
        'window_step_seconds': int(CFG['window_step_seconds']),
        'signals': list(CFG['signals']),
        'feature_count': 170,
        'label_protocol': 'Final19 causal active-window-only; normal dedicated runs only',
        'split_file_sha256': hashlib.sha256(SPLIT_FILE.read_bytes()).hexdigest(),
    }


def build_or_load_feature_cache(rebuild: bool=False) -> pd.DataFrame:
    split = load_locked_split()
    files = run_files()
    sig = source_signature(files)

    data = None
    if not rebuild and CACHE_FILE.exists() and CACHE_META.exists():
        try:
            if json.loads(CACHE_META.read_text(encoding='utf-8')) == sig:
                print(f'Loading locked Scientific1900 feature cache: {CACHE_FILE}')
                data = joblib.load(CACHE_FILE)
        except Exception:
            data = None

    if data is None:
        print('Building 60-s non-overlapping feature cache from 1900 Scientific1900 runs...')
        data = load_runs([DATA_DIR], size=int(CFG['window_seconds']), step=int(CFG['window_step_seconds']))
        tmp = CACHE_FILE.with_suffix('.tmp.joblib')
        joblib.dump(data, tmp, compress=0)
        os.replace(tmp, CACHE_FILE)
        CACHE_META.write_text(json.dumps(sig, indent=2), encoding='utf-8')
        print(f'Saved feature cache: {CACHE_FILE}')

    fcols = feature_columns(data)
    data[fcols] = data[fcols].astype(np.float32)

    partition_map = dict(zip(split['run_id'], split['partition']))
    data = data.copy()
    data['partition'] = data['run_id'].astype(str).map(partition_map)
    if data['partition'].isna().any():
        bad = data.loc[data['partition'].isna(), 'run_id'].astype(str).unique()[:10]
        raise RuntimeError(f'Feature rows exist for runs absent from the locked split: {bad.tolist()}')

    if data['run_id'].nunique() != 1900:
        raise RuntimeError(f'Feature cache contains {data.run_id.nunique()} runs, expected 1900.')

    crossing = data.groupby('run_id')['partition'].nunique()
    if (crossing != 1).any():
        raise RuntimeError('At least one run crosses locked partitions.')

    observed_codes = set(pd.to_numeric(data['run_target_label'], errors='raise').astype(int).unique())
    if observed_codes != set(FINAL_CODES.tolist()):
        raise RuntimeError(f'Feature cache class set is incorrect: {sorted(observed_codes)}')

    return data


def supervised_frame(data: pd.DataFrame) -> tuple[pd.DataFrame, list[str], np.ndarray, dict[int,int]]:
    frame = data[(data['supervised_usable'] == 1) & data['partition'].isin(['train','validation','test'])].copy()
    fcols = feature_columns(frame)
    frame[fcols] = frame[fcols].astype(np.float32)
    classes = np.array(sorted(frame['class_label'].astype(int).unique()), dtype=int)
    if not np.array_equal(classes, FINAL_CODES):
        raise RuntimeError(f'Supervised class set is not the final 19 codes: {classes.tolist()}')
    code_to_encoded = {int(code): i for i, code in enumerate(classes)}
    frame['encoded_label'] = frame['class_label'].astype(int).map(code_to_encoded).astype(int)
    return frame, fcols, classes, code_to_encoded


def manifest_summary(data: pd.DataFrame) -> pd.DataFrame:
    return (
        data.groupby(['partition','run_target_label'])['run_id']
        .nunique().rename('runs').reset_index()
        .sort_values(['partition','run_target_label'])
    )
