# Reproducing the Final19 study

## Level A — independent verification of archived test exports

No trained model binaries or full trajectories are required for the following checks:

```bash
python scripts/verify_results.py --json
python -m unittest discover -s tests -v
cd ml && python generate_final19_publication_figures.py
```

`verify_results.py` recomputes accuracy, balanced accuracy, macro-F1 and counts from frozen test predictions; checks the 19 class IDs, locked 70/15/15 run distribution and independent-run partition; verifies diagnostic metrics against the archived comparison table; and checks selected healthy-only anomaly results. One archived result (mode-conditioned Isolation Forest) has a small, documented summary/prediction mismatch; see `KNOWN_DISCREPANCIES.md`. Minor floating-point differences are tolerated.

## Level B — rebuild features and retrain models

**Prerequisites:** 1,900 original scientific campaign CSVs at `ml/data/final_scientific_v4_6_3/scientific1900/`, saved locked split (`scientific1900_LOCKED_run_split.csv`) and validation/split marker files. Restored full data must have the original `v463_sci1900_fc*_rep*.csv` filenames and the published run IDs.

```bash
python ml/check_final19_training_readiness.py
python ml/build_final19_feature_cache.py
python ml/train_final19_supervised.py
python ml/train_enhanced_models.py
python ml/train_final19_lstm.py
python ml/train_final19_anomaly_baselines.py
python ml/train_final19_deep_anomaly.py
python ml/validate_final19_artifacts.py
```

The original Final19 scripts contain additional exploratory/optional analyses. Dependencies may include CPU/GPU PyTorch and XGBoost. The original `ml/config.json` and `ml/reports/final19/supervised_selection_lock.json` must remain immutable when comparing against the published benchmark. **Regenerated experiments should be written to a separate output directory or branch**, not over the archived test exports.

Readiness checks should fail rather than silently manufacture a new run split or accept only part of the scientific campaign. Some training scripts may require existing baseline artifacts created by earlier scripts; inspect the built-in CLI help and the original execution logs if a step cannot be reproduced directly.

## Level C — re-execute MATLAB/Simscape campaign

Restore the original accepted `.slx`, MATLAB simulation scripts, parameter configuration, required toolboxes and data export helpers from the research archive. The nominal-cycle physical QA should establish stage order, thermal-liquid property envelopes, four hydraulic paths, CIP interlocks and no product/CIP overlap. Run the 38-run and 190-run preproduction gates before requesting a full 1,900-run campaign.

No source-control snapshot, however complete, replaces external plant calibration or industrial validation. Keep the original hardware/toolbox provenance and accepted version identifiers in the archival research record.

## Level D — local Streamlit serving

Import the actual operator HMI and its supporting modules from the original local project. Reconstruct the original runtime; do not substitute demo predictions for trained-model inference. Check schema compatibility (17 raw signals → 170 features), 19-class order, calibration and validation-selected model loading. The interface reports advisories; it is not a certified safety system.
