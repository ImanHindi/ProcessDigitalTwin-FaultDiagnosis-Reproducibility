from __future__ import annotations
import argparse
from final19_common import build_or_load_feature_cache, feature_columns, manifest_summary, REPORT_DIR

p=argparse.ArgumentParser()
p.add_argument('--rebuild', action='store_true')
a=p.parse_args()

data=build_or_load_feature_cache(rebuild=a.rebuild)
features=feature_columns(data)
print('\nFeature cache QA')
print('  rows:       ', f'{len(data):,}')
print('  runs:       ', data.run_id.nunique())
print('  features:   ', len(features))
print('  supervised: ', int((data.supervised_usable==1).sum()))
print('  anomalies:  ', int((data.anomaly_label==1).sum()))
print('\nRun counts by locked partition/class:')
summary=manifest_summary(data)
print(summary.to_string(index=False))
summary.to_csv(REPORT_DIR/'final19_feature_cache_run_counts.csv', index=False)
(REPORT_DIR/'FINAL19_FEATURE_CACHE_READY.txt').write_text(
    f'rows={len(data)}\nruns={data.run_id.nunique()}\nfeatures={len(features)}\n', encoding='utf-8')
print('\n*** FINAL19 FEATURE CACHE READY ***')
