from __future__ import annotations

from pathlib import Path
import joblib
import numpy as np
import pandas as pd

from features import ROOT, windowize
try:
    from anomaly_models import load_deep_anomaly_artifact, score_window_model, preprocess_array, score_sequence_model
except Exception:
    load_deep_anomaly_artifact = score_window_model = preprocess_array = score_sequence_model = None


def _decode_base(package: dict, prediction) -> np.ndarray:
    prediction = np.asarray(prediction).astype(int)
    encoder = package.get("label_encoder")
    if encoder is not None:
        return encoder.inverse_transform(prediction)
    original = package.get("original_classes")
    if original is not None:
        original = np.asarray(original).astype(int)
        if prediction.size and prediction.max(initial=0) < len(original):
            return original[prediction]
    return prediction


def _original_classes(package: dict, n_classes: int | None = None) -> np.ndarray:
    original = package.get("original_classes")
    if original is not None:
        return np.asarray(original).astype(int)
    encoder = package.get("label_encoder")
    if encoder is not None:
        return np.asarray(encoder.classes_).astype(int)
    return np.arange(n_classes or 0, dtype=int)


def _hierarchical_probabilities(package: dict, X: pd.DataFrame) -> np.ndarray:
    """Compose probabilities for the final 19-class hierarchy.

    v4.6.3 adds process-fault codes 11 and 12.  The old serving code had a
    hard-coded 1..10 loop, which silently assigned no hierarchical probability
    to the two new pump-degradation classes.  Final19 artifacts therefore carry
    explicit actuator_codes/sensor_codes; defaults preserve v4.6.3 semantics.
    """
    original = np.asarray(package["original_classes"]).astype(int)
    code_to_col = {int(code): i for i, code in enumerate(original)}
    actuator_codes = np.asarray(package.get("actuator_codes", list(range(1, 13))), dtype=int)
    sensor_codes = np.asarray(package.get("sensor_codes", list(range(101, 107))), dtype=int)
    family_prob = package["family_model"].predict_proba(X)
    actuator_prob = package["actuator_model"].predict_proba(X)
    sensor_prob = package["sensor_model"].predict_proba(X)
    out = np.zeros((len(X), len(original)), dtype=np.float32)
    if 0 in code_to_col:
        out[:, code_to_col[0]] = family_prob[:, 0]
    for local_idx, code in enumerate(actuator_codes):
        if int(code) in code_to_col and local_idx < actuator_prob.shape[1]:
            out[:, code_to_col[int(code)]] = family_prob[:, 1] * actuator_prob[:, local_idx]
    for local_idx, code in enumerate(sensor_codes):
        if int(code) in code_to_col and local_idx < sensor_prob.shape[1]:
            out[:, code_to_col[int(code)]] = family_prob[:, 2] * sensor_prob[:, local_idx]
    denom = out.sum(axis=1, keepdims=True)
    denom[denom <= 0] = 1.0
    return out / denom


def _topk_summary(prob: np.ndarray, classes: np.ndarray, k: int = 3) -> list[str]:
    result = []
    for row in prob:
        idx = np.argsort(row)[::-1][: min(k, len(row))]
        result.append(" | ".join(f"{int(classes[i])}:{row[i]:.1%}" for i in idx))
    return result


def _load(path: Path):
    return joblib.load(path) if path.exists() else None


def _add_classifier(out: pd.DataFrame, D: pd.DataFrame, name: str, package: dict):
    X = D.reindex(columns=package["features"])
    model = package["model"]
    pred_encoded = model.predict(X).astype(int)
    pred_original = _decode_base(package, pred_encoded)
    prob = model.predict_proba(X)
    classes = _original_classes(package, prob.shape[1])
    out[f"{name}_fault_code"] = pred_original.astype(int)
    out[f"{name}_confidence"] = prob.max(axis=1)
    out[f"{name}_top3"] = _topk_summary(prob, classes)
    return prob, classes


def _add_global_anomaly(out: pd.DataFrame, D: pd.DataFrame):
    package = _load(ROOT / "ml" / "models" / "isolation_forest.joblib")
    if package is None:
        return
    try:
        X = D.reindex(columns=package["features"])
        Z = package["imputer"].transform(X)
        if "scaler" in package:
            Z = package["scaler"].transform(Z)
        score = -package["model"].score_samples(Z)
        out["global_anomaly_score"] = score
        out["global_is_anomaly"] = (score >= float(package["threshold"])).astype(int)
    except Exception:
        pass


def _add_mode_anomaly(out: pd.DataFrame, D: pd.DataFrame):
    package = _load(ROOT / "ml" / "models" / "mode_conditioned_isolation_forest.joblib")
    if package is None:
        return
    try:
        features = package["features"]
        mode_feature = package.get("mode_feature", "process_mode__last")
        mode_models = package["mode_models"]
        scores = np.full(len(D), np.nan, dtype=float)
        flags = np.zeros(len(D), dtype=int)
        modes = pd.to_numeric(D.get(mode_feature, np.nan), errors="coerce").round()
        for mode in pd.Series(modes).dropna().unique():
            mode_int = int(mode)
            info = mode_models.get(mode_int, mode_models.get(str(mode_int)))
            if info is None:
                continue
            rows = np.flatnonzero(np.asarray(modes == mode))
            X = D.iloc[rows].reindex(columns=features)
            Z = info["imputer"].transform(X)
            s = -info["model"].score_samples(Z)
            scores[rows] = s
            flags[rows] = (s >= float(info["threshold"])).astype(int)
        out["mode_anomaly_score"] = scores
        out["mode_is_anomaly"] = flags
    except Exception:
        pass



def _add_advanced_anomaly(out: pd.DataFrame, D: pd.DataFrame):
    """Add the validation-selected deep anomaly detector when available."""
    path = ROOT / "ml" / "models" / "best_deep_anomaly_detector.pt"
    if not path.exists() or load_deep_anomaly_artifact is None:
        return
    try:
        package, model = load_deep_anomaly_artifact(path, device="cpu")
        features = package["features"]
        model_type = package["model_type"]
        threshold = float(package["threshold"])
        Xraw = D.reindex(columns=features).to_numpy(np.float32)
        if model_type in ("dae", "vae", "cvae"):
            modes = None
            if model_type == "cvae":
                mode_feature = package.get("mode_feature", "process_mode__last")
                modes = pd.to_numeric(D.get(mode_feature, 0), errors="coerce").round().fillna(0).astype(int).clip(0, 6).to_numpy()
            score = score_window_model(package, model, Xraw, modes=modes, device="cpu")
            flag = (score >= threshold).astype(int)
        elif model_type == "lstm_ae":
            seq_len = int(package.get("seq_len", 6))
            Xp = preprocess_array(Xraw, package["imputer_medians"], package["scaler_mean"], package["scaler_scale"])
            score = np.full(len(D), np.nan, dtype=float)
            flag = np.zeros(len(D), dtype=int)
            # Build sequences independently inside each run so sequence context never crosses run boundaries.
            for _, part in D.groupby("run_id", sort=False):
                positions = D.index.get_indexer(part.sort_values("time_start").index)
                if len(positions) < seq_len:
                    continue
                seqs, ends = [], []
                for end_local in range(seq_len - 1, len(positions)):
                    seqs.append(Xp[positions[end_local-seq_len+1:end_local+1]])
                    ends.append(positions[end_local])
                seqs = np.stack(seqs).astype(np.float32)
                scores = score_sequence_model(package, model, seqs, device="cpu")
                score[np.asarray(ends)] = scores
                flag[np.asarray(ends)] = (scores >= threshold).astype(int)
        else:
            return
        out["advanced_anomaly_score"] = score
        out["advanced_is_anomaly"] = flag
        out["advanced_anomaly_model"] = str(package.get("display_name", model_type))
    except Exception:
        pass


def predict_csv(path: Path | str) -> pd.DataFrame:
    """Serve the strongest available trained model while keeping research baselines."""
    D = windowize(pd.read_csv(path))
    if D.empty:
        return pd.DataFrame()
    out = D[["run_id", "scenario", "time_start", "time_end"]].copy()

    for name in ("random_forest", "xgboost"):
        package = _load(ROOT / "ml" / "models" / f"{name}.joblib")
        if package is not None:
            try:
                _add_classifier(out, D, name, package)
            except Exception:
                pass

    enhanced_package = _load(ROOT / "ml" / "models" / "enhanced_xgboost.joblib")
    enhanced_prob = None
    if enhanced_package is not None:
        try:
            X = D.reindex(columns=enhanced_package["features"])
            enhanced_prob = enhanced_package["model"].predict_proba(X)
            classes = np.asarray(enhanced_package["original_classes"]).astype(int)
            out["enhanced_xgboost_fault_code"] = classes[enhanced_prob.argmax(axis=1)]
            out["enhanced_xgboost_confidence"] = enhanced_prob.max(axis=1)
            out["enhanced_xgboost_top3"] = _topk_summary(enhanced_prob, classes)
        except Exception:
            enhanced_prob = None

    extra_package = _load(ROOT / "ml" / "models" / "extra_trees.joblib")
    if extra_package is not None:
        try:
            X = D.reindex(columns=extra_package["features"])
            prob = extra_package["model"].predict_proba(X)
            classes = np.asarray(extra_package["original_classes"]).astype(int)
            out["extra_trees_fault_code"] = classes[prob.argmax(axis=1)]
            out["extra_trees_confidence"] = prob.max(axis=1)
        except Exception:
            pass

    hier_package = _load(ROOT / "ml" / "models" / "hierarchical_xgboost.joblib")
    if hier_package is not None:
        try:
            X = D.reindex(columns=hier_package["features"])
            prob = _hierarchical_probabilities(hier_package, X)
            classes = np.asarray(hier_package["original_classes"]).astype(int)
            out["hierarchical_xgboost_fault_code"] = classes[prob.argmax(axis=1)]
            out["hierarchical_xgboost_confidence"] = prob.max(axis=1)
        except Exception:
            pass

    ensemble_package = _load(ROOT / "ml" / "models" / "q1_probability_ensemble.joblib")
    ensemble_prob = None
    if ensemble_package is not None:
        try:
            X = D.reindex(columns=ensemble_package["features"])
            classes = np.asarray(ensemble_package["original_classes"]).astype(int)
            flat_prob = ensemble_package["flat_xgb"].predict_proba(X)
            extra_prob = ensemble_package["extra_trees"].predict_proba(X)
            hier_prob = _hierarchical_probabilities(ensemble_package, X)
            weights = tuple(float(v) for v in ensemble_package.get("weights", (2, 1, 1)))
            ensemble_prob = (
                weights[0] * flat_prob + weights[1] * extra_prob + weights[2] * hier_prob
            ) / max(1e-12, sum(weights))
            out["probability_ensemble_fault_code"] = classes[ensemble_prob.argmax(axis=1)]
            out["probability_ensemble_confidence"] = ensemble_prob.max(axis=1)
            out["probability_ensemble_top3"] = _topk_summary(ensemble_prob, classes)
        except Exception:
            ensemble_prob = None

    if ensemble_prob is not None:
        out["primary_fault_code"] = out["probability_ensemble_fault_code"].astype(int)
        out["primary_confidence"] = out["probability_ensemble_confidence"].astype(float)
        out["primary_top3"] = out["probability_ensemble_top3"]
        out["primary_model"] = "Probability Ensemble"
    elif enhanced_prob is not None:
        out["primary_fault_code"] = out["enhanced_xgboost_fault_code"].astype(int)
        out["primary_confidence"] = out["enhanced_xgboost_confidence"].astype(float)
        out["primary_top3"] = out["enhanced_xgboost_top3"]
        out["primary_model"] = "Enhanced XGBoost"
    elif "xgboost_fault_code" in out:
        out["primary_fault_code"] = out["xgboost_fault_code"].astype(int)
        out["primary_confidence"] = out["xgboost_confidence"].astype(float)
        out["primary_top3"] = out.get("xgboost_top3", "")
        out["primary_model"] = "XGBoost"
    elif "random_forest_fault_code" in out:
        out["primary_fault_code"] = out["random_forest_fault_code"].astype(int)
        out["primary_confidence"] = out["random_forest_confidence"].astype(float)
        out["primary_top3"] = out.get("random_forest_top3", "")
        out["primary_model"] = "Random Forest"
    else:
        out["primary_fault_code"] = 0
        out["primary_confidence"] = np.nan
        out["primary_top3"] = ""
        out["primary_model"] = "No trained classifier"

    _add_global_anomaly(out, D)
    _add_mode_anomaly(out, D)
    _add_advanced_anomaly(out, D)
    return out
