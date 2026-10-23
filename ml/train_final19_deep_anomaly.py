from __future__ import annotations

import argparse
import gc
import json
import math
import os
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from features import ROOT, CFG
from final19_common import MODEL_DIR, REPORT_DIR, CACHE_FILE, NORMALIZED_SPLIT, build_or_load_feature_cache, feature_columns
from anomaly_models import (
    build_model,
    preprocess_array,
    score_sequence_model,
    score_window_model,
)

def find_feature_cache():
    build_or_load_feature_cache(rebuild=False)
    return CACHE_FILE


def fit_preprocessor(X):
    X = np.asarray(X, dtype=np.float32)
    with np.errstate(all='ignore'):
        medians = np.nanmedian(X, axis=0)
    medians = np.where(np.isfinite(medians), medians, 0.0).astype(np.float32)
    Xi = np.where(np.isfinite(X), X, medians)
    means = Xi.mean(axis=0, dtype=np.float64).astype(np.float32)
    scales = Xi.std(axis=0, dtype=np.float64).astype(np.float32)
    scales = np.where(np.isfinite(scales) & (scales > 1e-6), scales, 1.0).astype(np.float32)
    return medians, means, scales


def modes_from_frame(frame):
    col = 'process_mode__last'
    if col in frame.columns:
        values = pd.to_numeric(frame[col], errors='coerce').round().fillna(0).astype(int)
    else:
        values = pd.Series(np.zeros(len(frame), dtype=int), index=frame.index)
    return np.clip(values.to_numpy(dtype=np.int64), 0, 6)


def binary_metrics(y, score, threshold):
    y = np.asarray(y, dtype=int)
    score = np.asarray(score, dtype=float)
    pred = (score >= float(threshold)).astype(int)
    result = {
        'accuracy': float(accuracy_score(y, pred)),
        'balanced_accuracy': float(balanced_accuracy_score(y, pred)),
        'macro_f1': float(f1_score(y, pred, average='macro', zero_division=0)),
        'fault_precision': float(precision_score(y, pred, zero_division=0)),
        'fault_recall': float(recall_score(y, pred, zero_division=0)),
        'threshold': float(threshold),
        'n': int(len(y)),
        'fault_fraction': float(y.mean()) if len(y) else 0.0,
    }
    if len(np.unique(y)) == 2:
        result['roc_auc'] = float(roc_auc_score(y, score))
        result['average_precision'] = float(average_precision_score(y, score))
    else:
        result['roc_auc'] = None
        result['average_precision'] = None
    return result


def specificity(y, pred):
    y = np.asarray(y, dtype=int)
    pred = np.asarray(pred, dtype=int)
    normal = y == 0
    return float((pred[normal] == 0).mean()) if normal.any() else np.nan


def build_sequences(frame, Xp, seq_len, partitions=None, healthy_only=False):
    seqs, endpoints, labels, run_ids, times = [], [], [], [], []
    # frame index and Xp are positional-aligned.
    position = {idx: pos for pos, idx in enumerate(frame.index)}
    for run_id, part in frame.groupby('run_id', sort=False):
        part = part.sort_values('time_start')
        if partitions is not None and str(part['partition'].iloc[0]) not in partitions:
            continue
        if healthy_only and int(part['run_target_label'].iloc[0]) != 0:
            continue
        idx = part.index.to_numpy()
        if len(idx) < seq_len:
            continue
        pos = np.array([position[i] for i in idx], dtype=int)
        for end_local in range(seq_len - 1, len(idx)):
            start_local = end_local - seq_len + 1
            seqs.append(Xp[pos[start_local:end_local + 1]])
            endpoint_idx = idx[end_local]
            endpoints.append(endpoint_idx)
            labels.append(int(frame.loc[endpoint_idx, 'anomaly_label']))
            run_ids.append(str(run_id))
            times.append(float(frame.loc[endpoint_idx, 'time_end']))
    if seqs:
        seqs = np.stack(seqs).astype(np.float32, copy=False)
    else:
        seqs = np.empty((0, seq_len, Xp.shape[1]), dtype=np.float32)
    return seqs, np.asarray(endpoints), np.asarray(labels), np.asarray(run_ids), np.asarray(times)


def train_dense_ae(model, X_train, X_val, device, epochs, batch_size, noise_sigma, patience, name):
    train_loader = DataLoader(
        TensorDataset(torch.from_numpy(X_train)),
        batch_size=batch_size,
        shuffle=True,
        num_workers=0,
    )
    val_tensor = torch.from_numpy(X_val)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-5)
    best_loss, best_state, wait = math.inf, None, 0
    history = []
    for epoch in range(1, epochs + 1):
        model.train()
        running, n = 0.0, 0
        for (xb,) in train_loader:
            xb = xb.to(device)
            noisy = xb + noise_sigma * torch.randn_like(xb)
            optimizer.zero_grad(set_to_none=True)
            recon = model(noisy)
            loss = torch.mean((recon - xb) ** 2)
            loss.backward()
            optimizer.step()
            running += float(loss.item()) * len(xb); n += len(xb)
        model.eval()
        with torch.no_grad():
            vals = []
            for start in range(0, len(val_tensor), 2048):
                xb = val_tensor[start:start + 2048].to(device)
                vals.append(torch.mean((model(xb) - xb) ** 2).item())
            val_loss = float(np.mean(vals)) if vals else math.inf
        train_loss = running / max(n, 1)
        history.append({'epoch': epoch, 'train_loss': train_loss, 'val_loss': val_loss})
        print(f'{name} epoch {epoch:02d}: train={train_loss:.6f} val={val_loss:.6f}', flush=True)
        if val_loss < best_loss - 1e-6:
            best_loss = val_loss
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                break
    if best_state is None:
        raise RuntimeError(f'{name} did not produce a valid model state.')
    model.load_state_dict(best_state)
    return pd.DataFrame(history), best_loss


def train_vae(model, X_train, X_val, device, epochs, batch_size, beta, patience, name, train_modes=None, val_modes=None):
    if train_modes is None:
        train_ds = TensorDataset(torch.from_numpy(X_train))
    else:
        train_ds = TensorDataset(torch.from_numpy(X_train), torch.from_numpy(train_modes.astype(np.int64)))
    loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=0)
    optimizer = torch.optim.AdamW(model.parameters(), lr=8e-4, weight_decay=1e-5)
    best_loss, best_state, wait = math.inf, None, 0
    history = []

    def loss_for(xb, mb=None):
        if mb is None:
            recon, mu, logvar = model(xb)
        else:
            recon, mu, logvar = model(xb, mb)
        recon_loss = torch.mean((recon - xb) ** 2)
        kl = -0.5 * torch.mean(1 + logvar - mu.pow(2) - logvar.exp())
        return recon_loss + beta * kl, recon_loss, kl

    for epoch in range(1, epochs + 1):
        model.train(); running = 0.0; n = 0
        for batch in loader:
            xb = batch[0].to(device)
            mb = batch[1].to(device) if len(batch) > 1 else None
            optimizer.zero_grad(set_to_none=True)
            loss, recon_loss, kl = loss_for(xb, mb)
            loss.backward(); optimizer.step()
            running += float(loss.item()) * len(xb); n += len(xb)

        model.eval(); values = []
        with torch.no_grad():
            for start in range(0, len(X_val), 2048):
                xb = torch.from_numpy(X_val[start:start + 2048]).to(device)
                mb = None
                if val_modes is not None:
                    mb = torch.from_numpy(val_modes[start:start + 2048].astype(np.int64)).to(device)
                loss, _, _ = loss_for(xb, mb)
                values.append(float(loss.item()))
        val_loss = float(np.mean(values)) if values else math.inf
        train_loss = running / max(n, 1)
        history.append({'epoch': epoch, 'train_loss': train_loss, 'val_loss': val_loss})
        print(f'{name} epoch {epoch:02d}: train={train_loss:.6f} val={val_loss:.6f}', flush=True)
        if val_loss < best_loss - 1e-6:
            best_loss = val_loss
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                break
    if best_state is None:
        raise RuntimeError(f'{name} did not produce a valid model state.')
    model.load_state_dict(best_state)
    return pd.DataFrame(history), best_loss


def train_lstm_ae(model, seq_train, seq_val, device, epochs, batch_size, patience, name):
    loader = DataLoader(
        TensorDataset(torch.from_numpy(seq_train)),
        batch_size=batch_size,
        shuffle=True,
        num_workers=0,
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=8e-4, weight_decay=1e-5)
    best_loss, best_state, wait = math.inf, None, 0
    history = []
    for epoch in range(1, epochs + 1):
        model.train(); running = 0.0; n = 0
        for (xb,) in loader:
            xb = xb.to(device)
            optimizer.zero_grad(set_to_none=True)
            recon = model(xb)
            loss = torch.mean((recon - xb) ** 2)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
            running += float(loss.item()) * len(xb); n += len(xb)
        model.eval(); vals = []
        with torch.no_grad():
            for start in range(0, len(seq_val), 512):
                xb = torch.from_numpy(seq_val[start:start + 512]).to(device)
                vals.append(float(torch.mean((model(xb) - xb) ** 2).item()))
        val_loss = float(np.mean(vals)) if vals else math.inf
        train_loss = running / max(n, 1)
        history.append({'epoch': epoch, 'train_loss': train_loss, 'val_loss': val_loss})
        print(f'{name} epoch {epoch:02d}: train={train_loss:.6f} val={val_loss:.6f}', flush=True)
        if val_loss < best_loss - 1e-6:
            best_loss = val_loss
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                break
    if best_state is None:
        raise RuntimeError(f'{name} did not produce a valid model state.')
    model.load_state_dict(best_state)
    return pd.DataFrame(history), best_loss


def evaluate_existing_if(frame, feature_names, indices, model_path, mode_conditioned=False):
    if not model_path.exists():
        return None
    package = joblib.load(model_path)
    positions = frame.index.get_indexer(indices)
    subset = frame.loc[indices]
    if mode_conditioned:
        scores = np.full(len(subset), np.nan, dtype=float)
        flags = np.zeros(len(subset), dtype=int)
        modes = pd.to_numeric(subset.get(package.get('mode_feature', 'process_mode__last'), np.nan), errors='coerce').round()
        for mode in pd.Series(modes).dropna().unique():
            mode_int = int(mode)
            info = package['mode_models'].get(mode_int, package['mode_models'].get(str(mode_int)))
            if info is None: continue
            rows = np.flatnonzero(np.asarray(modes == mode))
            X = subset.iloc[rows].reindex(columns=package['features'])
            Z = info['imputer'].transform(X)
            s = -info['model'].score_samples(Z)
            scores[rows] = s
            flags[rows] = (s >= float(info['threshold'])).astype(int)
        valid = np.isfinite(scores)
        return scores, flags, valid
    X = subset.reindex(columns=package['features'])
    Z = package['imputer'].transform(X)
    if 'scaler' in package: Z = package['scaler'].transform(Z)
    scores = -package['model'].score_samples(Z)
    flags = (scores >= float(package['threshold'])).astype(int)
    return scores, flags, np.ones(len(subset), dtype=bool)


def bootstrap_run_ci(pred_frame, model_name, n_boot=1000, seed=42):
    part = pred_frame[['run_id', 'anomaly_label', f'{model_name}_pred']].dropna().copy()
    runs = part['run_id'].astype(str).unique()
    if len(runs) == 0: return None
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n_boot):
        chosen = rng.choice(runs, size=len(runs), replace=True)
        chunks = [part[part['run_id'].astype(str) == str(run)] for run in chosen]
        b = pd.concat(chunks, ignore_index=True)
        y = b['anomaly_label'].astype(int).to_numpy(); p = b[f'{model_name}_pred'].astype(int).to_numpy()
        vals.append([
            balanced_accuracy_score(y, p),
            f1_score(y, p, average='macro', zero_division=0),
            recall_score(y, p, zero_division=0),
        ])
    arr = np.asarray(vals)
    return {
        'model': model_name,
        'balanced_accuracy_mean': float(arr[:, 0].mean()),
        'balanced_accuracy_ci_low': float(np.quantile(arr[:, 0], .025)),
        'balanced_accuracy_ci_high': float(np.quantile(arr[:, 0], .975)),
        'macro_f1_mean': float(arr[:, 1].mean()),
        'macro_f1_ci_low': float(np.quantile(arr[:, 1], .025)),
        'macro_f1_ci_high': float(np.quantile(arr[:, 1], .975)),
        'fault_recall_mean': float(arr[:, 2].mean()),
        'fault_recall_ci_low': float(np.quantile(arr[:, 2], .025)),
        'fault_recall_ci_high': float(np.quantile(arr[:, 2], .975)),
    }


parser = argparse.ArgumentParser()
parser.add_argument('--n-jobs', type=int, default=2)
parser.add_argument('--epochs', type=int, default=60)
parser.add_argument('--patience', type=int, default=9)
parser.add_argument('--batch-size', type=int, default=256)
parser.add_argument('--seq-batch-size', type=int, default=128)
parser.add_argument('--seq-len', type=int, default=6, help='Number of consecutive 60-s feature windows for LSTM encoder-decoder.')
parser.add_argument('--target-fpr', type=float, default=float(CFG.get('isolation_forest_target_fpr', 0.05)))
parser.add_argument('--bootstrap', type=int, default=1000)
args = parser.parse_args()

torch.set_num_threads(max(1, args.n_jobs))
np.random.seed(int(CFG['seed']) + 901)
torch.manual_seed(int(CFG['seed']) + 901)
if torch.cuda.is_available(): torch.cuda.manual_seed_all(int(CFG['seed']) + 901)
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print('Device:', device, flush=True)

cache_path = find_feature_cache()
print('Loading feature cache:', cache_path, flush=True)
frame = joblib.load(cache_path)
split_path = NORMALIZED_SPLIT
if not split_path.exists():
    raise SystemExit(f'Missing normalized locked split: {split_path}. Run build_final19_feature_cache.py first.')
split = pd.read_csv(split_path)
partition_map = dict(zip(split['run_id'].astype(str), split['partition'].astype(str)))
frame['partition'] = frame['run_id'].astype(str).map(partition_map)
frame = frame[frame['partition'].isin(['train', 'validation', 'test'])].copy()
feature_names = [c for c in frame.columns if '__' in c]
if not feature_names: raise SystemExit('No engineered features found.')

healthy_train = frame[(frame['partition'] == 'train') & (frame['run_target_label'] == 0)]
healthy_val = frame[(frame['partition'] == 'validation') & (frame['run_target_label'] == 0)]
val_all = frame[frame['partition'] == 'validation']
test_all = frame[frame['partition'] == 'test']
print(f'Healthy train windows: {len(healthy_train):,}', flush=True)
print(f'Healthy validation windows: {len(healthy_val):,}', flush=True)
print(f'All validation windows: {len(val_all):,}', flush=True)
print(f'All test windows: {len(test_all):,}', flush=True)

medians, means, scales = fit_preprocessor(healthy_train[feature_names].to_numpy(np.float32))
X_all = preprocess_array(frame[feature_names].to_numpy(np.float32), medians, means, scales)
position = {idx: pos for pos, idx in enumerate(frame.index)}

def get_X(indices):
    return X_all[np.array([position[i] for i in indices], dtype=int)]

X_htrain = get_X(healthy_train.index)
X_hval = get_X(healthy_val.index)
modes_htrain = modes_from_frame(healthy_train)
modes_hval = modes_from_frame(healthy_val)

model_specs = {
    'dae': {'input_dim': len(feature_names), 'latent_dim': 24},
    'vae': {'input_dim': len(feature_names), 'latent_dim': 16},
    'cvae': {'input_dim': len(feature_names), 'latent_dim': 16, 'n_modes': 7},
    'lstm_ae': {'input_dim': len(feature_names), 'hidden_dim': 64, 'latent_dim': 32, 'num_layers': 1},
}
artifacts = {}
window_scores = {}
thresholds = {}
training_seconds = {}

# DAE
model = build_model('dae', model_specs['dae']).to(device)
t0 = time.perf_counter()
hist, _ = train_dense_ae(model, X_htrain, X_hval, device, args.epochs, args.batch_size, 0.05, args.patience, 'DAE')
training_seconds['dae'] = time.perf_counter() - t0
hist.to_csv(REPORT_DIR/'anomaly_history_dae.csv', index=False)
package = {'model_type':'dae','model_config':model_specs['dae'],'features':feature_names,'imputer_medians':medians,'scaler_mean':means,'scaler_scale':scales}
score_hval = score_window_model(package, model, healthy_val[feature_names].to_numpy(np.float32), modes_hval, device=device)
thresholds['dae'] = float(np.quantile(score_hval, 1.0 - args.target_fpr))
score_all = score_window_model(package, model, frame[feature_names].to_numpy(np.float32), modes_from_frame(frame), device=device)
window_scores['dae'] = pd.Series(score_all, index=frame.index)
artifacts['dae'] = {**package,'threshold':thresholds['dae'],'state_dict':{k:v.detach().cpu() for k,v in model.state_dict().items()},'seq_len':1,'display_name':'Denoising Autoencoder'}
del model; gc.collect()

# VAE
model = build_model('vae', model_specs['vae']).to(device)
t0 = time.perf_counter()
hist, _ = train_vae(model, X_htrain, X_hval, device, args.epochs, args.batch_size, beta=1e-3, patience=args.patience, name='VAE')
training_seconds['vae'] = time.perf_counter() - t0
hist.to_csv(REPORT_DIR/'anomaly_history_vae.csv', index=False)
package = {'model_type':'vae','model_config':model_specs['vae'],'features':feature_names,'imputer_medians':medians,'scaler_mean':means,'scaler_scale':scales}
score_hval = score_window_model(package, model, healthy_val[feature_names].to_numpy(np.float32), device=device)
thresholds['vae'] = float(np.quantile(score_hval, 1.0 - args.target_fpr))
score_all = score_window_model(package, model, frame[feature_names].to_numpy(np.float32), device=device)
window_scores['vae'] = pd.Series(score_all, index=frame.index)
artifacts['vae'] = {**package,'threshold':thresholds['vae'],'state_dict':{k:v.detach().cpu() for k,v in model.state_dict().items()},'seq_len':1,'display_name':'Variational Autoencoder'}
del model; gc.collect()

# Conditional VAE
model = build_model('cvae', model_specs['cvae']).to(device)
t0 = time.perf_counter()
hist, _ = train_vae(model, X_htrain, X_hval, device, args.epochs, args.batch_size, beta=1e-3, patience=args.patience, name='Conditional VAE', train_modes=modes_htrain, val_modes=modes_hval)
training_seconds['cvae'] = time.perf_counter() - t0
hist.to_csv(REPORT_DIR/'anomaly_history_cvae.csv', index=False)
package = {'model_type':'cvae','model_config':model_specs['cvae'],'features':feature_names,'imputer_medians':medians,'scaler_mean':means,'scaler_scale':scales,'mode_feature':'process_mode__last'}
score_hval = score_window_model(package, model, healthy_val[feature_names].to_numpy(np.float32), modes_hval, device=device)
thresholds['cvae'] = float(np.quantile(score_hval, 1.0 - args.target_fpr))
score_all = score_window_model(package, model, frame[feature_names].to_numpy(np.float32), modes_from_frame(frame), device=device)
window_scores['cvae'] = pd.Series(score_all, index=frame.index)
artifacts['cvae'] = {**package,'threshold':thresholds['cvae'],'state_dict':{k:v.detach().cpu() for k,v in model.state_dict().items()},'seq_len':1,'display_name':'Process-mode Conditional VAE'}
del model; gc.collect()

# Sequence data for LSTM AE and common-support comparison.
seq_train, train_endpoints, _, _, _ = build_sequences(frame, X_all, args.seq_len, partitions={'train'}, healthy_only=True)
seq_hval, hval_endpoints, _, _, _ = build_sequences(frame, X_all, args.seq_len, partitions={'validation'}, healthy_only=True)
seq_val, val_endpoints, val_labels, val_runs, val_times = build_sequences(frame, X_all, args.seq_len, partitions={'validation'}, healthy_only=False)
seq_test, test_endpoints, test_labels, test_runs, test_times = build_sequences(frame, X_all, args.seq_len, partitions={'test'}, healthy_only=False)
print(f'LSTM-AE healthy train sequences: {len(seq_train):,}', flush=True)
print(f'LSTM-AE healthy validation sequences: {len(seq_hval):,}', flush=True)
print(f'Common validation endpoint windows: {len(seq_val):,}', flush=True)
print(f'Common test endpoint windows: {len(seq_test):,}', flush=True)

model = build_model('lstm_ae', model_specs['lstm_ae']).to(device)
t0 = time.perf_counter()
hist, _ = train_lstm_ae(model, seq_train, seq_hval, device, args.epochs, args.seq_batch_size, args.patience, 'LSTM Encoder-Decoder')
training_seconds['lstm_ae'] = time.perf_counter() - t0
hist.to_csv(REPORT_DIR/'anomaly_history_lstm_ae.csv', index=False)
package = {'model_type':'lstm_ae','model_config':model_specs['lstm_ae'],'features':feature_names,'imputer_medians':medians,'scaler_mean':means,'scaler_scale':scales,'seq_len':args.seq_len}
score_hval = score_sequence_model(package, model, seq_hval, device=device)
thresholds['lstm_ae'] = float(np.quantile(score_hval, 1.0 - args.target_fpr))
val_seq_score = score_sequence_model(package, model, seq_val, device=device)
test_seq_score = score_sequence_model(package, model, seq_test, device=device)
artifacts['lstm_ae'] = {**package,'threshold':thresholds['lstm_ae'],'state_dict':{k:v.detach().cpu() for k,v in model.state_dict().items()},'display_name':'LSTM Encoder-Decoder Autoencoder'}
del model; gc.collect()

# Validation model selection on common run-independent endpoints.
val_rows = frame.loc[val_endpoints, ['run_id','scenario','time_start','time_end','anomaly_label','run_target_label']].copy()
test_rows = frame.loc[test_endpoints, ['run_id','scenario','time_start','time_end','anomaly_label','run_target_label']].copy()
validation_metrics = []
test_metrics = []

for name in ('dae','vae','cvae'):
    vscore = window_scores[name].loc[val_endpoints].to_numpy(float)
    tscore = window_scores[name].loc[test_endpoints].to_numpy(float)
    vm = binary_metrics(val_labels, vscore, thresholds[name]); vm.update(model=name, support='common_sequence_endpoints', training_seconds=training_seconds[name])
    tm = binary_metrics(test_labels, tscore, thresholds[name]); tm.update(model=name, support='common_sequence_endpoints', training_seconds=training_seconds[name])
    validation_metrics.append(vm); test_metrics.append(tm)
    val_rows[f'{name}_score'] = vscore; val_rows[f'{name}_pred'] = (vscore >= thresholds[name]).astype(int)
    test_rows[f'{name}_score'] = tscore; test_rows[f'{name}_pred'] = (tscore >= thresholds[name]).astype(int)

vm = binary_metrics(val_labels, val_seq_score, thresholds['lstm_ae']); vm.update(model='lstm_ae', support='common_sequence_endpoints', training_seconds=training_seconds['lstm_ae'])
tm = binary_metrics(test_labels, test_seq_score, thresholds['lstm_ae']); tm.update(model='lstm_ae', support='common_sequence_endpoints', training_seconds=training_seconds['lstm_ae'])
validation_metrics.append(vm); test_metrics.append(tm)
val_rows['lstm_ae_score'] = val_seq_score; val_rows['lstm_ae_pred'] = (val_seq_score >= thresholds['lstm_ae']).astype(int)
test_rows['lstm_ae_score'] = test_seq_score; test_rows['lstm_ae_pred'] = (test_seq_score >= thresholds['lstm_ae']).astype(int)

# Existing IF baselines, evaluated on the same endpoint support.
for name, path, mode_cond in (
    ('isolation_forest', MODEL_DIR/'isolation_forest.joblib', False),
    ('mode_conditioned_isolation_forest', MODEL_DIR/'mode_conditioned_isolation_forest.joblib', True),
):
    val_eval = evaluate_existing_if(frame, feature_names, val_endpoints, path, mode_cond)
    test_eval = evaluate_existing_if(frame, feature_names, test_endpoints, path, mode_cond)
    if val_eval is None or test_eval is None: continue
    vs, vp, vv = val_eval; ts, tp, tv = test_eval
    # For IF, threshold differs per mode in mode-conditioned case, so metrics use provided predictions.
    yv = val_labels[vv]; yt = test_labels[tv]
    def metric_from_pred(y, score, pred):
        r = {'accuracy':float(accuracy_score(y,pred)),'balanced_accuracy':float(balanced_accuracy_score(y,pred)),'macro_f1':float(f1_score(y,pred,average='macro',zero_division=0)),'fault_precision':float(precision_score(y,pred,zero_division=0)),'fault_recall':float(recall_score(y,pred,zero_division=0)),'threshold':None,'n':int(len(y)),'fault_fraction':float(y.mean())}
        if len(np.unique(y))==2 and np.isfinite(score).all():
            r['roc_auc']=float(roc_auc_score(y,score));r['average_precision']=float(average_precision_score(y,score))
        else:r['roc_auc']=None;r['average_precision']=None
        return r
    vmet = metric_from_pred(yv, vs[vv], vp[vv]); vmet.update(model=name,support='common_sequence_endpoints',training_seconds=None)
    tmet = metric_from_pred(yt, ts[tv], tp[tv]); tmet.update(model=name,support='common_sequence_endpoints',training_seconds=None)
    validation_metrics.append(vmet);test_metrics.append(tmet)
    val_rows[f'{name}_score'] = vs;val_rows[f'{name}_pred'] = vp
    test_rows[f'{name}_score'] = ts;test_rows[f'{name}_pred'] = tp

val_df = pd.DataFrame(validation_metrics).sort_values(['macro_f1','balanced_accuracy'],ascending=False)
test_df = pd.DataFrame(test_metrics).sort_values(['macro_f1','balanced_accuracy'],ascending=False)
val_df.to_csv(REPORT_DIR/'anomaly_model_comparison_validation.csv', index=False)
test_df.to_csv(REPORT_DIR/'anomaly_model_comparison_test.csv', index=False)
val_rows.to_csv(REPORT_DIR/'anomaly_predictions_validation.csv', index=False)
test_rows.to_csv(REPORT_DIR/'anomaly_predictions_test.csv', index=False)
print('\nValidation comparison (used for model selection):')
print(val_df.to_string(index=False), flush=True)
print('\nLocked test comparison:')
print(test_df.to_string(index=False), flush=True)

# Select only from validation results. This preserves the test set for final reporting.
selected_name = str(val_df.iloc[0]['model'])
selected_is_deep = selected_name in artifacts
selection = {
    'selection_metric': 'validation_macro_f1_on_common_independent_run_endpoints',
    'selected_model': selected_name,
    'selected_is_deep_model': bool(selected_is_deep),
    'target_healthy_validation_fpr': float(args.target_fpr),
    'sequence_length_windows': int(args.seq_len),
    'sequence_context_seconds': int(args.seq_len * int(CFG.get('window_step_seconds', 60))),
    'validation_ranking': val_df.to_dict(orient='records'),
    'locked_test_results': test_df.to_dict(orient='records'),
    'scientific_note': 'FinalScientific v4.6.3 Scientific1900: all deep models are trained only on dedicated healthy TRAIN runs; thresholds use healthy VALIDATION only; architecture selection uses VALIDATION only; locked TEST is not used for selection.',
}
(REPORT_DIR/'anomaly_model_selection.json').write_text(json.dumps(selection,indent=2),encoding='utf-8')

# Save every deep model; the validation-selected deep model is also saved as the deployment candidate.
for name, artifact in artifacts.items():
    torch.save(artifact, MODEL_DIR/f'anomaly_{name}.pt')
if selected_is_deep:
    selected_artifact = dict(artifacts[selected_name])
    selected_artifact['selection_metadata'] = selection
    torch.save(selected_artifact, MODEL_DIR/'best_deep_anomaly_detector.pt')
    print(f'\nDeployment candidate saved: best_deep_anomaly_detector.pt ({selected_name})', flush=True)
else:
    old = MODEL_DIR/'best_deep_anomaly_detector.pt'
    if old.exists(): old.unlink()
    print(f'\nExisting baseline remains validation-selected anomaly detector: {selected_name}', flush=True)

# Run-level bootstrap on locked test support.
bootstrap_rows = []
for name in [m for m in test_df['model'].astype(str) if f'{m}_pred' in test_rows.columns]:
    row = bootstrap_run_ci(test_rows, name, n_boot=args.bootstrap, seed=int(CFG['seed'])+1101)
    if row: bootstrap_rows.append(row)
pd.DataFrame(bootstrap_rows).to_csv(REPORT_DIR/'anomaly_model_bootstrap_test.csv', index=False)

# Detection delay for selected model if a prediction column exists.
if f'{selected_name}_pred' in test_rows.columns:
    delays = []
    # Campaign metadata is inferred from time labels already in feature table.
    for run_id, part in test_rows.groupby('run_id'):
        part = part.sort_values('time_end')
        fault = part[part['anomaly_label'].astype(int) == 1]
        if fault.empty: continue
        onset = float(fault['time_start'].min())
        after = part[(part['time_end'] >= onset) & (part[f'{selected_name}_pred'].astype(int) == 1)]
        first = float(after['time_end'].iloc[0]) if len(after) else np.nan
        delays.append({'run_id':run_id,'fault_onset_window_s':onset,'first_anomaly_detection_s':first,'detection_delay_s':max(0.0,first-onset) if np.isfinite(first) else np.nan,'detected':bool(np.isfinite(first))})
    pd.DataFrame(delays).to_csv(REPORT_DIR/'anomaly_detection_delay_selected_model.csv', index=False)

print('\nSelected anomaly model from validation:', selected_name, flush=True)
print('Reports written to:', REPORT_DIR, flush=True)
