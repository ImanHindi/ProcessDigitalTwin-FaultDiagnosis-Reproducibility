from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
from final19_common import REPORT_DIR
lines=['# FinalScientific v4.6.3 — Final19 Modeling Results','']
comp=REPORT_DIR/'final19_locked_test_model_comparison.csv'
if comp.exists():
 d=pd.read_csv(comp);lines+=['## Locked-test supervised comparison','','```text\n'+d.to_string(index=False)+'\n```','']
lstm=REPORT_DIR/'lstm_metrics.json'
if lstm.exists():lines+=['## LSTM locked-test metrics','',f'```json\n{lstm.read_text()}\n```','']
anom=REPORT_DIR/'anomaly_model_comparison_test.csv'
if anom.exists():lines+=['## Healthy-only anomaly benchmark — locked test','','```text\n'+pd.read_csv(anom).to_string(index=False)+'\n```','']
adv=REPORT_DIR/'final19_advanced_validation_summary.json'
if adv.exists():
 info=json.loads(adv.read_text());delay=info.get('fault_detection_delay',{});lines+=['## Diagnostic delay','',f"- Fault runs: {delay.get('n_fault_runs')}",f"- Eventually detected: {delay.get('fraction_eventually_detected')}",f"- Median delay (s): {delay.get('median_detection_delay_s')}",f"- <=60 s: {delay.get('detected_within_60s')}",f"- <=120 s: {delay.get('detected_within_120s')}",f"- <=300 s: {delay.get('detected_within_300s')}",'']
sh=REPORT_DIR/'final19_xgboost_shap_importance.csv'
if sh.exists():lines+=['## Top SHAP features','','```text\n'+pd.read_csv(sh).head(15).to_string(index=False)+'\n```','']
out=REPORT_DIR/'FINAL19_RESULTS_FOR_MANUSCRIPT.md';out.write_text('\n'.join(lines),encoding='utf-8');print('Saved',out)
