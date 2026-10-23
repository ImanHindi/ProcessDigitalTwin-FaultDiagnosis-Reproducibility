# Release history

## v1.1.0 — Final19 source-integrity and physical-source selection

- Verified the attached v4.6.3 Final19 retraining archive is identical to the earlier uploaded archive and matched all 36 ML source/configuration files with the public candidate via SHA-256.
- Added a permanent SHA-256 source manifest and `verify_source_manifest.py`.
- Confirmed the accepted physical model identifier is `AlKaseeh_PhysicalTwin_PM_FinalScientific_v4_6_2.slx`.
- Restricted local import to the accepted Simulink model, relevant final MATLAB source, and dashboard code, rather than all historical model copies and patches.
- Added a required-file completeness gate and audit report before creating a GitHub-ready ZIP.
- Kept raw training runs, heavyweight models and other generated files out of Git.

## v1.0.0 — Archived evaluation evidence and initial research-code release candidate

- Included Final19 training scripts, frozen benchmark evaluation exports, research documentation, environment requirements, and privacy audit tools.
