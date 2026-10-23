from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image
try:
    import tifffile
except Exception:
    tifffile=None

from final19_common import REPORT_DIR, FINAL_CODES

OUT=REPORT_DIR/'publication_figures_600dpi'
OUT.mkdir(parents=True,exist_ok=True)
DPI=600

CLASS_NAMES={
0:'Normal',1:'Production fill-pump degradation',2:'CIP supply-pump degradation',
3:'Production inlet valve blockage',4:'Tank inlet valve blockage',5:'Product discharge valve blockage',
6:'Product discharge valve leakage/stuck open',7:'Heating degradation',8:'Agitator degradation',
9:'CIP inlet valve blockage',10:'CIP return valve blockage',11:'Product discharge-pump degradation',
12:'CIP return-pump degradation',101:'Temperature sensor bias',102:'Level sensor bias',
103:'Production flow sensor scale',104:'Pressure sensor drift',105:'RPM excess noise',106:'Temperature sensor dropout'}

plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10.5,'axes.titlesize':13,'axes.labelsize':11.5,'pdf.fonttype':42})
created=[]; skipped=[]

def save(fig,stem,desc):
    png=OUT/f'{stem}.png'; pdf=OUT/f'{stem}.pdf'; svg=OUT/f'{stem}.svg'; tif=OUT/f'{stem}.tiff'
    fig.savefig(png,dpi=DPI,bbox_inches='tight',pad_inches=.08)
    fig.savefig(pdf,bbox_inches='tight',pad_inches=.08)
    fig.savefig(svg,bbox_inches='tight',pad_inches=.08)
    if tifffile is not None:
        with Image.open(png) as im:
            arr=np.asarray(im.convert('RGB'))
        tifffile.imwrite(tif,arr,photometric='rgb',resolution=(DPI,DPI),resolutionunit='INCH',metadata=None)
    plt.close(fig); created.append({'stem':stem,'description':desc})

def csv(name):
    p=REPORT_DIR/name
    return pd.read_csv(p) if p.exists() else None

def safe(stem,desc,fn):
    try:
        fig=fn()
        if fig is None:
            skipped.append({'stem':stem,'reason':'source report unavailable'}); return
        save(fig,stem,desc); print('CREATED',stem)
    except Exception as exc:
        skipped.append({'stem':stem,'reason':repr(exc)}); print('SKIPPED',stem,exc)

def fig_split():
    d=csv('run_split.csv')
    if d is None:return None
    p=d.groupby(['fault_code','partition']).size().unstack(fill_value=0).reindex(FINAL_CODES,fill_value=0)
    x=np.arange(len(p)); bottom=np.zeros(len(p)); fig,ax=plt.subplots(figsize=(9,5.5))
    for part in ['train','validation','test']:
        if part in p: ax.bar(x,p[part],bottom=bottom,label=part.title()); bottom+=p[part].to_numpy()
    ax.set_xticks(x);ax.set_xticklabels([str(c) for c in p.index],rotation=45,ha='right');ax.set_ylabel('Independent runs');ax.set_xlabel('Fault class code');ax.set_title('Locked run-level Scientific1900 partition');ax.legend(frameon=False);ax.grid(axis='y',alpha=.2);fig.tight_layout();return fig
safe('FigML01_locked_run_partition','Exactly 70/15/15 independent runs per final class.',fig_split)

def fig_models():
    d=csv('final19_locked_test_model_comparison.csv')
    if d is None:return None
    # Append LSTM when available.
    lp=REPORT_DIR/'lstm_metrics.json'
    if lp.exists():
        m=json.loads(lp.read_text()); d=pd.concat([d,pd.DataFrame([{'model':'lstm','accuracy':m.get('accuracy'),'balanced_accuracy':m.get('balanced_accuracy'),'macro_f1':m.get('macro_f1')}])],ignore_index=True)
    metrics=[('accuracy','Accuracy'),('balanced_accuracy','Balanced accuracy'),('macro_f1','Macro-F1')]
    x=np.arange(len(d));w=.22;fig,ax=plt.subplots(figsize=(10,5.7))
    for off,(col,label) in zip([-w,0,w],metrics): ax.bar(x+off,d[col],width=w,label=label)
    ax.set_xticks(x);ax.set_xticklabels(d.model.str.replace('_',' ').str.title(),rotation=25,ha='right');ax.set_ylim(0,1);ax.set_ylabel('Score');ax.set_title('Final19 performance on locked independent test runs');ax.legend(frameon=False);ax.grid(axis='y',alpha=.2);fig.tight_layout();return fig
safe('FigML02_final19_model_comparison','Baseline and enhanced classifier comparison on the locked test split.',fig_models)

def fig_cm():
    p=REPORT_DIR/'confusion_normalized_probability_ensemble.csv'
    if not p.exists():return None
    d=pd.read_csv(p,index_col=0);m=d.to_numpy(float);fig,ax=plt.subplots(figsize=(8.5,7.5));im=ax.imshow(m,vmin=0,vmax=1,aspect='equal');ax.set_xticks(range(len(d.columns)));ax.set_yticks(range(len(d.index)));ax.set_xticklabels(d.columns,rotation=90);ax.set_yticklabels(d.index);ax.set_xlabel('Predicted class');ax.set_ylabel('True class');ax.set_title('Probability Ensemble — normalized Final19 confusion matrix');fig.colorbar(im,ax=ax,label='Row-normalized fraction');fig.tight_layout();return fig
safe('FigML03_probability_ensemble_confusion','Row-normalized 19-class confusion matrix.',fig_cm)

def fig_f1():
    d=csv('final19_per_class_metrics.csv')
    if d is None:return None
    d=d[d.model.isin(['enhanced_xgboost','probability_ensemble'])]
    if d.empty:return None
    p=d.pivot(index='class_code',columns='model',values='f1').reindex(FINAL_CODES);x=np.arange(len(p));fig,ax=plt.subplots(figsize=(10,5.5))
    for col in p.columns:ax.plot(x,p[col],marker='o',label=col.replace('_',' ').title())
    ax.set_xticks(x);ax.set_xticklabels([str(c) for c in p.index],rotation=45,ha='right');ax.set_ylim(0,1.02);ax.set_ylabel('F1 score');ax.set_xlabel('Fault class code');ax.set_title('Class-wise Final19 diagnostic F1');ax.legend(frameon=False);ax.grid(axis='y',alpha=.2);fig.tight_layout();return fig
safe('FigML04_classwise_f1','Class-wise F1 for leading enhanced classifiers.',fig_f1)

def fig_prob():
    d=csv('final19_advanced_probability_metrics.csv')
    if d is None:return None
    x=np.arange(len(d));w=.32;fig,ax=plt.subplots(figsize=(9,5.4));ax.bar(x-w/2,d.macro_roc_auc_ovr,width=w,label='Macro ROC-AUC');ax.bar(x+w/2,d.macro_average_precision,width=w,label='Macro average precision');ax.set_xticks(x);ax.set_xticklabels(d.model.str.replace('_',' ').str.title(),rotation=25,ha='right');ax.set_ylim(0,1);ax.set_ylabel('Score');ax.set_title('Final19 probability-ranking quality');ax.legend(frameon=False);ax.grid(axis='y',alpha=.2);fig.tight_layout();return fig
safe('FigML05_probability_quality','Macro ROC-AUC and average precision.',fig_prob)

def fig_cal():
    d=csv('final19_calibration_bins.csv')
    if d is None:return None
    fig,ax=plt.subplots(figsize=(7,5.8));ax.plot([0,1],[0,1],'--',label='Ideal')
    for model in ['enhanced_xgboost','probability_ensemble']:
        p=d[d.model==model].sort_values('mean_confidence')
        if len(p):ax.plot(p.mean_confidence,p.accuracy,marker='o',label=model.replace('_',' ').title())
    ax.set_xlim(0,1);ax.set_ylim(0,1);ax.set_xlabel('Mean confidence');ax.set_ylabel('Observed accuracy');ax.set_title('Final19 reliability diagram');ax.legend(frameon=False);ax.grid(alpha=.2);fig.tight_layout();return fig
safe('FigML06_reliability','Reliability/calibration curve.',fig_cal)

def fig_severity():
    d=csv('final19_severity_stratified_performance.csv')
    if d is None or d.empty:return None
    x=np.arange(len(d));fig,ax=plt.subplots(figsize=(7,5.2))
    for c,l in [('accuracy','Accuracy'),('balanced_accuracy','Balanced accuracy'),('macro_f1','Macro-F1')]:ax.plot(x,d[c],marker='o',label=l)
    ax.set_xticks(x);ax.set_xticklabels(d.severity_band);ax.set_ylim(0,1);ax.set_ylabel('Score');ax.set_xlabel('Actuator-fault severity band');ax.set_title('Robustness across fault severity');ax.legend(frameon=False);ax.grid(axis='y',alpha=.2);fig.tight_layout();return fig
safe('FigML07_severity_robustness','Final19 ensemble performance across actuator-fault severity.',fig_severity)

def fig_mode():
    d=csv('final19_process_mode_performance.csv')
    if d is None or d.empty:return None
    d=d.sort_values('process_mode');fig,ax=plt.subplots(figsize=(8,5.2));ax.plot(d.process_mode,d.accuracy,marker='o',label='Accuracy');ax.plot(d.process_mode,d.macro_f1,marker='o',label='Macro-F1');ax.set_ylim(0,1);ax.set_xlabel('Process mode');ax.set_ylabel('Score');ax.set_title('Final19 diagnostic performance by process mode');ax.legend(frameon=False);ax.grid(axis='y',alpha=.2);fig.tight_layout();return fig
safe('FigML08_process_mode_robustness','Final19 ensemble performance by operating mode.',fig_mode)

def fig_delay():
    d=csv('final19_fault_detection_delay_by_run.csv')
    if d is None:return None
    v=np.sort(pd.to_numeric(d.loc[d.detected.astype(bool),'detection_delay_s'],errors='coerce').dropna().to_numpy())
    if not len(v):return None
    y=np.arange(1,len(v)+1)/len(v);fig,ax=plt.subplots(figsize=(7,5.4));ax.step(v,y,where='post');ax.axvline(np.median(v),linestyle='--',label=f'Median = {np.median(v):.0f} s');ax.set_ylim(0,1.02);ax.set_xlabel('First correct diagnostic delay (s)');ax.set_ylabel('Cumulative fraction of detected runs');ax.set_title('Final19 post-onset diagnostic delay');ax.legend(frameon=False);ax.grid(alpha=.2);fig.tight_layout();return fig
safe('FigML09_detection_delay_ecdf','Run-level empirical CDF of post-onset diagnostic delay.',fig_delay)

def fig_anomaly():
    d=csv('anomaly_model_comparison_test.csv')
    if d is None:return None
    x=np.arange(len(d));w=.22;fig,ax=plt.subplots(figsize=(10,5.5))
    for off,c,l in [(-w,'balanced_accuracy','Balanced accuracy'),(0,'macro_f1','Macro-F1'),(w,'fault_recall','Fault recall')]:ax.bar(x+off,d[c],width=w,label=l)
    ax.set_xticks(x);ax.set_xticklabels(d.model.str.replace('_',' ').str.title(),rotation=25,ha='right');ax.set_ylim(0,1);ax.set_ylabel('Score');ax.set_title('Healthy-only anomaly benchmark on locked test runs');ax.legend(frameon=False);ax.grid(axis='y',alpha=.2);fig.tight_layout();return fig
safe('FigML10_anomaly_benchmark','Healthy-only anomaly detector comparison.',fig_anomaly)

def fig_shap():
    d=csv('final19_xgboost_shap_importance.csv')
    if d is None:return None
    p=d.head(15).iloc[::-1];fig,ax=plt.subplots(figsize=(9.5,7));ax.barh(p.feature,p.mean_abs_shap);ax.set_xlabel('Mean |SHAP value|');ax.set_title('Final19 enhanced XGBoost global SHAP importance');ax.grid(axis='x',alpha=.2);fig.tight_layout();return fig
safe('FigML11_shap_importance','Top global SHAP features for enhanced XGBoost.',fig_shap)

pd.DataFrame(created).to_csv(OUT/'FIGURE_MANIFEST.csv',index=False)
pd.DataFrame(skipped).to_csv(OUT/'SKIPPED_FIGURES.csv',index=False)
print(f'Created {len(created)} Final19 publication figures in {OUT}')
if skipped:print(f'Skipped {len(skipped)} figures; see SKIPPED_FIGURES.csv')
