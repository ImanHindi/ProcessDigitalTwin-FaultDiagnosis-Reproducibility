# Final research-source selection and release verification

The uploaded **Final19 ML Retraining Package** is a patch archive, not the complete MATLAB/Simscape/Streamlit research project. The original and newly supplied copies of this archive have identical SHA-256 checksums. Its **36 `ml/` source/configuration files match the 36 included GitHub candidate files byte-for-byte**. The audit covers `config.json`, feature engineering, locked-split readiness, supervised classifiers, deep anomaly training, inference, promotion, QA, interpretation and figure generation.

The archived README explicitly identifies the **accepted physical plant model** as:

`models/AlKaseeh_PhysicalTwin_PM_FinalScientific_v4_6_2.slx`

The subsequent **v4.6.3** label denotes the Scientific1900 fault/sensor/campaign and machine-learning layer. A similarly named earlier `.slx` file is not interchangeable with the accepted v4.6.2 model. A code snapshot alone cannot demonstrate that the plant model successfully executed; physical QA should be re-run in the declared MATLAB runtime.

## Final source roster

| Source component | Public release expectation | Source status in this downloadable candidate |
|---|---|---|
| Final19 `ml/` files (36) | Exact copies of authoritative retraining archive | Included and SHA-256 verified |
| Frozen locked-test reports and predictions | Included for independent statistical verification | Included |
| Accepted v4.6.2 `.slx` plant | One exact file, not all historical `.slx` variants | Not supplied in retraining archive; to import locally |
| v4.6.2 production/CIP controller | Final version rather than historical controller patch sequence | To import from local physical source tree |
| v4.6.3 Scientific1900 run script | Production campaign entry point | To import from local physical source tree |
| v4.6.3 Scientific1900 QA script | Simulation acceptance test | To import from local physical source tree |
| v4.6.3 frozen split creator | Preserve published run assignments | To import from local physical source tree |
| v4.6.2 nominal-cycle validator | Physical-model acceptance evidence | To import from local physical source tree |
| Streamlit source code | Real application (no demonstration stubs) | To import from local project |
| Full 1,900 trajectories and trained artifacts | Large research archive rather than Git history | External deposit required |

The release builder imports only the accepted `models/...v4_6_2.slx` file, relevant v4.6.2/v4.6.3 MATLAB code, required common simulator helpers, and Streamlit source; it excludes older model variants, development patches, `_backups`, `slprj`, generated runs, caches and trained model binaries. Files containing detected developer paths or sensitive strings are excluded. No original source is modified.

The builder produces a `docs/SOURCE_COMPLETENESS.json` file that records whether the required source files actually made it into the locally built release. It refuses to produce a GitHub-ready ZIP if the accepted `.slx`, any of the mandatory MATLAB source files, or Streamlit Python source is missing. The external local import report documents excluded/conflicting source files and must not be uploaded.

Use `python scripts/verify_source_manifest.py` to validate the retained Final19 source against the manifest. This is a **source-integrity check**, not a replacement for running the full physical simulator and training scripts.

## Observed scope

The full contents of the pictured local Windows folder are not supplied as machine-readable files in the lightweight retraining archive. Their filenames are visible in the user-supplied screenshots, but their content and exact runtime dependencies cannot be fully audited until a local release candidate is built and executed. A complete validated pipeline should preserve a MATLAB/Simscape version/toolbox manifest and the 1,900-run source dataset in a separately citable archival deposit.
