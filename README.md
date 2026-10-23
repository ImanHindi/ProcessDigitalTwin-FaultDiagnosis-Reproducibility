# AlKaseeh Process Digital Twin — Reproducible Multi-Fault Condition Monitoring

**Research software and evaluation evidence | Scientific1900 / Final19 | v1.1.0**

This repository documents a simulation-domain condition-monitoring framework for a multi-mode Jameed production process. It links physical and supervisory modelling in MATLAB/Simulink and Simscape Thermal Liquid with independent-run synthetic fault generation, causal 60-second feature engineering, fault diagnosis, one-class anomaly detection, and operator-facing Streamlit decision support.

The reproducible evaluation design contains **19 classes** (one normal, 12 process/actuator, six sensor faults), **1,900 independent 9,000-second simulation runs** (100 per class), and a frozen **70/15/15 run-level split**. Its modelling contract uses 17 signals and 10 statistics per signal (170 engineered features). Reported diagnostics should be interpreted as **simulation-domain evidence**; this repository does not claim factory calibration, live bidirectional synchronization, certified safety control, or remaining-useful-life prediction.

## What is included

| Component | Location | Availability |
|---|---|---|
| Final19 feature, split, model-training and inference scripts | `ml/` | Included |
| Validation-only selection, leakage/QA checks, interpretability and plotting scripts | `ml/` | Included |
| Frozen run assignments, campaign metadata and locked-test prediction/evaluation exports | `ml/reports/final19/` | Included |
| Code and reproducibility tests for these exports | `scripts/`, `tests/` | Included |
| Final physical model (v4.6.2) and matching MATLAB simulation scripts | `models/`, `matlab/` | Import from local source; builder checks exact accepted model and required scripts |
| Operator dashboard and serving integration | `dashboard/` | Import from the local project; builder requires genuine Python application source |
| Full 1,900-run time-series dataset, feature cache and trained neural/tree artifacts | Not stored in Git | External research archive required for a full rerun |

The included statistical exports support verification of the **reported Final19 test results** without downloading trained model binaries. Re-executing the complete simulation and training pipeline requires the original model, full trajectories, and an environment consistent with those used for the experiments. The local import utility adds eligible code without uploading heavyweight artifacts or developer-specific paths.

## Repository layout

```text
AlKaseeh-DigitalTwin-Reproducibility/
├── ml/
│   ├── config.json                    # Final19 frozen evaluation settings
│   ├── features.py                    # 1 Hz → causal 60 s / 170-feature contract
│   ├── final19_common.py              # locked split and campaign integrity
│   ├── train_final19_*.py             # supervised/deep anomaly training
│   ├── predict.py                     # diagnostic prediction
│   ├── validate_final19_artifacts.py  # class-code/selection/artifact QA
│   └── reports/final19/              # supplied published-study results
├── matlab/                           # MATLAB source added from local installation
├── models/                           # accepted physical .slx added from local installation
├── dashboard/                        # Streamlit UI added from local installation
├── scripts/
│   ├── verify_results.py             # independent evaluation evidence audit
│   ├── prepare_local_release.py      # safe local source-code assembly
│   ├── audit_public_release.py       # final privacy/size scan
│   └── write_checksums.py            # reproducibility checksums
├── tests/
├── docs/
└── environment.yml
```

## Installation

Use Python **3.11** in a separate environment for the included analysis scripts. MATLAB, Simulink and Simscape Thermal Liquid must be installed separately to execute the process model; the MATLAB release and toolbox versions used for the original study should be recorded with the archived model.

```bash
conda env create -f environment.yml
conda activate alkaseeh-final19
python scripts/verify_results.py
python scripts/verify_source_manifest.py
python -m unittest discover -s tests -v
```

A Python-only environment can instead be created using `pip install -r requirements.txt`. CPU training is possible but may be computationally intensive.

## Reproducing the published evaluation from archived outputs

The evaluation exports contain the actual held-out predictions, model-comparison tables, run partition, anomaly scores/predictions and campaign metadata. To check the 19-class protocol and recalculate metrics:

```bash
python scripts/verify_results.py --json
```

To regenerate publication figures from the frozen results:

```bash
cd ml
python generate_final19_publication_figures.py
```

The figure generator writes to `ml/reports/final19/publication_figures_600dpi/`. These generated raster/TIFF/PDF/SVG files are intentionally not tracked by Git.

## Full simulation and retraining reproduction

The original virtual plant and simulation data are **not** generated by this lightweight repository alone. A full reproduction uses the accepted physical model (**v4.6.2**) and the Final19 campaign layer (**v4.6.3**):

1. Verify a nominal 9,000-second cycle and its thermal-liquid property, mode, flow and CIP isolation checks.
2. Pass Smoke38 (two runs per class) and Development190 (ten runs per class) physical and fault-evidence gates.
3. Export Scientific1900 at 1 Hz, preserving independent run seeds, fault-onset fields, true state and measured channels.
4. Restore the released campaign files to `ml/data/final_scientific_v4_6_3/scientific1900/` and the original locked split and gate markers; **do not regenerate or reshuffle the published split**.
5. From the repository root, perform readiness checks and model training with the Final19 source scripts. See [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md) for the command sequence.
6. Validate 19-class model mappings and promote only validation-selected models, not test-selected models.

To incorporate the **final physical `.slx` model and source code** (but not trained machine-learning weights, raw datasets, passwords, or developer-specific paths):

```bash
python scripts/prepare_local_release.py --physical-root "PATH_TO_PHYSICAL_PROJECT" --scientific-root "PATH_TO_FINAL19_PROJECT" --output "PATH_TO_RELEASE_CANDIDATE"
python scripts/audit_public_release.py "PATH_TO_RELEASE_CANDIDATE"
```

The preparation tool creates an independent **release candidate** rather than altering the original experiment folders. It selects `AlKaseeh_PhysicalTwin_PM_FinalScientific_v4_6_2.slx` and only final-stage MATLAB sources, refusing to create a GitHub-ready ZIP unless the accepted model, required scripts, and HMI source are present. It reports excluded and conflicting files. See [`docs/FINAL_SOURCE_SELECTION.md`](docs/FINAL_SOURCE_SELECTION.md) and [`docs/RELEASE_PROCESS.md`](docs/RELEASE_PROCESS.md).

## Dataset, model artifacts and availability

The **complete raw time-series campaign** and **large trained model files** are not included here. The repository includes small traceable test evidence, but this is **not equivalent to full executable reproduction**. A separate archival deposit can hold the full 1,900 trajectories, original `.slx` and/or heavy inference artifacts together with the required environment and checksums. Link the archive to the software release after its identity and access rights are verified.

The archive DOI and GitHub release URL are deliberately **not fabricated**. See [`docs/DATA_AND_CODE_AVAILABILITY.md`](docs/DATA_AND_CODE_AVAILABILITY.md) for publication wording, the release manifest, and citation guidance.

## Scientific scope and responsible use

This is a digital-twin **research prototype** and offline/simulation advisory system. It does not replace independent plant safety systems, machine-protection logic, validated PLC controls, physical commissioning or professional maintenance judgments. No authentic factory telemetry is claimed in these published-study evaluation exports.

## Reproducibility documentation

- [Final accepted-model and source-selection audit](docs/FINAL_SOURCE_SELECTION.md)
- [Research design and control/model architecture](docs/ARCHITECTURE.md)
- [Independent-run protocol and class taxonomy](docs/PROTOCOL.md)
- [End-to-end reproduction procedure](docs/REPRODUCIBILITY.md)
- [Software/artifact availability statement](docs/DATA_AND_CODE_AVAILABILITY.md)
- [Known archived-report discrepancy](docs/KNOWN_DISCREPANCIES.md)
- [Public-release safety and attribution checklist](docs/RELEASE_PROCESS.md)

The frozen model-selection report and final locked-test exports are supplied as evidence of the original experimental run. Re-training can differ across hardware/software versions; rerun outputs must be labelled separately and must never silently overwrite the archived locked-test results.

## Final-source archive verification (v1.1.0)

The supplied Final19 retraining archive contains 43 files, including 36 ML source/configuration files. The 36 files in `ml/` match the retained public candidate exactly by SHA-256. This confirms the **Final19 patch code** has not been silently replaced by older scripts. The archive does **not** contain the accepted `.slx` physical model or the original Streamlit application. Full physical and HMI source completeness must therefore be established through the local release builder. See `docs/FINAL19_SOURCE_AUDIT.json`.
