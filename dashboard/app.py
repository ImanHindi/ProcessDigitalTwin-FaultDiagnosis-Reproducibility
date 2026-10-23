from __future__ import annotations
from pathlib import Path
import json, sys
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'ml'));sys.path.insert(0,str(Path(__file__).resolve().parent))
from smooth_hmi import build_hmi_html,discharge_validation
from dashboard_utils import FAULT_NAMES,detection_summary,fault_name,normalize_schema,trend_figure
try:
    from predict import predict_csv
except Exception:
    predict_csv=None

st.set_page_config(page_title='Al Kaseeh Digital Twin Control Room',page_icon='🏭',layout='wide',initial_sidebar_state='expanded')
st.markdown('''<style>
:root{--navy:#0a1728;--ink:#172033;--muted:#65758a;--line:#d7e1ec;--bg:#f3f6fa}[data-testid="stAppViewContainer"]{background:var(--bg);color:var(--ink)}[data-testid="stHeader"]{background:rgba(243,246,250,.90)}[data-testid="stSidebar"]{background:var(--navy);border-right:1px solid #20364c}[data-testid="stSidebar"] label,[data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3,[data-testid="stSidebar"] p{color:#e8f0f8!important}[data-testid="stFileUploader"] section{background:#f8fafc!important;border:1px dashed #8fa3b7!important}[data-testid="stFileUploader"] section *,[data-testid="stFileUploader"] button,[data-testid="stFileUploader"] button *{color:#172033!important}[data-testid="stFileUploader"] button{background:#fff!important;border:1px solid #cbd6e2!important}[data-testid="stSidebar"] [data-baseweb="select"]>div{background:#f8fafc!important;border-color:#b9c7d5!important}[data-testid="stSidebar"] [data-baseweb="select"] *{color:#172033!important}[data-testid="stSidebar"] [data-testid="stAlert"]{background:#112b46!important;border:1px solid #234866!important}[data-testid="stSidebar"] [data-testid="stAlert"] *{color:#eaf2fa!important}.block-container{padding-top:.85rem;padding-bottom:2rem;max-width:1760px}.hero{background:linear-gradient(115deg,#09182a,#15385e);border:1px solid #234b70;border-radius:16px;padding:18px 24px;color:white;margin-bottom:12px;box-shadow:0 8px 24px rgba(15,37,62,.13)}.hero h1{font-size:1.72rem;margin:0 0 .25rem 0}.hero p{margin:0;color:#cbd9e8}.run-grid{display:grid;grid-template-columns:2fr 1fr 1fr 1fr;gap:10px;margin:8px 0 12px}.run-card,.equipment-card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px 14px;box-shadow:0 2px 8px rgba(25,45,70,.045)}.run-card .label{color:var(--muted);font-size:.76rem;text-transform:uppercase}.run-card .value{color:var(--ink);font-size:1.02rem;font-weight:700;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.equipment-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:12px}.equipment-card h4{margin:0 0 9px;color:#174b74}.equipment-card .row{display:flex;justify-content:space-between;gap:12px;margin-top:6px;color:#526274;font-size:.90rem}.equipment-card .row b{color:#172033}.section-note{background:#eef4f9;color:#43556a;border:1px solid #d5e1ec;border-radius:10px;padding:10px 12px;font-size:.90rem;margin:.4rem 0 .9rem}.model-badge{display:inline-block;padding:4px 9px;border-radius:999px;background:#e8f4f1;color:#146d59;border:1px solid #b7dfd5;font-size:.80rem;font-weight:700}[data-testid="stMetric"]{background:#fff;border:1px solid var(--line);border-radius:11px;padding:10px 12px}[data-testid="stMetricLabel"]{color:#607186!important}[data-testid="stMetricValue"]{color:#172033!important}.stTabs [data-baseweb="tab-list"]{gap:4px;border-bottom:1px solid #d5dfeb}.stTabs [data-baseweb="tab"]{color:#52657a;padding:.65rem .75rem}.stTabs [aria-selected="true"]{color:#123f63!important;border-bottom-color:#1f8f7a!important}@media(max-width:1100px){.run-grid,.equipment-grid{grid-template-columns:1fr 1fr}}
</style>''',unsafe_allow_html=True)
st.markdown('<div class="hero"><h1>Al Kaseeh Jameed Digital Twin · Condition Monitoring Control Room</h1><p>Physics-based process replay, equipment-state visualization, validated AI fault diagnosis, explainability and scientific evaluation.</p></div>',unsafe_allow_html=True)

@st.cache_data(show_spinner=False)
def read_run(path_string):return normalize_schema(pd.read_csv(path_string))
@st.cache_data(show_spinner=False)
def run_predictions(path_string,modified_ns):
    del modified_ns
    if predict_csv is None:return None
    try:return predict_csv(Path(path_string))
    except Exception as exc:return pd.DataFrame({'prediction_error':[str(exc)]})

runs=sorted((ROOT/'data'/'campaign_runs').glob('*.csv'))+sorted((ROOT/'data'/'runs').glob('*.csv'))
st.sidebar.markdown('### Run source');uploaded=st.sidebar.file_uploader('Upload a simulation CSV',type='csv')
if uploaded is not None:
    selected_path=ROOT/'data'/'_uploaded_dashboard.csv';selected_path.write_bytes(uploaded.getvalue());run_name=uploaded.name
else:
    if not runs:st.error('No CSV files were found in data/runs or data/campaign_runs.');st.stop()
    selected_path=st.sidebar.selectbox('Simulation run',runs,format_func=lambda p:p.stem.replace('_',' '));run_name=selected_path.name
st.sidebar.markdown('---');st.sidebar.info('Playback runs inside the browser HMI, so the Streamlit page does not rerun at every simulation step. Dynamic AI status is synchronized inside the same HMI.')
df=read_run(str(selected_path));
if df.empty:st.error('The selected CSV is empty.');st.stop()
predictions=run_predictions(str(selected_path),selected_path.stat().st_mtime_ns);prediction_error=None
if predictions is not None and 'prediction_error' in predictions:prediction_error=str(predictions['prediction_error'].iloc[0]);predictions=None
available=predictions is not None and not predictions.empty
primary='No trained classifier'
if available and 'primary_model' in predictions and len(predictions['primary_model'].dropna()):primary=str(predictions['primary_model'].dropna().iloc[-1])
scenario=str(df['scenario'].iloc[0]);run_id=str(df['run_id'].iloc[0]);duration=float(df['time'].max()-df['time'].min())
st.markdown(f'<div class="run-grid"><div class="run-card"><div class="label">Selected run</div><div class="value">{run_name}</div></div><div class="run-card"><div class="label">Scenario</div><div class="value">{scenario.replace("_"," ")}</div></div><div class="run-card"><div class="label">Duration</div><div class="value">{duration:.0f} s</div></div><div class="run-card"><div class="label">Primary AI</div><div class="value">{primary}</div></div></div>',unsafe_allow_html=True)
if prediction_error:st.warning(f'The run loaded, but model inference could not be completed: {prediction_error}')

tabs=st.tabs(['Control room','Sensors & trends','Faults & alarms','AI diagnosis','Explainability','Scientific validation','Data & reports'])
with tabs[0]:
    components.html(build_hmi_html(df,run_name,predictions),height=790,scrolling=False)
    st.markdown('<div class="section-note"><b>Interpretation.</b> The embedded HMI owns the playback clock and keeps process state, actual fault state and AI diagnosis synchronized without repeated Streamlit reruns. AI output is decision support only. A pre-onset indication is explicitly marked exploratory and is not claimed as validated prognosis or RUL.</div>',unsafe_allow_html=True)
    last=df.iloc[-1]
    st.markdown(f'<div class="equipment-grid"><div class="equipment-card"><h4>Production pump P-101</h4><div class="row"><span>Effective command</span><b>{last.get("effective_prod_flow_command_kg_s",0):.2f} kg/s</b></div><div class="row"><span>Measured flow</span><b>{last.get("production_mass_flow_measured_kg_s",np.nan):.2f} kg/s</b></div></div><div class="equipment-card"><h4>Steam heating</h4><div class="row"><span>Command</span><b>{last.get("cmd_steam",0):.0f}</b></div><div class="row"><span>Heat input</span><b>{last.get("effective_heat_flow_W",0)/1000:.1f} kW</b></div></div><div class="equipment-card"><h4>Agitator M-101</h4><div class="row"><span>Setpoint</span><b>{last.get("cmd_agitator_rpm",0):.1f} rpm</b></div><div class="row"><span>Measured</span><b>{last.get("agitator_speed_measured_rpm",np.nan):.1f} rpm</b></div></div><div class="equipment-card"><h4>Process condition</h4><div class="row"><span>Pressure</span><b>{last.get("gauge_pressure_measured_Pa",np.nan)/1000:.2f} kPa</b></div><div class="row"><span>Volume</span><b>{last.get("volume_m3",np.nan):.3f} m³</b></div></div></div>',unsafe_allow_html=True)
with tabs[1]:
    st.markdown('<div class="section-note">True signals are Simscape physical outputs. Measured signals include configured sensor noise and injected measurement faults. The trained models use the same canonical schema.</div>',unsafe_allow_html=True)
    l,r=st.columns(2)
    with l:
        st.plotly_chart(trend_figure(df,['level_true_m','level_measured_m'],'Tank level','Level (m)'),use_container_width=True);st.plotly_chart(trend_figure(df,['production_mass_flow_true_kg_s','production_mass_flow_measured_kg_s','effective_prod_flow_command_kg_s'],'Production flow','Mass flow (kg/s)'),use_container_width=True);st.plotly_chart(trend_figure(df,['gauge_pressure_true_Pa','gauge_pressure_measured_Pa'],'Tank gauge pressure','Pressure (Pa)'),use_container_width=True)
    with r:
        st.plotly_chart(trend_figure(df,['temperature_true_K','temperature_measured_K'],'Tank temperature','Temperature (K)'),use_container_width=True);st.plotly_chart(trend_figure(df,['agitator_speed_true_rpm','agitator_speed_measured_rpm','cmd_agitator_rpm'],'Agitator command and response','Speed (rpm)'),use_container_width=True);st.plotly_chart(trend_figure(df,['process_mode'],'Operating mode sequence','Mode code'),use_container_width=True)
with tabs[2]:
    st.subheader('Injected/actual fault timeline');timeline=df.copy();sensor_active=pd.Series(False,index=timeline.index);sensor_code=pd.to_numeric(timeline['sensor_fault_code'],errors='coerce').fillna(0)>0;start=pd.to_numeric(timeline.get('requested_fault_start_s',np.nan),errors='coerce');end=pd.to_numeric(timeline.get('requested_fault_end_s',np.nan),errors='coerce');sensor_active=sensor_code&((start.isna())|(timeline['time']>=start))&((end.isna())|(timeline['time']<=end));active=(pd.to_numeric(timeline['fault_active'],errors='coerce').fillna(0)>=.5)|sensor_active;events=timeline.loc[active,['time','fault_code','sensor_fault_code','fault_severity']].copy()
    if len(events):events['fault']=np.where(events['sensor_fault_code']>0,events['sensor_fault_code'],events['fault_code']).astype(int);events['fault_name']=events['fault'].map(lambda c:FAULT_NAMES.get(int(c),str(c)));st.dataframe(events.tail(500),use_container_width=True,hide_index=True)
    else:st.success('No actual/injected fault is active in this run.')
    qa=discharge_validation(df);(st.success if qa['status']=='pass' else st.warning if qa['status']=='review' else st.info)(qa['message'])
with tabs[3]:
    if not available:st.warning('No trained prediction is available. Copy the trained artifacts into ml/models and restart Streamlit.')
    else:
        summary=detection_summary(df,predictions);final_pred=int(predictions['primary_fault_code'].iloc[-1]);final_conf=float(predictions['primary_confidence'].iloc[-1]);top3=str(predictions['primary_top3'].iloc[-1]);a1,a2,a3,a4=st.columns(4);a1.metric('Primary model',primary);a2.metric('Latest predicted class',fault_name(final_pred));a3.metric('Latest confidence','—' if not np.isfinite(final_conf) else f'{final_conf:.1%}');a4.metric('Top-3 ranking',top3 or '—')
        st.markdown('<div class="section-note"><b>Model alignment.</b> The dashboard preferentially serves the validation-selected probability ensemble when available. Enhanced XGBoost remains visible because it achieved the best balanced accuracy. Isolation Forest is retained as an anomaly-detection baseline. When a validation-selected deep anomaly detector is available, the HMI displays it separately from the supervised fault classifier. The anomaly detector answers normal/abnormal; the probability ensemble or Enhanced XGBoost identifies the fault class.</div>',unsafe_allow_html=True)
        st.dataframe(pd.DataFrame([{'Event':'Actual fault begins','Time (s)':summary['actual_fault_start_s']},{'Event':'First high-confidence non-normal classifier indication','Time (s)':summary['classification_detection_s']},{'Event':'Post-onset delay (negative = exploratory pre-onset indication)','Time (s)':summary['classification_delay_s']}]),use_container_width=True,hide_index=True)
        cols=[c for c in ['probability_ensemble_fault_code','enhanced_xgboost_fault_code','xgboost_fault_code','random_forest_fault_code'] if c in predictions]
        if cols:
            fig=px.line(predictions,x='time_end',y=cols,title='Window-level supervised diagnosis');fig.update_layout(paper_bgcolor='#fff',plot_bgcolor='#fff',legend=dict(orientation='h',y=1.02,x=0));st.plotly_chart(fig,use_container_width=True)
        st.dataframe(predictions.tail(250),use_container_width=True,hide_index=True)
with tabs[4]:
    st.markdown('<div class="section-note">Feature importance and SHAP describe model behavior, not physical causality. They are used to identify dominant diagnostic information and observability limitations.</div>',unsafe_allow_html=True);ip=ROOT/'ml'/'reports'/'rf_feature_importance.csv'
    if ip.exists():
        imp=pd.read_csv(ip).head(25);fig=px.bar(imp.sort_values('importance'),x='importance',y='feature',orientation='h',title='Random Forest global feature importance');fig.update_layout(height=650,paper_bgcolor='#fff',plot_bgcolor='#fff');st.plotly_chart(fig,use_container_width=True)
    sp=ROOT/'ml'/'reports'/'xgboost_shap_summary.png';st.image(sp,caption='XGBoost SHAP summary',use_container_width=True) if sp.exists() else st.info('SHAP summary not found.')
with tabs[5]:
    st.markdown('<span class="model-badge">Leakage-controlled run-level validation</span>',unsafe_allow_html=True);mp=ROOT/'ml'/'reports'/'research_metrics.json'
    if mp.exists():
        m=json.loads(mp.read_text());st.success('Primary evaluation uses independent run-grouped partitions.') if m.get('scientifically_valid') else st.error('Leakage-prone split detected; do not use for publication.');rows=[{'model':n,**v} for n,v in m.get('metrics',{}).items()];st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True) if rows else None
    for title,name in [('Enhanced model comparison','enhanced_model_comparison.csv'),('Advanced probability metrics','advanced_probability_metrics.csv'),('Repeated grouped holdouts','repeated_grouped_holdout.csv'),('Window-length sensitivity','window_length_sensitivity.csv'),('Process-mode robustness','process_mode_performance.csv'),('Fault-severity robustness','severity_stratified_performance.csv')]:
        p=ROOT/'ml'/'reports'/name
        if p.exists():
            with st.expander(title):st.dataframe(pd.read_csv(p),use_container_width=True,hide_index=True)
with tabs[6]:
    st.subheader('Selected run');st.write(f'**File:** `{run_name}`');st.write(f'**Scenario:** {scenario} · **Run ID:** {run_id} · **Rows:** {len(df):,}');st.dataframe(df.tail(1000),use_container_width=True,hide_index=True);st.download_button('Download normalized CSV',df.to_csv(index=False),file_name=f'normalized_{run_name}',mime='text/csv');report={'file':run_name,'scenario':scenario,'run_id':run_id,'duration_s':duration,'primary_model':primary,'prediction_available':available,'process_qa':discharge_validation(df)};st.download_button('Download run diagnostic summary (JSON)',json.dumps(report,indent=2),file_name=f'diagnostic_summary_{Path(run_name).stem}.json',mime='application/json')
