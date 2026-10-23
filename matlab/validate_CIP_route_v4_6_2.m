%% validate_CIP_route_v4_6_2.m
clear; clc;

thisScript=mfilename('fullpath');
matlabDir=fileparts(thisScript);
root=fileparts(matlabDir);

model='AlKaseeh_PhysicalTwin_PM_FinalScientific_v4_6_2';
file=fullfile(root,'models',[model '.slx']);

if ~isfile(file),error('Run the v4.6.2 patcher first.');end
if bdIsLoaded(model),close_system(model,0);end
load_system(file);

set_param(model,'SimscapeLogType','all');
set_param(model,'SimscapeLogName','simlog_v462_route');

set_param([model '/ALK_FaultCode'],'Value','0');
set_param([model '/ALK_FaultSeverity'],'Value','0');
set_param([model '/ALK_FaultStart'],'Value','0');
set_param([model '/ALK_FaultEnd'],'Value','5535');
set_param([model '/Subsystem/TK1'],'level','0.2');
set_param([model '/Subsystem/TK1'],'T_I','300');
set_param(model,'StopTime','5535');

fprintf('Running v4.6.2 shared-CIP-inlet validation...\n');
sim(model);

simlog=simscape.logging.getSimulationLog(model);

psv2=simscape.logging.findNode(simlog,[model '/Subsystem/PS_V2_ToTanksValve']);
cip=simscape.logging.findNode(simlog,[model '/Subsystem/CIP_P_FlowSource2']);

times=[5514.5 5515 5520 5525];

fprintf('\n============================================================\n');
fprintf('v4.6.2 SHARED-INLET CHECK\n');
fprintf('============================================================\n');

for i=1:numel(times)
    tt=times(i);

    area=valueAt(psv2.area_in.series,tt,'m^2');
    mdot=valueAt(cip.M.series,tt,'kg/s');

    pA=valueAt(psv2.A.p.series,tt,'MPa');
    pB=valueAt(psv2.B.p.series,tt,'MPa');

    TA=valueAt(psv2.A.T.series,tt,'K');
    TB=valueAt(psv2.B.T.series,tt,'K');

    fprintf('\nt = %.1f s\n',tt);
    fprintf('  CIP supply command = %.6f kg/s\n',mdot);
    fprintf('  PS_V2 area         = %.9f m^2\n',area);
    fprintf('  PS_V2 pressure A/B = %.6f / %.6f MPa\n',pA,pB);
    fprintf('  PS_V2 temp A/B     = %.3f / %.3f K\n',TA,TB);
end

tt=5525;
area=valueAt(psv2.area_in.series,tt,'m^2');
mdot=valueAt(cip.M.series,tt,'kg/s');
pA=valueAt(psv2.A.p.series,tt,'MPa');
pB=valueAt(psv2.B.p.series,tt,'MPa');
TA=valueAt(psv2.A.T.series,tt,'K');
TB=valueAt(psv2.B.T.series,tt,'K');

areaPass=area>=4.9e-3;
flowPass=mdot>=9.5;
pressurePass=isfinite(pA)&&isfinite(pB)&&abs(pA)<5&&abs(pB)<5;
tempPass=isfinite(TA)&&isfinite(TB)&&TA>=273.16&&TA<=342&&TB>=273.16&&TB<=342;

overall=areaPass&&flowPass&&pressurePass&&tempPass;

R=table(overall,areaPass,flowPass,pressurePass,tempPass,area,mdot,pA,pB,TA,TB, ...
    'VariableNames',{'overall_pass','shared_valve_open_pass','cip_flow_pass', ...
    'pressure_pass','temperature_pass','PS_V2_area_m2','CIP_supply_kg_s', ...
    'PS_V2_A_MPa','PS_V2_B_MPa','PS_V2_A_K','PS_V2_B_K'});
disp(R);

if overall
    fprintf('\n*** v4.6.2 SHARED-CIP-INLET VALIDATION PASSED ***\n');
else
    fprintf('\n*** v4.6.2 SHARED-CIP-INLET VALIDATION FAILED ***\n');
end

function v=valueAt(seriesObj,targetTime,unit)
t=seriesObj.time;
vals=seriesObj.values(unit);
[~,idx]=min(abs(t-targetTime));
v=vals(idx);
end
