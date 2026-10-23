from __future__ import annotations
import json, math
import numpy as np
import pandas as pd

MODES={0:'Idle',1:'Production filling',2:'Heating and mixing',3:'Temperature holding',4:'Product discharge',5:'CIP circulation',6:'CIP drain',7:'PROCESS HOLD · CIP inhibited'}
FAULTS={0:'Normal operation',1:'Production pump degradation',2:'CIP pump degradation',3:'Production inlet valve blockage',4:'Tank inlet valve blockage',5:'Discharge valve blockage',6:'Discharge valve leakage',7:'Steam heating degradation',8:'Agitator degradation',9:'CIP inlet blockage',10:'CIP return blockage',101:'Temperature sensor bias',102:'Level sensor bias',103:'Flow sensor scale error',104:'Pressure sensor drift',105:'RPM sensor excessive noise',106:'Temperature sensor dropout'}

def _num(v,d=0.0):
    try:
        x=float(v); return x if math.isfinite(x) else d
    except Exception:return d

def discharge_validation(df,target=0.20,tolerance=0.03):
    """Audit discharge completion and CIP entry permissive for the HMI."""
    mode = pd.to_numeric(
        df.get('process_mode', pd.Series(0, index=df.index)),
        errors='coerce'
    ).round()

    level = pd.to_numeric(
        df.get('level_measured_m', pd.Series(np.nan, index=df.index)),
        errors='coerce'
    )

    discharge = mode == 4
    cip = mode.isin([5,6])

    if not discharge.any():
        return {
            'status':'missing',
            'message':'No product-discharge interval was found in this run.',
            'unsafe_cip_start':False,
            'cip_start_level_m':np.nan,
        }

    s = level[discharge].dropna()
    if s.empty:
        return {
            'status':'missing',
            'message':'Discharge interval has no valid level measurement.',
            'unsafe_cip_start':False,
            'cip_start_level_m':np.nan,
        }

    minimum = float(s.min())
    permitted = target + tolerance

    cip_start_level = np.nan
    unsafe = False

    if cip.any():
        first = df.index[cip][0]
        if pd.notna(level.loc[first]):
            cip_start_level = float(level.loc[first])
            unsafe = cip_start_level > permitted

    if unsafe:
        return {
            'status':'critical',
            'minimum_level_m':minimum,
            'target_m':target,
            'unsafe_cip_start':True,
            'cip_start_level_m':cip_start_level,
            'message':(
                f'PROCESS SAFETY: CIP began at tank level '
                f'{cip_start_level:.3f} m before the discharge permissive '
                f'({permitted:.2f} m) was satisfied. Residual Jameed would '
                f'be exposed to CIP fluid. Use the CIP-safe controller and '
                f'correct the discharge hydraulics.'
            ),
        }

    passed = minimum <= permitted

    return {
        'status':'pass' if passed else 'review',
        'minimum_level_m':minimum,
        'target_m':target,
        'unsafe_cip_start':False,
        'cip_start_level_m':cip_start_level,
        'message':(
            f'Discharge permissive reached; minimum measured level '
            f'{minimum:.3f} m.'
            if passed
            else
            f'Process-model QA: discharge minimum {minimum:.3f} m; '
            f'configured target {target:.2f} m. CIP must remain inhibited '
            f'until the empty permissive is satisfied.'
        ),
    }

def _merge_predictions(df,predictions):
    """Synchronize raw process samples with window-level AI predictions.

    pandas.merge_asof requires the left and right merge keys to have exactly
    the same dtype. Campaign CSVs can store whole-second time as int64 while
    feature-window predictions store time_end as float64. Both keys are
    therefore normalized explicitly to float64 before sorting and merging.
    """
    d = df.copy()

    if 'time' not in d.columns:
        raise ValueError("Process dataframe is missing required 'time' column.")

    d['time'] = pd.to_numeric(d['time'], errors='coerce').astype('float64')
    d = d.dropna(subset=['time']).sort_values('time').reset_index(drop=True)

    defaults = [
        ('primary_fault_code', 0),
        ('primary_confidence', np.nan),
        ('primary_model', 'No trained classifier'),
        ('primary_top3', ''),
        ('global_is_anomaly', 0),
        ('mode_is_anomaly', 0),
        ('advanced_is_anomaly', 0),
        ('advanced_anomaly_score', np.nan),
        ('advanced_anomaly_model', ''),
    ]

    if predictions is None or predictions.empty:
        for c, v in defaults:
            d[c] = v
        return d

    p = predictions.copy()

    if 'time_end' not in p.columns:
        for c, v in defaults:
            d[c] = v
        return d

    # Critical compatibility fix: force BOTH merge keys to float64.
    p['time_end'] = pd.to_numeric(p['time_end'], errors='coerce').astype('float64')
    p = p.dropna(subset=['time_end']).sort_values('time_end').reset_index(drop=True)

    if p.empty:
        for c, v in defaults:
            d[c] = v
        return d

    wanted = [
        'time_end',
        'primary_fault_code',
        'primary_confidence',
        'primary_model',
        'primary_top3',
        'global_is_anomaly',
        'mode_is_anomaly',
        'advanced_is_anomaly',
        'advanced_anomaly_score',
        'advanced_anomaly_model',
    ]

    text_columns = {
        'primary_model',
        'primary_top3',
        'advanced_anomaly_model',
    }

    for c in wanted:
        if c not in p.columns:
            p[c] = '' if c in text_columns else np.nan

    # merge_asof also requires sorted keys.
    d = pd.merge_asof(
        d,
        p[wanted],
        left_on='time',
        right_on='time_end',
        direction='backward',
        allow_exact_matches=True,
    )

    d['primary_fault_code'] = (
        pd.to_numeric(d['primary_fault_code'], errors='coerce')
        .fillna(0)
        .astype(int)
    )
    d['primary_confidence'] = pd.to_numeric(
        d['primary_confidence'], errors='coerce'
    )
    d['primary_model'] = d['primary_model'].fillna('No prediction yet')
    d['primary_top3'] = d['primary_top3'].fillna('')

    for c in ('global_is_anomaly', 'mode_is_anomaly', 'advanced_is_anomaly'):
        d[c] = (
            pd.to_numeric(d[c], errors='coerce')
            .fillna(0)
            .astype(int)
        )

    d['advanced_anomaly_score'] = pd.to_numeric(
        d['advanced_anomaly_score'], errors='coerce'
    )
    d['advanced_anomaly_model'] = d['advanced_anomaly_model'].fillna('')

    return d

def _records(df,predictions,max_points=2600):
    d=_merge_predictions(df,predictions)
    if len(d)>max_points:
        idx=np.linspace(0,len(d)-1,max_points).round().astype(int);d=d.iloc[np.unique(idx)].reset_index(drop=True)
    nums=['time','process_mode','level_measured_m','volume_m3','temperature_measured_K','gauge_pressure_measured_Pa','production_mass_flow_measured_kg_s','agitator_speed_measured_rpm','cmd_agitator_rpm','cmd_steam','effective_heat_flow_W','cmd_prod_flow','cmd_cip_flow','prod_inlet_actual_pct','tank_inlet_actual_pct','discharge_actual_pct','cip_inlet_actual_pct','cip_return_actual_pct','fault_active','fault_code','sensor_fault_code','requested_fault_start_s','requested_fault_end_s','primary_fault_code','primary_confidence','global_is_anomaly','mode_is_anomaly','advanced_is_anomaly','advanced_anomaly_score','advanced_anomaly_model']
    out=[]
    for _,r in d.iterrows():
        item={c:_num(r.get(c,0),0) for c in nums};item['primary_model']=str(r.get('primary_model','No prediction yet'));item['primary_top3']=str(r.get('primary_top3',''));item['advanced_anomaly_model']=str(r.get('advanced_anomaly_model',''));out.append(item)
    return out

def build_hmi_html(df,run_name,predictions=None,confidence_threshold=0.55):
    rec=_records(df,predictions); data=json.dumps(rec,separators=(',',':')); modes=json.dumps(MODES); faults=json.dumps(FAULTS); val=discharge_validation(df); qac='qa-pass' if val['status']=='pass' else ('qa-critical' if val['status']=='critical' else 'qa-review'); mx=max(0,len(rec)-1)
    template='''<!doctype html><html><head><meta charset="utf-8"><style>
:root{--bg:#07111f;--panel:#0d1d30;--panel2:#11263d;--border:#29455f;--text:#edf4fb;--muted:#9db0c4;--pipe:#4c7ea7;--active:#2fc7a0;--product:#caa35e;--steam:#e77a45;--alarm:#e15d5d;--advisory:#e7b547;--normal:#2fc790;--cyan:#58b8d8}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,Segoe UI,Arial,sans-serif}.wrap{border:1px solid var(--border);border-radius:16px;overflow:hidden;background:linear-gradient(145deg,#07111f,#0d2034);box-shadow:0 14px 32px rgba(0,0,0,.18)}.top{display:grid;grid-template-columns:1.7fr repeat(5,1fr);gap:9px;padding:12px;background:#09182a;border-bottom:1px solid var(--border)}.k{background:var(--panel2);border:1px solid #31516f;border-radius:10px;padding:9px 11px;min-width:0}.k small{color:var(--muted);font-size:11px}.k b{display:block;font-size:18px;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}svg{width:100%;height:535px;display:block}.pipe{stroke:var(--pipe);stroke-width:8;fill:none;stroke-linecap:round}.pipe.on{stroke:var(--active);filter:drop-shadow(0 0 4px rgba(47,199,160,.42))}.cip{stroke:#5e7186;stroke-width:7}.cip.on{stroke:var(--cyan)}.eq{fill:#10243a;stroke:#a9bdd0;stroke-width:2.2}.txt{fill:var(--text);font-size:12px}.muted{fill:var(--muted);font-size:10px}.title{fill:var(--text);font-size:13px;font-weight:700}.liquid{fill:var(--product);transition:y .08s linear,height .08s linear}.valve{fill:#52667b;stroke:#dbe6f1;stroke-width:1.2}.valve.on{fill:var(--active)}.motor{fill:#52667b;stroke:#dbe6f1;stroke-width:2}.motor.on{fill:var(--active)}.heater{fill:#52667b;stroke:#dbe6f1;stroke-width:2}.heater.on{fill:var(--steam)}.beacon{fill:var(--normal);stroke:#fff;stroke-width:2}.beacon.advisory{fill:var(--advisory)}.beacon.alarm{fill:var(--alarm);animation:pulse 1.05s infinite}@keyframes pulse{50%{opacity:.55}}.ai-box{fill:#0b1a2b;stroke:#355674;stroke-width:1.5}.controls{display:grid;grid-template-columns:auto auto 1fr auto;gap:10px;align-items:center;padding:11px 14px;background:#09182a;border-top:1px solid var(--border)}button,select{background:#173550;color:#f6fbff;border:1px solid #416784;border-radius:8px;padding:8px 13px;font-weight:700}button:hover{background:#1c4465}input[type=range]{width:100%;accent-color:var(--active)}.footer{display:grid;grid-template-columns:1fr auto;gap:12px;padding:9px 14px 12px;background:#09182a}.qa{padding:8px 11px;border-radius:8px;font-size:12px}.qa-pass{background:#0f3027;border:1px solid #2c8b6b;color:#d9f7ea}.qa-review{background:#302718;border:1px solid #9b783a;color:#fae9c4}.qa-critical{background:#3a1719;border:1px solid #b94d55;color:#ffe5e7}.disclaimer{color:#9fb0c2;font-size:11px;text-align:right;align-self:center}
</style></head><body><div class="wrap"><div class="top"><div class="k"><small>Selected run</small><b>__RUN__</b></div><div class="k"><small>Time</small><b id="kt">0.0 s</b></div><div class="k"><small>Mode</small><b id="km">—</b></div><div class="k"><small>Level</small><b id="kl">—</b></div><div class="k"><small>Temperature</small><b id="ktemp">—</b></div><div class="k"><small>Status</small><b id="ka">NORMAL</b></div></div>
<svg viewBox="0 0 1500 535"><path id="p1" class="pipe" d="M40 185 H320"/><circle id="pump" class="eq" cx="365" cy="185" r="43"/><path id="p2" class="pipe" d="M408 185 H610"/><text class="title" x="365" y="180" text-anchor="middle">P-101</text><text class="txt" x="365" y="198" text-anchor="middle">PROD PUMP</text><text id="flow" class="muted" x="365" y="242" text-anchor="middle">0.00 kg/s</text>
<path id="vin" class="valve" d="M475 169 L497 185 L475 201 Z M519 169 L497 185 L519 201 Z"/><text class="muted" x="497" y="151" text-anchor="middle">V-IN</text><text id="vinp" class="txt" x="497" y="164" text-anchor="middle">0%</text><path id="vtk" class="valve" d="M545 169 L567 185 L545 201 Z M589 169 L567 185 L589 201 Z"/><text class="muted" x="567" y="151" text-anchor="middle">V-TK1</text><text id="vtkp" class="txt" x="567" y="164" text-anchor="middle">0%</text>
<rect class="eq" x="610" y="120" width="300" height="330" rx="7"/><rect id="liq" class="liquid" x="622" y="438" width="276" height="4" rx="2"/><text class="title" x="626" y="108">TK1 · JAMEED MIXING TANK</text><circle id="motor" class="motor" cx="760" cy="77" r="36"/><text class="txt" x="760" y="73" text-anchor="middle">M-101</text><text id="rpm" class="txt" x="760" y="89" text-anchor="middle">0.0 rpm</text><line x1="760" y1="113" x2="760" y2="368" stroke="#eaf1f8" stroke-width="4"/><line x1="711" y1="368" x2="809" y2="368" stroke="#eaf1f8" stroke-width="7"/><rect x="665" y="260" width="190" height="104" rx="7" fill="rgba(4,12,23,.76)" stroke="#708ba5"/><text id="tv" class="txt" x="760" y="285" text-anchor="middle"></text>
<path id="vout" class="valve" d="M925 169 L947 185 L925 201 Z M969 169 L947 185 L969 201 Z"/><text class="muted" x="947" y="151" text-anchor="middle">V-OUT</text><text id="voutp" class="txt" x="947" y="164" text-anchor="middle">0%</text><rect id="heater" class="heater" x="985" y="160" width="145" height="88" rx="7"/><text class="title" x="1057" y="192" text-anchor="middle">STEAM HEAT</text><text id="heat" class="txt" x="1057" y="215" text-anchor="middle">0 kW</text><path id="out" class="pipe" d="M910 410 H1348"/><rect class="eq" x="1348" y="365" width="132" height="90" rx="7"/><text class="title" x="1414" y="414" text-anchor="middle">FILLING LINE</text>
<rect class="eq" x="52" y="430" width="174" height="72" rx="7"/><text class="title" x="139" y="470" text-anchor="middle">CIP SKID</text><path id="cip1" class="pipe cip" d="M226 466 H610"/><path id="cip2" class="pipe cip" d="M910 466 H1308"/><path id="cipin" class="valve" d="M477 450 L499 466 L477 482 Z M521 450 L499 466 L521 482 Z"/><text class="muted" x="499" y="432" text-anchor="middle">CIP-IN</text><text id="cipinp" class="txt" x="499" y="445" text-anchor="middle">0%</text><path id="cipret" class="valve" d="M1090 450 L1112 466 L1090 482 Z M1134 450 L1112 466 L1134 482 Z"/><text class="muted" x="1112" y="432" text-anchor="middle">CIP-RET</text><text id="cipretp" class="txt" x="1112" y="445" text-anchor="middle">0%</text>
<circle id="beacon" class="beacon" cx="1410" cy="82" r="33"/><text id="bl" class="title" x="1410" y="135" text-anchor="middle">NORMAL</text><rect class="ai-box" x="1040" y="28" width="300" height="104" rx="8"/><text class="muted" x="1055" y="48">AI DECISION SUPPORT</text><text id="aimodel" class="txt" x="1055" y="68">Model: —</text><text id="aipred" class="txt" x="1055" y="88">Prediction: —</text><text id="aiconf" class="txt" x="1055" y="108">Confidence: —</text><text id="anom" class="muted" x="1055" y="125">Anomaly baseline: —</text><text id="msg" class="txt" x="1030" y="154">No active fault</text></svg>
<div class="controls"><button id="play">▶ Play</button><button id="reset">↺ Reset</button><input id="timeline" type="range" min="0" max="__MAX__" value="0"><select id="speed"><option value="1">1×</option><option value="2">2×</option><option value="5" selected>5×</option><option value="10">10×</option><option value="20">20×</option></select></div><div class="footer"><div class="qa __QAC__"><b>Process-model QA:</b> __QAMSG__</div><div class="disclaimer">AI output is diagnostic decision support, not a safety interlock or validated RUL/prognostic estimate.</div></div></div>
<script>const D=__DATA__,M=__MODES__,F=__FAULTS__,TH=__TH__,UNSAFE_CIP=__UNSAFE_CIP__,CIP_ENTRY_LEVEL=__CIP_ENTRY_LEVEL__;let i=0,playing=false,timer=null;const e=id=>document.getElementById(id),fmt=(v,n=2)=>Number.isFinite(v)?v.toFixed(n):'—',on=(id,v)=>e(id).classList.toggle('on',!!v),vp=(id,v)=>e(id).classList.toggle('on',v>1);function sensorActive(d){const c=Math.round(d.sensor_fault_code||0),s=d.requested_fault_start_s,en=d.requested_fault_end_s;if(c<=0)return false;if(Number.isFinite(s)&&Number.isFinite(en))return d.time>=s&&d.time<=en;if(Number.isFinite(s))return d.time>=s;return d.fault_active>=.5}function update(n){i=Math.max(0,Math.min(D.length-1,n));const d=D[i],frac=Math.max(0,Math.min(1,d.level_measured_m/1.61)),h=306*frac,y=442-h,sActive=sensorActive(d),actual=d.fault_active>=.5||sActive,actualCode=sActive?Math.round(d.sensor_fault_code||0):Math.round(d.fault_code||0),predCode=Math.round(d.primary_fault_code||0),conf=Number.isFinite(d.primary_confidence)?d.primary_confidence:NaN,ai=predCode!==0&&Number.isFinite(conf)&&conf>=TH;let status='NORMAL',message='No active fault; no high-confidence AI indication',cls='beacon';const mode=Math.round(d.process_mode||0),processHold=mode===7,unsafeLegacyCIP=UNSAFE_CIP&&(mode===5||mode===6);if(processHold){status='PROCESS HOLD';message='CIP inhibited: discharge/sequence permissive was not satisfied';cls='beacon alarm'}else if(unsafeLegacyCIP){status='PROCESS SAFETY';message='Unsafe recorded CIP entry: residual tank level '+CIP_ENTRY_LEVEL.toFixed(3)+' m';cls='beacon alarm'}else if(actual){status='ALARM';message='Actual/injected fault active: '+(F[actualCode]||('Fault '+actualCode));cls='beacon alarm'}else if(ai){status='ADVISORY';const st=d.requested_fault_start_s;if(Number.isFinite(st)&&d.time<st)message='Pre-onset AI indication (exploratory): '+(F[predCode]||('Fault '+predCode));else message='AI diagnostic indication: '+(F[predCode]||('Fault '+predCode));cls='beacon advisory'}e('liq').setAttribute('y',y);e('liq').setAttribute('height',Math.max(4,h));e('kt').textContent=fmt(d.time,1)+' s';e('km').textContent=M[Math.round(d.process_mode)]||('Mode '+Math.round(d.process_mode));e('kl').textContent=fmt(d.level_measured_m,3)+' m';e('ktemp').textContent=fmt(d.temperature_measured_K,2)+' K';e('ka').textContent=status;e('flow').textContent=fmt(d.production_mass_flow_measured_kg_s,2)+' kg/s';e('rpm').textContent=fmt(d.agitator_speed_measured_rpm,1)+' rpm';e('heat').textContent=fmt(d.effective_heat_flow_W/1000,0)+' kW';e('tv').innerHTML='<tspan x="760" dy="0">Level '+fmt(d.level_measured_m,3)+' m</tspan><tspan x="760" dy="21">Volume '+fmt(d.volume_m3,3)+' m³</tspan><tspan x="760" dy="21">Temp '+fmt(d.temperature_measured_K,2)+' K</tspan><tspan x="760" dy="21">Pressure '+fmt(d.gauge_pressure_measured_Pa/1000,2)+' kPa</tspan>';on('p1',d.cmd_prod_flow>.5);on('p2',d.cmd_prod_flow>.5);on('out',d.discharge_actual_pct>1);on('cip1',d.cmd_cip_flow>.5);on('cip2',d.cmd_cip_flow>.5);on('motor',d.cmd_agitator_rpm>1);on('heater',d.cmd_steam>.5);vp('vin',d.prod_inlet_actual_pct);vp('vtk',d.tank_inlet_actual_pct);vp('vout',d.discharge_actual_pct);vp('cipin',d.cip_inlet_actual_pct);vp('cipret',d.cip_return_actual_pct);e('vinp').textContent=fmt(d.prod_inlet_actual_pct,0)+'%';e('vtkp').textContent=fmt(d.tank_inlet_actual_pct,0)+'%';e('voutp').textContent=fmt(d.discharge_actual_pct,0)+'%';e('cipinp').textContent=fmt(d.cip_inlet_actual_pct,0)+'%';e('cipretp').textContent=fmt(d.cip_return_actual_pct,0)+'%';e('beacon').setAttribute('class',cls);e('bl').textContent=status;e('msg').textContent=message;e('aimodel').textContent='Model: '+(d.primary_model||'—');e('aipred').textContent='Prediction: '+(predCode===0?'Normal':(F[predCode]||('Fault '+predCode)));e('aiconf').textContent='Confidence: '+(Number.isFinite(conf)?(100*conf).toFixed(1)+'%':'—');const hasDeep=(d.advanced_anomaly_model||'').length>0,af=hasDeep?d.advanced_is_anomaly>=.5:(d.mode_is_anomaly>=.5||d.global_is_anomaly>=.5);e('anom').textContent=hasDeep?('Anomaly detector: '+d.advanced_anomaly_model+' · '+(af?'FLAGGED':'normal')):('Anomaly baseline: '+(af?'flagged (research only)':'not flagged'));e('timeline').value=i}function stop(){playing=false;e('play').textContent='▶ Play';if(timer)clearInterval(timer);timer=null}function start(){if(playing){stop();return}playing=true;e('play').textContent='⏸ Pause';timer=setInterval(()=>{const s=parseInt(e('speed').value||'5'),n=i+s;if(n>=D.length){update(D.length-1);stop()}else update(n)},105)}e('play').onclick=start;e('reset').onclick=()=>{stop();update(0)};e('timeline').oninput=x=>{stop();update(parseInt(x.target.value))};update(0)</script></body></html>'''
    return (template.replace('__RUN__',str(run_name)).replace('__MAX__',str(mx)).replace('__QAC__',qac).replace('__QAMSG__',val['message']).replace('__DATA__',data).replace('__MODES__',modes).replace('__FAULTS__',faults).replace('__TH__',f'{confidence_threshold:.6f}').replace('__UNSAFE_CIP__','true' if val.get('unsafe_cip_start',False) else 'false').replace('__CIP_ENTRY_LEVEL__',f"{_num(val.get('cip_start_level_m',0.0),0.0):.6f}"))
