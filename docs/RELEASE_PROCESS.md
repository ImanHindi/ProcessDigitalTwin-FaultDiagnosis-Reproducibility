# Research software release process

A public research release consists of code, documented evaluation protocol, traceable results and explicit dependencies. **It should not include personal machine paths, credentials, unlicensed factory documentation, proprietary production data or large unreviewed model binaries.**

## Source assembly

The two experimental roots may have additional MATLAB/Simulink, HMI and campaign-export source files. Assemble an independent release candidate with:

```bash
python scripts/prepare_local_release.py --physical-root "PATH_TO_PHYSICAL_PROJECT" --scientific-root "PATH_TO_FINAL19_PROJECT" --output "PATH_TO_RELEASE_CANDIDATE"
```

The preparer accepts the project root or an outer archive directory, copies only allow-listed research code and a limited-size physical `.slx` snapshot, preserves already included Final19 scripts when local duplicates differ, excludes raw data and trained binary artifacts, and logs all skipped or conflicting files to `release_import_report.json`. Text source carrying personal paths, e-mail addresses, or apparent secrets is excluded rather than silently rewritten into potentially broken code.

## Public safety audit

```bash
python scripts/audit_public_release.py "PATH_TO_RELEASE_CANDIDATE"
```

A release audit checks for possible personal identifiers, high-risk tokens, oversized files, archives, and common data/model binary patterns. A passing automated scan does not replace manual rights and privacy review. The preparer does not create a remote GitHub repository or push files.

## Citation and archival release

A software release can be tagged `v1.0.0` and archived via Zenodo's GitHub release integration. This produces an independently resolvable DOI after publication, not before. The DOI for a large raw-data deposit may differ from the source-code DOI. Before journal submission, verify that the DOI resolves to the **AlKaseeh** dataset/software, not a different research project, and insert the correct permanent URLs in the manuscript.

## Intellectual property and safety

A repository license must reflect ownership of source files and any industrial collaboration conditions. MATLAB/Simscape models may embed simulation data, block references and external component metadata; review them before public release. No claim of official factory endorsement or production readiness is implied.
