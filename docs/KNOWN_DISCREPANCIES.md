# Known archived-report discrepancy

The supplied Final19 validation CSVs are preserved as experimental records, rather than silently altered to force agreement. Recomputing the held-out binary test metrics from `ml/reports/final19/anomaly_predictions_test.csv` gives **0.641872 balanced accuracy** and **0.658972 macro-F1** for the `mode_conditioned_isolation_forest_pred` column, while `anomaly_model_comparison_test.csv` reports **0.643393 balanced accuracy** and **0.660106 macro-F1** for the same named model.

The selected LSTM autoencoder and the VAE, DAE, CVAE and global Isolation Forest results reproduce the archived comparison table exactly. All supervised model top-1 accuracy, balanced accuracy and macro-F1 results reproduced from the held-out prediction export.

The mode-conditioned difference may arise from distinct exported model states or reporting populations, but the materials available here do not establish the cause. Therefore, the software audit does **not** certify exact equivalence for this one secondary result. The discrepancy should be resolved using the original locked evaluation run and promotion artifact before claiming full numerical reproducibility for that baseline.

Public-release redaction: developer-specific machine paths were removed from the artifact validation detail fields and one local training-metadata reference. All class IDs, model scores, run assignments and prediction exports were left unchanged.
