from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
    roc_auc_score,
    top_k_accuracy_score,
)
from sklearn.preprocessing import label_binarize

from features import ROOT
from final19_common import REPORT_DIR, DATA_DIR, CACHE_FILE, build_or_load_feature_cache


def family(code: int) -> int:
    code = int(code)
    if code == 0:
        return 0
    if 1 <= code <= 12:
        return 1
    return 2


def expected_calibration_error(y_true, prob, bins=15):
    confidence = prob.max(axis=1)
    prediction = prob.argmax(axis=1)
    correct = (prediction == y_true).astype(float)
    edges = np.linspace(0, 1, bins + 1)
    ece = 0.0
    rows = []
    for left, right in zip(edges[:-1], edges[1:]):
        mask = (
            (confidence >= left)
            & (
                (confidence < right)
                if right < 1
                else (confidence <= right)
            )
        )
        if not mask.any():
            continue
        acc = correct[mask].mean()
        conf = confidence[mask].mean()
        weight = mask.mean()
        ece += weight * abs(acc - conf)
        rows.append({
            "bin_left": left,
            "bin_right": right,
            "n": int(mask.sum()),
            "accuracy": float(acc),
            "mean_confidence": float(conf),
        })
    return float(ece), pd.DataFrame(rows)


def multiclass_brier(y_true, prob):
    one_hot = np.eye(prob.shape[1], dtype=np.float64)[y_true]
    return float(np.mean(np.sum((prob - one_hot) ** 2, axis=1)))


def probability_metrics(y_true, prob):
    n_classes = prob.shape[1]
    y_binary = label_binarize(
        y_true,
        classes=np.arange(n_classes),
    )
    return {
        "top1_accuracy": float(
            accuracy_score(y_true, prob.argmax(axis=1))
        ),
        "top3_accuracy": float(
            top_k_accuracy_score(
                y_true,
                prob,
                k=min(3, n_classes),
                labels=np.arange(n_classes),
            )
        ),
        "macro_roc_auc_ovr": float(
            roc_auc_score(
                y_binary,
                prob,
                average="macro",
                multi_class="ovr",
            )
        ),
        "macro_average_precision": float(
            average_precision_score(
                y_binary,
                prob,
                average="macro",
            )
        ),
        "multiclass_brier": multiclass_brier(y_true, prob),
    }


def bootstrap_by_run(
    frame,
    y_true_col,
    y_pred_col,
    run_col="run_id",
    n_boot=1000,
    seed=42,
):
    rng = np.random.default_rng(seed)
    run_ids = frame[run_col].astype(str).unique()
    values = []

    for _ in range(n_boot):
        sampled = rng.choice(run_ids, size=len(run_ids), replace=True)
        pieces = []
        for occurrence, run_id in enumerate(sampled):
            part = frame[frame[run_col].astype(str) == str(run_id)].copy()
            part["_bootstrap_run"] = f"{run_id}_{occurrence}"
            pieces.append(part)
        boot = pd.concat(pieces, ignore_index=True)

        yt = boot[y_true_col].astype(int)
        yp = boot[y_pred_col].astype(int)
        values.append([
            accuracy_score(yt, yp),
            balanced_accuracy_score(yt, yp),
            f1_score(yt, yp, average="macro", zero_division=0),
        ])

    array = np.asarray(values)
    names = ["accuracy", "balanced_accuracy", "macro_f1"]
    result = {}
    for j, name in enumerate(names):
        result[name] = {
            "mean": float(array[:, j].mean()),
            "ci95_low": float(np.quantile(array[:, j], 0.025)),
            "ci95_high": float(np.quantile(array[:, j], 0.975)),
        }
    return result


def run_metadata():
    output = REPORT_DIR / "campaign_run_metadata.csv"
    if output.exists():
        return pd.read_csv(output)

    rows = []
    for path in sorted(DATA_DIR.glob("v463_sci1900_fc*_rep*.csv")):
        try:
            d = pd.read_csv(path, nrows=1)
            if d.empty:
                continue
            r = d.iloc[0]

            def pick(names, default=np.nan):
                for name in names:
                    if name in d.columns and pd.notna(r[name]):
                        return r[name]
                return default

            rows.append({
                "run_id": str(pick(["run_id"], path.stem)),
                "scenario": str(pick(["scenario"], path.stem)),
                "fault_code": int(float(pick(
                    ["run_target_label", "target", "injected_fault_code", "requested_fault_code", "fault_code"], 0
                ))),
                "sensor_fault_code": int(float(pick(
                    ["sensor_fault_code"], 0
                ))),
                "fault_severity": float(pick(
                    ["fault_severity", "requested_fault_severity", "severity"],
                    np.nan,
                )),
                "fault_start_s": float(pick(
                    ["requested_fault_start_s", "fault_start_s"],
                    np.nan,
                )),
                "fault_end_s": float(pick(
                    ["requested_fault_end_s", "fault_end_s"],
                    np.nan,
                )),
                "initial_level_m": float(pick(
                    ["initial_level_m"], np.nan
                )),
                "initial_temperature_K": float(pick(
                    ["initial_temperature_K"], np.nan
                )),
                "nominal_flow_kg_s": float(pick(
                    ["nominal_flow_kg_s"], np.nan
                )),
                "heat_power_W": float(pick(
                    ["heat_power_W"], np.nan
                )),
                "sensor_fault_value": float(pick(
                    ["sensor_fault_value"], np.nan
                )),
            })
        except Exception as exc:
            print("Metadata skip:", path.name, exc)

    frame = pd.DataFrame(rows)
    frame.to_csv(output, index=False)
    return frame


parser = argparse.ArgumentParser()
parser.add_argument("--bootstrap", type=int, default=1000)
args = parser.parse_args()

pred_path = REPORT_DIR / "final19_locked_test_predictions.csv"
prob_path = REPORT_DIR / "final19_locked_test_probabilities.npz"
if not pred_path.exists() or not prob_path.exists():
    raise SystemExit(
        "Run ml/train_final19_supervised.py before Final19 advanced validation."
    )

pred = pd.read_csv(pred_path)
prob_data = np.load(prob_path)
classes = prob_data["original_classes"].astype(int)
y_original = prob_data["y_test_original"].astype(int)
code_to_encoded = {int(c): i for i, c in enumerate(classes)}
y_encoded = np.array(
    [code_to_encoded[int(v)] for v in y_original],
    dtype=int,
)

model_names = [
    "enhanced_xgboost",
    "extra_trees",
    "hierarchical_xgboost",
    "probability_ensemble",
]

summary_rows = []
bootstrap_results = {}
calibration_rows = []
class_metric_rows = []
family_rows = []
coverage_rows = []

for model_name in model_names:
    prob = prob_data[model_name]
    pred_encoded = prob.argmax(axis=1)
    pred_original = classes[pred_encoded]

    base = {
        "model": model_name,
        "accuracy": float(
            accuracy_score(y_original, pred_original)
        ),
        "balanced_accuracy": float(
            balanced_accuracy_score(y_original, pred_original)
        ),
        "macro_f1": float(
            f1_score(
                y_original,
                pred_original,
                average="macro",
                zero_division=0,
            )
        ),
    }
    base.update(probability_metrics(y_encoded, prob))
    ece, bins = expected_calibration_error(y_encoded, prob)
    base["ece_15bin"] = ece
    summary_rows.append(base)

    bins["model"] = model_name
    calibration_rows.append(bins)

    report = classification_report(
        y_original,
        pred_original,
        labels=classes,
        output_dict=True,
        zero_division=0,
    )
    for code in classes:
        values = report[str(int(code))]
        class_metric_rows.append({
            "model": model_name,
            "class_code": int(code),
            "precision": values["precision"],
            "recall": values["recall"],
            "f1": values["f1-score"],
            "support": values["support"],
        })

    family_true = np.array([family(x) for x in y_original])
    family_pred = np.array([family(x) for x in pred_original])
    family_rows.append({
        "model": model_name,
        "family_accuracy": float(
            accuracy_score(family_true, family_pred)
        ),
        "family_balanced_accuracy": float(
            balanced_accuracy_score(
                family_true, family_pred
            )
        ),
        "family_macro_f1": float(
            f1_score(
                family_true,
                family_pred,
                average="macro",
                zero_division=0,
            )
        ),
    })

    temp = pred[
        ["run_id", "true_label"]
    ].copy()
    temp["predicted"] = pred_original
    bootstrap_results[model_name] = bootstrap_by_run(
        temp,
        "true_label",
        "predicted",
        n_boot=args.bootstrap,
    )

    confidence = prob.max(axis=1)
    correct = (pred_original == y_original)
    for threshold in np.arange(0.40, 0.96, 0.05):
        mask = confidence >= threshold
        if not mask.any():
            continue
        coverage_rows.append({
            "model": model_name,
            "confidence_threshold": float(threshold),
            "coverage": float(mask.mean()),
            "selective_accuracy": float(
                correct[mask].mean()
            ),
            "selective_macro_f1": float(
                f1_score(
                    y_original[mask],
                    pred_original[mask],
                    average="macro",
                    zero_division=0,
                )
            ),
            "n_windows": int(mask.sum()),
        })

pd.DataFrame(summary_rows).to_csv(
    REPORT_DIR / "final19_advanced_probability_metrics.csv",
    index=False,
)
pd.concat(calibration_rows, ignore_index=True).to_csv(
    REPORT_DIR / "final19_calibration_bins.csv",
    index=False,
)
pd.DataFrame(class_metric_rows).to_csv(
    REPORT_DIR / "final19_per_class_metrics.csv",
    index=False,
)
pd.DataFrame(family_rows).to_csv(
    REPORT_DIR / "final19_fault_family_metrics.csv",
    index=False,
)
pd.DataFrame(coverage_rows).to_csv(
    REPORT_DIR / "final19_confidence_coverage.csv",
    index=False,
)

# Confusion matrices and top confusion pairs.
confusion_rows = []
for model_name in model_names:
    pred_original = pred[
        f"{model_name}_predicted_label"
    ].astype(int).to_numpy()
    cm = confusion_matrix(
        y_original, pred_original, labels=classes
    )
    pd.DataFrame(
        cm, index=classes, columns=classes
    ).to_csv(
        REPORT_DIR / f"confusion_{model_name}.csv"
    )

    denom = cm.sum(axis=1, keepdims=True)
    normalized = np.divide(
        cm,
        denom,
        out=np.zeros_like(cm, dtype=float),
        where=denom != 0,
    )
    pd.DataFrame(
        normalized, index=classes, columns=classes
    ).to_csv(
        REPORT_DIR / f"confusion_normalized_{model_name}.csv"
    )

    for i, true_code in enumerate(classes):
        for j, pred_code in enumerate(classes):
            if i == j or cm[i, j] == 0:
                continue
            confusion_rows.append({
                "model": model_name,
                "true_class": int(true_code),
                "predicted_class": int(pred_code),
                "count": int(cm[i, j]),
                "row_fraction": float(normalized[i, j]),
            })

pd.DataFrame(confusion_rows).sort_values(
    ["model", "count"],
    ascending=[True, False],
).to_csv(
    REPORT_DIR / "final19_top_confusion_pairs.csv",
    index=False,
)

# Severity and operating-mode stratification for best ensemble.
metadata = run_metadata()
ensemble_pred_col = "probability_ensemble_predicted_label"
analysis = pred.merge(
    metadata,
    on="run_id",
    how="left",
    suffixes=("", "_run"),
)

actuator = analysis[
    analysis["true_label"].between(1, 12)
    & analysis["fault_severity"].notna()
].copy()
if len(actuator):
    actuator["severity_band"] = pd.cut(
        actuator["fault_severity"],
        bins=[-np.inf, 0.40, 0.60, np.inf],
        labels=["low", "medium", "high"],
    )
    rows = []
    for band, part in actuator.groupby(
        "severity_band", observed=True
    ):
        if len(part) == 0:
            continue
        rows.append({
            "severity_band": str(band),
            "n_windows": len(part),
            "n_runs": part["run_id"].nunique(),
            "accuracy": accuracy_score(
                part["true_label"],
                part[ensemble_pred_col],
            ),
            "balanced_accuracy": balanced_accuracy_score(
                part["true_label"],
                part[ensemble_pred_col],
            ),
            "macro_f1": f1_score(
                part["true_label"],
                part[ensemble_pred_col],
                average="macro",
                zero_division=0,
            ),
        })
    pd.DataFrame(rows).to_csv(
        REPORT_DIR / "final19_severity_stratified_performance.csv",
        index=False,
    )

# Operating mode from cached feature table.
build_or_load_feature_cache(rebuild=False)
if CACHE_FILE.exists():
    feature_table = joblib.load(CACHE_FILE)
    mode_col = "process_mode__last"
    if mode_col in feature_table.columns:
        mode_map = feature_table[[
            "run_id", "time_start", "time_end", mode_col
        ]].copy()
        mode_map["process_mode"] = (
            pd.to_numeric(mode_map[mode_col], errors="coerce")
            .round()
            .astype("Int64")
        )
        mode_analysis = pred.merge(
            mode_map[
                ["run_id", "time_start", "time_end", "process_mode"]
            ],
            on=["run_id", "time_start", "time_end"],
            how="left",
        )
        rows = []
        for mode, part in mode_analysis.groupby(
            "process_mode", dropna=True
        ):
            if len(part) < 20:
                continue
            rows.append({
                "process_mode": int(mode),
                "n_windows": len(part),
                "accuracy": accuracy_score(
                    part["true_label"],
                    part[ensemble_pred_col],
                ),
                "macro_f1": f1_score(
                    part["true_label"],
                    part[ensemble_pred_col],
                    average="macro",
                    zero_division=0,
                ),
            })
        pd.DataFrame(rows).to_csv(
            REPORT_DIR / "final19_process_mode_performance.csv",
            index=False,
        )

# Onset detection delay for correctly classified ensemble windows.
delay_rows = []
for run_id, part in analysis.groupby("run_id"):
    true_code = int(part["true_label"].mode().iloc[0])
    if true_code == 0:
        continue
    start = pd.to_numeric(
        part["fault_start_s"], errors="coerce"
    ).dropna()
    if start.empty:
        continue
    onset = float(start.iloc[0])
    after = part[
        (part["time_end"] >= onset)
        & (
            part[ensemble_pred_col].astype(int)
            == part["true_label"].astype(int)
        )
    ].sort_values("time_end")

    if len(after):
        first_time = float(after.iloc[0]["time_end"])
        delay = max(0.0, first_time - onset)
        detected = True
    else:
        first_time = np.nan
        delay = np.nan
        detected = False

    delay_rows.append({
        "run_id": run_id,
        "fault_code": true_code,
        "fault_start_s": onset,
        "first_correct_detection_s": first_time,
        "detection_delay_s": delay,
        "detected": detected,
    })

delay_frame = pd.DataFrame(delay_rows)
delay_frame.to_csv(
    REPORT_DIR / "final19_fault_detection_delay_by_run.csv",
    index=False,
)
if len(delay_frame):
    detected = delay_frame[delay_frame["detected"]]
    delay_summary = {
        "n_fault_runs": int(len(delay_frame)),
        "fraction_eventually_detected": float(
            delay_frame["detected"].mean()
        ),
        "median_detection_delay_s": (
            float(detected["detection_delay_s"].median())
            if len(detected) else None
        ),
        "detected_within_60s": float(
            (
                delay_frame["detection_delay_s"] <= 60
            ).fillna(False).mean()
        ),
        "detected_within_120s": float(
            (
                delay_frame["detection_delay_s"] <= 120
            ).fillna(False).mean()
        ),
        "detected_within_300s": float(
            (
                delay_frame["detection_delay_s"] <= 300
            ).fillna(False).mean()
        ),
    }
else:
    delay_summary = {}

# Family confusion for ensemble.
ensemble_pred = pred[ensemble_pred_col].astype(int).to_numpy()
family_true = np.array([family(x) for x in y_original])
family_pred = np.array([family(x) for x in ensemble_pred])
pd.DataFrame(
    confusion_matrix(
        family_true, family_pred, labels=[0, 1, 2]
    ),
    index=["healthy", "actuator", "sensor"],
    columns=["healthy", "actuator", "sensor"],
).to_csv(
    REPORT_DIR / "final19_confusion_fault_family_ensemble.csv"
)

summary = {
    "bootstrap_unit": "independent test run",
    "bootstrap_replicates": args.bootstrap,
    "bootstrap_95ci": bootstrap_results,
    "fault_detection_delay": delay_summary,
    "validation_principles": [
        "All uncertainty intervals are bootstrapped at run level, not window level.",
        "No test run contributes to hyperparameter or ensemble-weight selection.",
        "Calibration, top-k accuracy, confidence coverage, severity stratification, process-mode stratification, and onset delay are evaluated on the held-out test runs.",
        "Actuator severity analysis is not mixed with sensor-fault magnitude because the units are not comparable.",
    ],
}
(REPORT_DIR / "final19_advanced_validation_summary.json").write_text(
    json.dumps(summary, indent=2)
)

print("\nAdvanced validation summary")
print(pd.DataFrame(summary_rows).to_string(index=False))
print("\nRun-level bootstrap 95% confidence intervals saved.")
print("Fault detection delay:", delay_summary)
