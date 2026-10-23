from __future__ import annotations

from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "ml" / "config.json").read_text(encoding="utf-8"))
SIGNALS = tuple(CFG["signals"])
STAT_NAMES = (
    "mean", "std", "min", "max", "median",
    "q05", "q95", "last", "slope", "rms",
)
TEMP_SETPOINT_K = 338.15


def numeric_series(frame: pd.DataFrame, column: str, default=np.nan) -> pd.Series:
    if column in frame.columns:
        return pd.to_numeric(frame[column], errors="coerce")
    return pd.Series(np.full(len(frame), default, dtype=float), index=frame.index, name=column)


def string_series(frame: pd.DataFrame, column: str, default="unknown") -> pd.Series:
    if column in frame.columns:
        return frame[column].fillna(default).astype(str)
    return pd.Series([default] * len(frame), index=frame.index, dtype="object", name=column)


def _gradient(y: pd.Series, t: pd.Series) -> np.ndarray:
    yy = pd.to_numeric(y, errors="coerce").to_numpy(float)
    tt = pd.to_numeric(t, errors="coerce").to_numpy(float)
    out = np.full(len(yy), np.nan, dtype=float)
    good = np.isfinite(yy) & np.isfinite(tt)
    if good.sum() < 2:
        return out
    # Interpolate only for derivative construction; original measured channel is untouched.
    s = pd.Series(yy).interpolate(limit_direction="both").to_numpy(float)
    dt = np.gradient(tt)
    dt[~np.isfinite(dt) | (np.abs(dt) < 1e-12)] = 1.0
    out = np.gradient(s) / dt
    return out


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Create the exact 17-channel analysis contract used by the final 19-class pipeline."""
    d = df.copy()

    aliases = {
        "temperature_K": "temperature_true_K",
        "level_m": "level_true_m",
        "gauge_pressure_Pa": "gauge_pressure_true_Pa",
        "production_mass_flow_kg_s": "production_mass_flow_true_kg_s",
        "agitator_speed_rpm": "agitator_speed_true_rpm",
    }
    for source, target in aliases.items():
        if source in d.columns and target not in d.columns:
            d[target] = d[source]

    measured_pairs = [
        ("temperature_measured_K", "temperature_true_K"),
        ("level_measured_m", "level_true_m"),
        ("gauge_pressure_measured_Pa", "gauge_pressure_true_Pa"),
        ("production_mass_flow_measured_kg_s", "production_mass_flow_true_kg_s"),
        ("agitator_speed_measured_rpm", "agitator_speed_true_rpm"),
    ]
    for measured, truth in measured_pairs:
        if measured not in d.columns and truth in d.columns:
            d[measured] = d[truth]

    t = numeric_series(d, "time", np.nan)

    if "temperature_rate_K_s" not in d.columns:
        d["temperature_rate_K_s"] = _gradient(numeric_series(d, "temperature_measured_K"), t)
    if "level_rate_m_s" not in d.columns:
        d["level_rate_m_s"] = _gradient(numeric_series(d, "level_measured_m"), t)
    if "temperature_error_K" not in d.columns:
        d["temperature_error_K"] = TEMP_SETPOINT_K - numeric_series(d, "temperature_measured_K")
    if "agitator_speed_error_rpm" not in d.columns:
        d["agitator_speed_error_rpm"] = (
            numeric_series(d, "cmd_agitator_rpm", 0.0)
            - numeric_series(d, "agitator_speed_measured_rpm")
        )
    if "effective_prod_flow_command_kg_s" not in d.columns:
        if "cmd_prod_flow" in d.columns:
            d["effective_prod_flow_command_kg_s"] = 10.0 * numeric_series(d, "cmd_prod_flow", 0.0)
        else:
            d["effective_prod_flow_command_kg_s"] = np.nan

    # Preserve physical heat-flow logging when available. Fall back only when the column
    # is absent entirely; never overwrite an existing fault-affected/NaN signal.
    if "effective_heat_flow_W" not in d.columns:
        if "cmd_steam" in d.columns:
            d["effective_heat_flow_W"] = 120000.0 * numeric_series(d, "cmd_steam", 0.0)
        else:
            d["effective_heat_flow_W"] = np.nan

    return d


def _stats(x, t):
    x = np.asarray(x, dtype=np.float64)
    t = np.asarray(t, dtype=np.float64)
    finite = np.isfinite(x) & np.isfinite(t)
    x = x[finite]
    tt = t[finite]
    if len(x) == 0:
        return [np.nan] * len(STAT_NAMES)
    slope = np.polyfit(tt, x, 1)[0] if len(x) > 1 and np.ptp(tt) > 0 else 0.0
    return [
        np.mean(x), np.std(x), np.min(x), np.max(x), np.median(x),
        np.quantile(x, 0.05), np.quantile(x, 0.95), x[-1], slope,
        np.sqrt(np.mean(x * x)),
    ]


def _run_target(w: pd.DataFrame) -> int:
    # FinalScientific v4.6.3 exports run_target_label and target on every row.
    for col in ("run_target_label", "target", "injected_fault_code", "requested_fault_code"):
        if col in w.columns:
            s = pd.to_numeric(w[col], errors="coerce").dropna()
            if len(s):
                return int(round(float(s.median())))
    # Last-resort fallback for older files.
    sensor = numeric_series(w, "sensor_fault_code", 0.0).fillna(0)
    fault = numeric_series(w, "fault_code", 0.0).fillna(0)
    if sensor.max() > 0:
        return int(round(float(sensor.max())))
    if fault.max() > 0:
        return int(round(float(fault.max())))
    return 0


def window_labels(w: pd.DataFrame) -> dict:
    """Conservative causal labels for final 19-class supervised/anomaly tasks."""
    run_target = _run_target(w)
    if run_target == 0:
        return {
            "class_label": 0,
            "anomaly_label": 0,
            "supervised_usable": 1,
            "run_target_label": 0,
            "fault_window_fraction": 0.0,
        }

    active_fraction = float(numeric_series(w, "fault_active", 0.0).fillna(0.0).mean())
    if active_fraction <= 0 and {"requested_fault_start_s", "requested_fault_end_s"}.issubset(w.columns):
        t = numeric_series(w, "time", np.nan)
        start = float(numeric_series(w, "requested_fault_start_s", np.nan).median())
        end = float(numeric_series(w, "requested_fault_end_s", np.nan).median())
        if np.isfinite(start) and np.isfinite(end):
            active_fraction = float(((t >= start) & (t <= end)).mean())

    active = active_fraction >= 0.5
    return {
        "class_label": int(run_target) if active else -1,
        "anomaly_label": int(active),
        "supervised_usable": int(active),
        "run_target_label": int(run_target),
        "fault_window_fraction": float(active_fraction),
    }


def windowize(df: pd.DataFrame, size: int | None = None, step: int | None = None) -> pd.DataFrame:
    size = int(size or CFG["window_seconds"])
    step = int(step or CFG["window_step_seconds"])
    d = enrich(df)
    if "time" not in d.columns:
        raise ValueError("Required column 'time' is missing.")
    if len(d) < size:
        return pd.DataFrame()

    rows = []
    for start in range(0, len(d) - size + 1, step):
        w = d.iloc[start:start + size]
        time_values = numeric_series(w, "time", np.nan)
        row = {}
        # Always emit 17 x 10 = 170 feature columns, even if one raw logger is absent.
        for column in SIGNALS:
            signal = numeric_series(w, column, np.nan)
            vals = _stats(signal, time_values)
            row.update({f"{column}__{name}": value for name, value in zip(STAT_NAMES, vals)})

        labels = window_labels(w)
        row.update(
            label=int(labels["class_label"]),
            class_label=int(labels["class_label"]),
            anomaly_label=int(labels["anomaly_label"]),
            supervised_usable=int(labels["supervised_usable"]),
            run_target_label=int(labels["run_target_label"]),
            fault_window_fraction=float(labels["fault_window_fraction"]),
            run_id=str(string_series(w, "run_id", "unknown").iloc[0]),
            scenario=str(string_series(w, "scenario", "unknown").iloc[0]),
            time_start=float(time_values.iloc[0]),
            time_end=float(time_values.iloc[-1]),
        )
        rows.append(row)

    result = pd.DataFrame(rows)
    feature_cols = [c for c in result.columns if "__" in c]
    if len(feature_cols) != 170:
        raise RuntimeError(f"Expected 170 engineered features; created {len(feature_cols)}.")
    result[feature_cols] = result[feature_cols].astype("float32")
    return result


def load_runs(run_dirs, size: int | None = None, step: int | None = None) -> pd.DataFrame:
    parts = []
    for run_dir in run_dirs:
        for csv_file in sorted(Path(run_dir).glob("*.csv")):
            # Only simulation-run files; QA/split/summary CSVs are intentionally excluded.
            if not csv_file.name.startswith("v463_sci1900_fc"):
                continue
            try:
                windows = windowize(pd.read_csv(csv_file), size=size, step=step)
                if windows.empty:
                    print(f"SKIP {csv_file.name}: shorter than one analysis window")
                    continue
                parts.append(windows)
            except Exception as exc:
                raise RuntimeError(f"Failed feature extraction for {csv_file}: {exc}") from exc
    if not parts:
        raise RuntimeError("No usable Scientific1900 run CSVs found.")
    result = pd.concat(parts, ignore_index=True)
    if "run_id" not in result.columns:
        raise RuntimeError("Window table is missing run_id.")
    return result
