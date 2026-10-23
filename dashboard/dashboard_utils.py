from __future__ import annotations

from typing import Iterable
import math
import numpy as np
import pandas as pd
import plotly.graph_objects as go

FAULT_NAMES = {
    0: "Normal operation", 1: "Production pump degradation", 2: "CIP pump degradation",
    3: "Production inlet valve blockage", 4: "Tank inlet valve blockage",
    5: "Discharge valve blockage", 6: "Discharge valve leakage",
    7: "Steam heating degradation", 8: "Agitator degradation",
    9: "CIP inlet blockage", 10: "CIP return blockage",
    101: "Temperature sensor bias", 102: "Level sensor bias",
    103: "Flow sensor scale error", 104: "Pressure sensor drift",
    105: "RPM sensor excessive noise", 106: "Temperature sensor dropout",
}
MODE_NAMES = {0:"Idle",1:"Production filling",2:"Heating and mixing",3:"Temperature holding",4:"Product discharge",5:"CIP circulation",6:"CIP drain"}
ALIASES = {
    "temperature_true_K":["temperature_true_K","temperature_K","TK1_Temp"],
    "temperature_measured_K":["temperature_measured_K","temperature_K","TK1_Temp"],
    "level_true_m":["level_true_m","level_m","TK1_Level"],
    "level_measured_m":["level_measured_m","level_m","TK1_Level"],
    "volume_m3":["volume_m3","TK1_Volume"],
    "gauge_pressure_true_Pa":["gauge_pressure_true_Pa","gauge_pressure_Pa"],
    "gauge_pressure_measured_Pa":["gauge_pressure_measured_Pa","gauge_pressure_Pa"],
    "production_mass_flow_true_kg_s":["production_mass_flow_true_kg_s","production_mass_flow_kg_s"],
    "production_mass_flow_measured_kg_s":["production_mass_flow_measured_kg_s","production_mass_flow_kg_s"],
    "agitator_speed_true_rpm":["agitator_speed_true_rpm","agitator_speed_rpm"],
    "agitator_speed_measured_rpm":["agitator_speed_measured_rpm","agitator_speed_rpm"],
    "return_temperature_K":["return_temperature_K","cip_return_temperature_K"],
    "process_mode":["process_mode","Mode"], "fault_active":["fault_active"],
    "fault_code":["fault_code","requested_fault_code"],
    "fault_severity":["fault_severity","requested_fault_severity"],
    "sensor_fault_code":["sensor_fault_code"],
    "requested_fault_start_s":["requested_fault_start_s","fault_start_s"],
    "requested_fault_end_s":["requested_fault_end_s","fault_end_s"],
    "cmd_prod_inlet":["cmd_prod_inlet"], "cmd_prod_to_tank":["cmd_prod_to_tank"],
    "cmd_prod_to_filling":["cmd_prod_to_filling"], "cmd_cip_inlet":["cmd_cip_inlet"],
    "cmd_cip_return":["cmd_cip_return"], "cmd_steam":["cmd_steam"],
    "cmd_prod_flow":["cmd_prod_flow"], "cmd_cip_flow":["cmd_cip_flow"],
    "cmd_agitator_rpm":["cmd_agitator_rpm"], "pump_capacity_factor":["pump_capacity_factor"],
    "effective_heat_flow_W":["effective_heat_flow_W"],
    "effective_prod_flow_command_kg_s":["effective_prod_flow_command_kg_s"],
}

def normalize_schema(df: pd.DataFrame) -> pd.DataFrame:
    d=df.copy()
    if "time" not in d:
        for c in ("Time","timestamp","t"):
            if c in d: d["time"]=d[c]; break
    if "time" not in d: d["time"]=np.arange(len(d),dtype=float)
    d["time"]=pd.to_numeric(d["time"],errors="coerce")
    d=d.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)
    for canonical,candidates in ALIASES.items():
        if canonical in d: continue
        for c in candidates:
            if c in d: d[canonical]=d[c]; break
    defaults={"fault_active":0.,"fault_code":0.,"fault_severity":0.,"sensor_fault_code":0.,"requested_fault_start_s":np.nan,"requested_fault_end_s":np.nan,"process_mode":0.,"cmd_prod_inlet":0.,"cmd_prod_to_tank":0.,"cmd_prod_to_filling":0.,"cmd_cip_inlet":0.,"cmd_cip_return":0.,"cmd_steam":0.,"cmd_prod_flow":0.,"cmd_cip_flow":0.,"cmd_agitator_rpm":0.}
    for c,default in defaults.items():
        if c not in d: d[c]=default
        d[c]=pd.to_numeric(d[c],errors="coerce")
        if np.isfinite(default): d[c]=d[c].fillna(default)
    if "effective_heat_flow_W" not in d: d["effective_heat_flow_W"]=d["cmd_steam"]*120000.
    if "effective_prod_flow_command_kg_s" not in d: d["effective_prod_flow_command_kg_s"]=d["cmd_prod_flow"]*10.
    if "pump_capacity_factor" not in d:
        cmd=d["effective_prod_flow_command_kg_s"].abs(); d["pump_capacity_factor"]=np.where(cmd>1e-9,cmd/10.,0.)
    vo,vc=5e-4,1e-8
    for command,output in (("cmd_prod_inlet","prod_inlet_actual_pct"),("cmd_prod_to_tank","tank_inlet_actual_pct"),("cmd_prod_to_filling","discharge_actual_pct"),("cmd_cip_inlet","cip_inlet_actual_pct"),("cmd_cip_return","cip_return_actual_pct")):
        if output not in d: d[output]=np.clip(100*(d[command]-vc)/(vo-vc),0,100)
    if "scenario" not in d: d["scenario"]="simulation"
    if "run_id" not in d: d["run_id"]="run"
    return d

def value(row,name,default=np.nan):
    try:
        x=float(row.get(name,default)); return x if math.isfinite(x) else default
    except Exception: return default

def mode_name(code):
    try: return MODE_NAMES.get(int(round(float(code))),f"Mode {int(round(float(code)))}")
    except Exception: return "Unknown mode"

def fault_name(code):
    try: return FAULT_NAMES.get(int(round(float(code))),f"Fault code {int(round(float(code)))}")
    except Exception: return "Unknown"

def actual_fault_state(row):
    t=value(row,"time",0.); actuator=value(row,"fault_active",0.)>=.5; ac=int(round(value(row,"fault_code",0.))); sc=int(round(value(row,"sensor_fault_code",0.)))
    s=value(row,"requested_fault_start_s",np.nan); e=value(row,"requested_fault_end_s",np.nan)
    if sc>0:
        active=(s<=t<=e) if math.isfinite(s) and math.isfinite(e) else (t>=s if math.isfinite(s) else actuator)
        if active: return True,sc
    return (True,ac) if actuator else (False,0)

def alarm_state(row,ai_row=None,confidence_threshold=.55):
    actual,actual_code=actual_fault_state(row); pred=0; conf=np.nan; model="No trained classifier"; top3=""
    if ai_row is not None:
        pred=int(ai_row.get("primary_fault_code",0) or 0); model=str(ai_row.get("primary_model",model)); top3=str(ai_row.get("primary_top3",""))
        try: conf=float(ai_row.get("primary_confidence",np.nan))
        except Exception: pass
    high=pred!=0 and math.isfinite(conf) and conf>=confidence_threshold
    if actual: level,message="ALARM",f"Actual/injected fault active: {fault_name(actual_code)}"
    elif high: level,message="ADVISORY",f"AI diagnostic indication: {fault_name(pred)}"
    else: level,message="NORMAL","No active fault; no high-confidence AI diagnostic indication"
    return {"level":level,"message":message,"actual_code":actual_code,"predicted_code":pred,"confidence":conf,"primary_model":model,"top3":top3}

def trend_figure(df:pd.DataFrame,columns:Iterable[str],title:str,y_title:str,cursor_time:float|None=None)->go.Figure:
    labels={"level_true_m":"Physical truth","level_measured_m":"Measured","temperature_true_K":"Physical truth","temperature_measured_K":"Measured","gauge_pressure_true_Pa":"Physical truth","gauge_pressure_measured_Pa":"Measured","production_mass_flow_true_kg_s":"Physical truth","production_mass_flow_measured_kg_s":"Measured","effective_prod_flow_command_kg_s":"Effective command","agitator_speed_true_rpm":"Physical truth","agitator_speed_measured_rpm":"Measured","cmd_agitator_rpm":"Command","process_mode":"Process mode"}
    palette=["#127A9A","#D18A2E","#4D6A87","#1E9E78","#8F5DB7"]
    fig=go.Figure(); i=0
    for c in columns:
        if c in df:
            fig.add_trace(go.Scatter(x=df["time"],y=df[c],name=labels.get(c,c.replace("_"," ")),mode="lines",line=dict(color=palette[i%len(palette)],width=2),hovertemplate="%{x:.1f} s<br>%{y:.4g}<extra>%{fullData.name}</extra>")); i+=1
    if cursor_time is not None: fig.add_vline(x=cursor_time,line_dash="dash",line_color="#C34F4F")
    fig.update_layout(title=dict(text=title,font=dict(size=16,color="#172033")),xaxis_title="Simulation time (s)",yaxis_title=y_title,height=340,margin=dict(l=35,r=25,t=55,b=40),paper_bgcolor="#fff",plot_bgcolor="#fff",font=dict(color="#26364A"),legend=dict(orientation="h",yanchor="bottom",y=1.02,xanchor="left",x=0,bgcolor="rgba(255,255,255,.88)"),xaxis=dict(showgrid=True,gridcolor="#E7EDF4",zeroline=False),yaxis=dict(showgrid=True,gridcolor="#E7EDF4",zeroline=False))
    return fig

def detection_summary(df,predictions):
    times=[float(r["time"]) for _,r in df.iterrows() if actual_fault_state(r)[0]]; start=min(times) if times else np.nan
    result={"actual_fault_start_s":start,"classification_detection_s":np.nan,"classification_delay_s":np.nan,"pre_onset_indication":False}
    if predictions is None or predictions.empty or "primary_fault_code" not in predictions: return result
    codes=pd.to_numeric(predictions["primary_fault_code"],errors="coerce").fillna(0).astype(int); conf=pd.to_numeric(predictions.get("primary_confidence",np.nan),errors="coerce")
    hit=predictions[(codes!=0)&(conf>=.55)]
    if len(hit):
        first=float(hit["time_end"].iloc[0]); result["classification_detection_s"]=first
        if math.isfinite(start): result["classification_delay_s"]=first-start; result["pre_onset_indication"]=first<start
    return result
