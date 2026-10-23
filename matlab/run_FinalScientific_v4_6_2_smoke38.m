%% run_FinalScientific_v4_6_2_smoke38.m
% Al Kaseeh Final Scientific v4.6.2
% 38-run smoke campaign: 2 runs x 19 classes.
%
% PURPOSE
% -------
% This is a QA gate, NOT the final 1900-run scientific campaign.
%
% It:
%   1) runs the accepted v4.6.2 model for 9000 s/run;
%   2) uses two deterministic severities per nonzero fault class;
%   3) uses conservative initial-state variation;
%   4) infers mode windows from the first healthy run;
%   5) injects each fault across the mode in which the affected component
%      should be operating;
%   6) exports one 1-Hz CSV per run;
%   7) preserves true physical channels separately from measured channels;
%   8) records FaultActive and fault metadata;
%   9) continues after an individual failed run, but records the failure.
%
% MODEL IS NOT MODIFIED.
%
% NEXT:
%   run('matlab/qa_FinalScientific_v4_6_2_smoke38.m')
%
% MATLAB: R2025b

clear; clc;

%% ------------------------------------------------------------------------
% Project / model
% -------------------------------------------------------------------------
thisScript = mfilename('fullpath');
matlabDir = fileparts(thisScript);
projectRoot = fileparts(matlabDir);

model = 'AlKaseeh_PhysicalTwin_PM_FinalScientific_v4_6_2';
modelFile = fullfile(projectRoot,'models',[model '.slx']);

if ~isfile(modelFile)
    error('Accepted v4.6.2 model not found:\n%s',modelFile);
end

outDir = fullfile(projectRoot,'ml','data', ...
    'final_scientific_v4_6_2','smoke38');

if ~isfolder(outDir)
    mkdir(outDir);
end

manifestFile = fullfile(outDir,'smoke38_manifest.csv');
modeWindowFile = fullfile(outDir,'baseline_mode_windows.csv');

%% ------------------------------------------------------------------------
% Short Simulink build paths
% -------------------------------------------------------------------------
cacheDir = 'C:\AKBuild\cache';
codeDir  = 'C:\AKBuild\codegen';

if ~isfolder(cacheDir), mkdir(cacheDir); end
if ~isfolder(codeDir),  mkdir(codeDir);  end

Simulink.fileGenControl('set', ...
    'CacheFolder',cacheDir, ...
    'CodeGenFolder',codeDir, ...
    'createDir',true);

if bdIsLoaded(model)
    close_system(model,0);
end

load_system(modelFile);

set_param(model,'FastRestart','off');
set_param(model,'StopTime','9000');
set_param(model,'SolverType','Variable-step');
set_param(model,'Solver','ode15s');
set_param(model,'RelTol','1e-4');
set_param(model,'MaxStep','0.1');

% Full-horizon physical logging, decimated for campaign memory efficiency.
% v4.6.2 nominal validation was already performed with decimation=1.
set_param(model,'SimscapeLogType','all');
set_param(model,'SimscapeLogName','simlog_v462_smoke');
set_param(model,'SimscapeLogLimitData','off');
set_param(model,'SimscapeLogDecimation',20);

%% ------------------------------------------------------------------------
% Fault catalog: EXACT final 19-class taxonomy
% -------------------------------------------------------------------------
faultCodes = [ ...
      0, ...
      1,2,3,4,5,6,7,8,9,10,11,12, ...
      101,102,103,104,105,106];

faultNames = { ...
    'Normal', ...
    'Production fill-pump degradation', ...
    'CIP supply-pump degradation', ...
    'Production inlet valve blockage', ...
    'Tank inlet valve blockage', ...
    'Product discharge valve blockage', ...
    'Product discharge valve leakage-stuck open', ...
    'Heating degradation', ...
    'Agitator degradation', ...
    'CIP inlet valve blockage', ...
    'CIP return valve blockage', ...
    'Product discharge-pump degradation', ...
    'CIP return-pump degradation', ...
    'Temperature sensor bias', ...
    'Level sensor bias', ...
    'Production flow sensor scale', ...
    'Pressure sensor drift', ...
    'RPM excess noise', ...
    'Temperature sensor dropout'};

nClasses = numel(faultCodes);
nRep = 2;
expectedRuns = nClasses*nRep;

fprintf('============================================================\n');
fprintf('FINAL SCIENTIFIC v4.6.2 — 38-RUN SMOKE CAMPAIGN\n');
fprintf('============================================================\n');
fprintf('Model: %s\n',model);
fprintf('Runs:  %d classes x %d = %d\n',nClasses,nRep,expectedRuns);
fprintf('Stop time: 9000 s/run\n');
fprintf('Export: 1 Hz CSV\n');
fprintf('Output: %s\n',outDir);
fprintf('============================================================\n\n');

%% ------------------------------------------------------------------------
% Resume support
% -------------------------------------------------------------------------
if isfile(manifestFile)
    manifest = readtable(manifestFile,'TextType','string');
else
    manifest = emptyManifest();
end

% If a baseline run already exists, recover its mode windows.
baselineCSV = fullfile(outDir,'v462_smoke_fc000_rep01.csv');

if isfile(modeWindowFile)
    modeWindows = readtable(modeWindowFile);
elseif isfile(baselineCSV)
    B = readtable(baselineCSV);
    modeWindows = inferModeWindows(B.time,B.process_mode);
    writetable(modeWindows,modeWindowFile);
else
    modeWindows = table();
end

runCounter = 0;

%% ------------------------------------------------------------------------
% Campaign
% -------------------------------------------------------------------------
for c = 1:nClasses

    code = faultCodes(c);
    name = faultNames{c};

    for rep = 1:nRep

        runCounter = runCounter+1;
        runID = sprintf('v462_smoke_fc%03d_rep%02d',code,rep);
        csvFile = fullfile(outDir,[runID '.csv']);

        % Resume safely without mixing duplicate runs.
        if isfile(csvFile)
            fprintf('[%02d/%02d] SKIP existing: %s\n', ...
                runCounter,expectedRuns,runID);

            if code==0 && rep==1 && isempty(modeWindows)
                B = readtable(csvFile);
                modeWindows = inferModeWindows(B.time,B.process_mode);
                writetable(modeWindows,modeWindowFile);
            end
            continue;
        end

        seed = 462000 + c*100 + rep;
        rng(seed,'twister');

        % Smoke uses conservative, deterministic variability.
        % Final scientific campaign will later use the wider locked ranges.
        if code==0 && rep==1
            initLevel = 0.20;
            initTemp  = 300.0;
        else
            initLevel = 0.16 + 0.08*rand();   % 0.16–0.24 m
            initTemp  = 296.0 + 5.0*rand();   % 296–301 K
        end

        severity = smokeSeverity(code,rep);

        if code==0
            faultStart = 0.0;
            faultEnd   = 0.0;
        else
            if isempty(modeWindows)
                error(['Baseline mode windows are unavailable. ' ...
                    'The first healthy run must complete before fault runs.']);
            end
            [faultStart,faultEnd] = faultWindowForCode(code,modeWindows);
        end

        fprintf('\n[%02d/%02d] %s\n',runCounter,expectedRuns,runID);
        fprintf('  class:     %d — %s\n',code,name);
        fprintf('  severity:  %.3f\n',severity);
        fprintf('  fault:     %.1f -> %.1f s\n',faultStart,faultEnd);
        fprintf('  init:      level %.4f m, temp %.3f K\n',initLevel,initTemp);

        % Configure injected fault.
        set_param([model '/ALK_FaultCode'], ...
            'Value',num2str(code,'%.15g'));
        set_param([model '/ALK_FaultSeverity'], ...
            'Value',num2str(severity,'%.15g'));
        set_param([model '/ALK_FaultStart'], ...
            'Value',num2str(faultStart,'%.15g'));
        set_param([model '/ALK_FaultEnd'], ...
            'Value',num2str(faultEnd,'%.15g'));

        % Initial plant state.
        set_param([model '/Subsystem/TK1'], ...
            'level',num2str(initLevel,'%.15g'));
        set_param([model '/Subsystem/TK1'], ...
            'T_I',num2str(initTemp,'%.15g'));

        simOK = false;
        quickQAPass = false;
        errText = "";
        warningText = "";
        rowsExported = 0;
        faultActiveSamples = 0;
        modesReachedText = "";
        mode7Present = false;
        propertyEnvelopePass = false;
        measuredContractPass = false;
        criticalMinT = NaN;
        criticalMaxT = NaN;
        criticalMinP = NaN;
        criticalMaxP = NaN;
        criticalBadBlock = "";

        try
            lastwarn('');

            simOut = sim(model,'ReturnWorkspaceOutputs','on');

            [wmsg,~] = lastwarn;
            warningText = string(wmsg);

            simlog = simscape.logging.getSimulationLog(model);

            if isempty(simlog)
                error('Simulation completed but no Simscape log was returned.');
            end

            D = buildExportTable( ...
                simOut,simlog,model,runID,code,name,rep,seed,severity, ...
                faultStart,faultEnd,initLevel,initTemp);

            rowsExported = height(D);

            writetable(D,csvFile);

            % First healthy run defines mode-aware fault windows.
            if code==0 && rep==1
                modeWindows = inferModeWindows(D.time,D.process_mode);
                writetable(modeWindows,modeWindowFile);

                requiredModes = 0:6;
                if ~all(ismember(requiredModes,modeWindows.mode))
                    error(['Baseline run did not cover all Modes 0–6. ' ...
                        'Do not schedule fault runs.']);
                end
            end

            [quickQAPass,q] = quickRunQA(D,code,warningText);

            % Critical branch-level Simscape envelope. This is mandatory
            % because a blocked branch can become nonphysical while TK1 bulk
            % pressure/temperature still look normal.
            [criticalPass,criticalMinT,criticalMaxT, ...
                criticalMinP,criticalMaxP,criticalBadBlock] = ...
                criticalTLPropertyEnvelope(simlog,model);

            faultActiveSamples = q.fault_active_samples;
            modesReachedText = string(q.modes_reached);
            mode7Present = q.mode7_present;
            propertyEnvelopePass = q.property_envelope_pass && criticalPass;
            measuredContractPass = q.measured_contract_pass;

            quickQAPass = quickQAPass && criticalPass;

            simOK = true;

            fprintf('  export:    %d rows\n',rowsExported);
            fprintf('  modes:     %s\n',modesReachedText);
            fprintf('  active:    %d samples\n',faultActiveSamples);
            fprintf('  quick QA:  %s\n',tfstr(quickQAPass));

        catch ME
            errText = string(getReport(ME,'basic','hyperlinks','off'));
            fprintf(2,'  *** RUN FAILED ***\n%s\n',errText);

            % Baseline failure is a hard stop because later mode-aware
            % injection timing cannot be scheduled scientifically.
            if code==0 && rep==1
                row = manifestRow(runID,code,name,rep,seed,severity, ...
                    faultStart,faultEnd,initLevel,initTemp, ...
                    simOK,quickQAPass,rowsExported,faultActiveSamples, ...
                    modesReachedText,mode7Present,propertyEnvelopePass, ...
                    measuredContractPass,criticalMinT,criticalMaxT, ...
                    criticalMinP,criticalMaxP,criticalBadBlock, ...
                    warningText,errText,csvFile);
                manifest = upsertManifest(manifest,row);
                writetable(manifest,manifestFile);
                rethrow(ME);
            end
        end

        row = manifestRow(runID,code,name,rep,seed,severity, ...
            faultStart,faultEnd,initLevel,initTemp, ...
            simOK,quickQAPass,rowsExported,faultActiveSamples, ...
            modesReachedText,mode7Present,propertyEnvelopePass, ...
            measuredContractPass,criticalMinT,criticalMaxT, ...
            criticalMinP,criticalMaxP,criticalBadBlock, ...
            warningText,errText,csvFile);

        manifest = upsertManifest(manifest,row);
        writetable(manifest,manifestFile);

        clear simOut simlog D
        drawnow;
    end
end

fprintf('\n============================================================\n');
fprintf('SMOKE CAMPAIGN EXECUTION COMPLETE\n');
fprintf('============================================================\n');
fprintf('Manifest:\n  %s\n',manifestFile);
fprintf('\nRUN THE MANDATORY QA GATE NOW:\n');
fprintf('  run(''matlab/qa_FinalScientific_v4_6_2_smoke38.m'')\n');
fprintf('============================================================\n');

%% ========================================================================
% Local functions
% ========================================================================

function severity = smokeSeverity(code,rep)
if code==0
    severity = 0.0;
elseif code==6
    vals = [0.15 0.30]; % leakage: moderate / stronger
elseif code>=101
    vals = [0.25 0.45]; % sensor fault severity
else
    vals = [0.30 0.50]; % degradation / blockage
end
if code~=0
    severity = vals(rep);
end
end

function [t1,t2] = faultWindowForCode(code,W)

m1 = modeBounds(W,1);
m2 = modeBounds(W,2);
m3 = modeBounds(W,3);
m4 = modeBounds(W,4);
m5 = modeBounds(W,5);

switch code
    case {1,3,4,103}
        % Entire useful production-fill period.
        t1 = max(0,m1(1)+5);
        t2 = min(9000,m1(2)+20);

    case {7,8,101,102,104,105,106}
        % Broad middle portion of heating/mixing.
        d = max(1,m2(2)-m2(1));
        t1 = m2(1)+0.15*d;
        t2 = m2(1)+0.65*d;

    case 6
        % Leakage should be visible while discharge should still be closed,
        % then into early discharge.
        d3 = max(1,m3(2)-m3(1));
        t1 = m3(1)+0.30*d3;
        t2 = min(m5(1)-10,m4(1)+90);
        if t2 <= t1
            t1 = max(0,m4(1)-30);
            t2 = m4(2)+20;
        end

    case {5,11}
        % Product discharge path.
        t1 = max(0,m4(1)-20);
        t2 = min(9000,m4(2)+30);

    case {2,9,10,12}
        % CIP circulation path.
        t1 = max(0,m5(1)-20);
        t2 = min(9000,m5(2)+30);

    otherwise
        error('No smoke fault window defined for code %d.',code);
end

if ~(isfinite(t1)&&isfinite(t2)&&t2>t1)
    error('Invalid injection window for fault code %d.',code);
end
end

function b = modeBounds(W,modeID)
idx = W.mode==modeID;
if ~any(idx)
    error('Baseline did not contain required mode %d.',modeID);
end
b = [min(W.start_s(idx)),max(W.end_s(idx))];
end

function W = inferModeWindows(t,m)
t = double(t(:));
m = round(double(m(:)));

good = isfinite(t)&isfinite(m);
t=t(good); m=m(good);

if isempty(t)
    error('Cannot infer mode windows from empty mode signal.');
end

change = [true; diff(m)~=0];
starts = find(change);
ends = [starts(2:end)-1; numel(m)];

mode = m(starts);
start_s = t(starts);
end_s = t(ends);

W = table(mode,start_s,end_s);
end

function D = buildExportTable( ...
    simOut,simlog,model,runID,code,name,rep,seed,severity, ...
    faultStart,faultEnd,initLevel,initTemp)

tg = (0:1:9000)';

phys = [model '/Subsystem'];

% ---------------- Physical truth ----------------
tk1 = requireNode(simlog,[phys '/TK1']);

levelTrue = ssAt(tk1.level.series,tg,'m');
% TK1 is the accepted constant-area tank: A = 1.24 m^2.
% Derive volume deterministically rather than depending on a version-specific
% Simscape internal volume-node name.
volume = 1.24*levelTrue;
tempTrue = ssAt(tk1.T_out.series,tg,'K');

% Absolute pressure -> gauge Pa.
pAbsMPa = ssAt(tk1.B.p.series,tg,'MPa');
gaugePressureTrue = pAbsMPa*1e6 - 101325.0;

fill = requireNode(simlog,[phys '/PS_P1_FlowSource']);
prod = requireNode(simlog,[phys '/Prod_RP_FlowSource']);
cipS = requireNode(simlog,[phys '/CIP_P_FlowSource2']);
cipR = requireNode(simlog,[phys '/CIP_RP_FlowSource']);

% For Flow Rate Source (TL), M is the imposed mass-flow input. This is the
% same source quantity used by the accepted v4.6.2 nominal validators.
prodFillTrue = abs(ssAt(fill.M.series,tg,'kg/s'));
prodDischargeTrue = abs(ssAt(prod.M.series,tg,'kg/s'));
cipSupplyTrue = abs(ssAt(cipS.M.series,tg,'kg/s'));
cipReturnTrue = abs(ssAt(cipR.M.series,tg,'kg/s'));

% Physical valve positions.
prodInletPct = valvePct(simlog,[phys '/V001_InletValve'],tg);
tankInletPct = valvePct(simlog,[phys '/PS_V2_ToTanksValve'],tg);
dischargePct = valvePct(simlog,[phys '/Prod_V2_ToFillingLine3'],tg);
cipInletPct = valvePct(simlog,[phys '/CIP_V1_InletValve'],tg);
cipReturnPct = valvePct(simlog,[phys '/CIP_V3_ReturnValve'],tg);

% ---------------- Simulink/control/measured signals ----------------
processMode = simSignalAt(simOut, ...
    {'process_mode','Mode','ALK_Mode','ProcessMode','mode'}, ...
    tg,'previous');

if all(isnan(processMode))
    error('Required process-mode logging signal was not found.');
end

faultActive = simSignalAt(simOut, ...
    {'FaultActive','fault_active','ALK_FaultActive','Fault_Active'}, ...
    tg,'previous');

tempMeasured = simSignalAt(simOut, ...
    {'TK1_Temp','temperature_measured_K','TK1_Temp_Measured', ...
     'Measured_TK1_Temp','ControllerSeen_TK1_Temp'},tg,'linear');

levelMeasured = simSignalAt(simOut, ...
    {'TK1_Level','level_measured_m','TK1_Level_Measured', ...
     'Measured_TK1_Level','ControllerSeen_TK1_Level'},tg,'linear');

pressureMeasured = simSignalAt(simOut, ...
    {'TK1_Pressure','TK1_pressure','gauge_pressure_measured_Pa', ...
     'PressureMeasured','TK1_Pressure_Measured'},tg,'linear');

% Normalize a logged pressure channel to gauge Pa without hiding the
% class-104 drift. The unaffected early segment is used only to resolve
% unit/absolute-vs-gauge representation.
if ~all(isnan(pressureMeasured))
    pressureMeasured = normalizePressureMeasured( ...
        pressureMeasured,gaugePressureTrue,tg,faultStart);
end

prodFlowMeasured = simSignalAt(simOut, ...
    {'MassFlowRateProd','production_mass_flow_measured_kg_s', ...
     'MassFlowRate','ProdFlowMeasured'},tg,'linear');

rpmMeasured = simSignalAt(simOut, ...
    {'M1_RPM','agitator_speed_measured_rpm','AgitatorRPM_Measured', ...
     'MeasuredAgitatorRPM'},tg,'linear');

rpmTrue = simSignalAt(simOut, ...
    {'M1_RPM_True','AgitatorRPM_True','agitator_speed_true_rpm', ...
     'TrueAgitatorRPM'},tg,'linear');

steamCmd = simSignalAt(simOut, ...
    {'SteamValve','cmd_steam','SteamCmd','outv6_steam_cmd'}, ...
    tg,'previous');

heatFlow = simSignalAt(simOut, ...
    {'EnergyFlowRate','effective_heat_flow_W','EffectiveHeatFlow', ...
     'HeatFlowRate'},tg,'linear');

% Preserve sensor-fault detectability. Fallback to physical truth is allowed
% for non-target sensor channels, but never for the channel being tested.
if all(isnan(tempMeasured))
    if ismember(code,[101 106])
        tempMeasured = nan(size(tg));
    else
        tempMeasured = tempTrue;
    end
end

if all(isnan(levelMeasured))
    if code==102
        levelMeasured = nan(size(tg));
    else
        levelMeasured = levelTrue;
    end
end

if all(isnan(pressureMeasured))
    if code==104
        pressureMeasured = nan(size(tg));
    else
        pressureMeasured = gaugePressureTrue;
    end
end

if all(isnan(prodFlowMeasured))
    if code==103
        prodFlowMeasured = nan(size(tg));
    else
        prodFlowMeasured = prodFillTrue;
    end
end

% Fixed controller command in Modes 2/3 from accepted v4.6.2 logic.
cmdAgitator = zeros(size(tg));
cmdAgitator(processMode==2 | processMode==3) = 23.2;

% If explicit true RPM is unavailable, do not silently claim measured=true
% for RPM sensor-fault classes.
if all(isnan(rpmTrue))
    if ~ismember(code,[8 105]) && ~all(isnan(rpmMeasured))
        rpmTrue = rpmMeasured;
    end
end

% HMI-compatible effective flow command fields. These represent effective
% physical source command after fault injection, normalized to nominal 10 kg/s.
cmdProdFlow = min(1,max(0,prodFillTrue/10.0));
cmdProdDischarge = min(1,max(0,prodDischargeTrue/10.0));
cmdCIPFlow = min(1,max(0,cipSupplyTrue/10.0));
cmdCIPReturn = min(1,max(0,cipReturnTrue/10.0));

if all(isnan(steamCmd))
    steamCmd = zeros(size(tg));
end

if all(isnan(heatFlow))
    heatFlow = nan(size(tg));
end

% Active row-level labels.
if all(isnan(faultActive))
    activeMask = false(size(tg));
else
    activeMask = faultActive >= 0.5;
end

faultCode = zeros(size(tg));
sensorFaultCode = zeros(size(tg));

if code>=101
    sensorFaultCode(activeMask) = code;
else
    faultCode(activeMask) = code;
end

% ---------------- Export table ----------------
n = numel(tg);

D = table();

D.time = tg;
D.run_id = repmat(string(runID),n,1);
D.scenario = repmat(string(name),n,1);

D.target = repmat(code,n,1);
D.run_target_label = repmat(code,n,1);
D.injected_fault_code = repmat(code,n,1);
D.fault_name = repmat(string(name),n,1);
D.replicate = repmat(rep,n,1);
D.seed = repmat(seed,n,1);
D.fault_severity = repmat(severity,n,1);
D.requested_fault_start_s = repmat(faultStart,n,1);
D.requested_fault_end_s = repmat(faultEnd,n,1);
D.initial_level_m = repmat(initLevel,n,1);
D.initial_temperature_K = repmat(initTemp,n,1);

D.process_mode = processMode;
D.fault_active = faultActive;
D.fault_code = faultCode;
D.sensor_fault_code = sensorFaultCode;

D.level_true_m = levelTrue;
D.level_measured_m = levelMeasured;
D.volume_m3 = volume;

D.temperature_true_K = tempTrue;
D.temperature_measured_K = tempMeasured;

D.gauge_pressure_true_Pa = gaugePressureTrue;
D.gauge_pressure_measured_Pa = pressureMeasured;

D.production_mass_flow_true_kg_s = prodFillTrue;
D.production_mass_flow_measured_kg_s = prodFlowMeasured;
D.product_discharge_mass_flow_true_kg_s = prodDischargeTrue;
D.cip_supply_mass_flow_true_kg_s = cipSupplyTrue;
D.cip_return_mass_flow_true_kg_s = cipReturnTrue;

D.agitator_speed_true_rpm = rpmTrue;
D.agitator_speed_measured_rpm = rpmMeasured;
D.cmd_agitator_rpm = cmdAgitator;

D.cmd_steam = steamCmd;
D.effective_heat_flow_W = heatFlow;

D.cmd_prod_flow = cmdProdFlow;
D.cmd_product_discharge_flow = cmdProdDischarge;
D.cmd_cip_flow = cmdCIPFlow;
D.cmd_cip_return_flow = cmdCIPReturn;

D.prod_inlet_actual_pct = prodInletPct;
D.tank_inlet_actual_pct = tankInletPct;
D.discharge_actual_pct = dischargePct;
D.cip_inlet_actual_pct = cipInletPct;
D.cip_return_actual_pct = cipReturnPct;

end

function [pass,q] = quickRunQA(D,code,warningText)

q = struct();

core = [ ...
    D.time, ...
    D.process_mode, ...
    D.level_true_m, ...
    D.volume_m3, ...
    D.temperature_true_K, ...
    D.gauge_pressure_true_Pa, ...
    D.production_mass_flow_true_kg_s, ...
    D.product_discharge_mass_flow_true_kg_s, ...
    D.cip_supply_mass_flow_true_kg_s, ...
    D.cip_return_mass_flow_true_kg_s];

coreFinite = all(isfinite(core),'all');

timePass = height(D)==9001 && ...
    abs(D.time(1))<1e-9 && ...
    abs(D.time(end)-9000)<1e-9 && ...
    all(diff(D.time)>0);

modes = unique(round(D.process_mode(isfinite(D.process_mode))))';
q.modes_reached = mat2str(modes);
q.mode7_present = any(round(D.process_mode)==7);

if code==0
    activePass = all((D.fault_active==0) | isnan(D.fault_active));
    modePass = all(ismember(0:6,modes)) && ~q.mode7_present;
else
    activePass = any(D.fault_active>=0.5);
    modePass = true;
end

q.fault_active_samples = sum(D.fault_active>=0.5);

% Broad physical validity gate. These are numerical sanity limits rather
% than certified plant design limits.
absPressureMPa = (D.gauge_pressure_true_Pa + 101325)/1e6;

q.property_envelope_pass = ...
    all(D.temperature_true_K>=273.16 & D.temperature_true_K<=342.0) && ...
    all(absPressureMPa>0 & absPressureMPa<5.0) && ...
    all(D.level_true_m>=0 & D.level_true_m<=1.65);

warnLower = lower(string(warningText));
warningPass = ~(contains(warnLower,'assertion') || ...
    contains(warnLower,'maximum valid pressure') || ...
    contains(warnLower,'minimum valid temperature') || ...
    contains(warnLower,'maximum valid temperature'));

q.measured_contract_pass = measuredContract(D,code);

pass = coreFinite && timePass && activePass && modePass && ...
    q.property_envelope_pass && warningPass && q.measured_contract_pass;
end

function pass = measuredContract(D,code)

active = D.fault_active>=0.5;
pass = true;

switch code
    case {101,106}
        pass = any(active) && any(isfinite(D.temperature_measured_K(active)) | ...
            isnan(D.temperature_measured_K(active)));
        % Require the measured channel to exist as a separate faulted signal:
        diffv = abs(D.temperature_measured_K-D.temperature_true_K);
        pass = pass && any(isnan(D.temperature_measured_K(active)) | ...
            (isfinite(diffv(active)) & diffv(active)>1e-6));

    case 102
        diffv = abs(D.level_measured_m-D.level_true_m);
        pass = any(active) && any(isfinite(diffv(active)) & diffv(active)>1e-8);

    case 103
        diffv = abs(D.production_mass_flow_measured_kg_s- ...
            D.production_mass_flow_true_kg_s);
        pass = any(active) && any(isfinite(diffv(active)) & diffv(active)>1e-6);

    case 104
        diffv = abs(D.gauge_pressure_measured_Pa-D.gauge_pressure_true_Pa);
        pass = any(active) && any(isfinite(diffv(active)) & diffv(active)>1e-3);

    case 105
        if all(isnan(D.agitator_speed_true_rpm)) || ...
                all(isnan(D.agitator_speed_measured_rpm))
            pass = false;
        else
            diffv = abs(D.agitator_speed_measured_rpm- ...
                D.agitator_speed_true_rpm);
            pass = any(active) && any(isfinite(diffv(active)) & diffv(active)>1e-6);
        end

    case 8
        if all(isnan(D.agitator_speed_measured_rpm))
            pass = false;
        else
            activeMix = active & D.cmd_agitator_rpm>1;
            pass = any(activeMix) && ...
                median(D.agitator_speed_measured_rpm(activeMix),'omitnan') < ...
                median(D.cmd_agitator_rpm(activeMix),'omitnan')-0.25;
        end
end
end

function node = requireNode(simlog,path)
node = simscape.logging.findNode(simlog,path);
if isempty(node)
    error('Required Simscape node not found:\n%s',path);
end
end

function y = ssAt(seriesObj,tg,unit)
t = double(time(seriesObj));
v = double(values(seriesObj,'Units',unit));
t=t(:); v=v(:);

good = isfinite(t)&isfinite(v);
t=t(good); v=v(good);

[t,ia] = unique(t,'stable');
v=v(ia);

if isempty(t)
    y = nan(size(tg));
else
    y = interp1(t,v,tg,'linear','extrap');
end
end

function pct = valvePct(simlog,path,tg)
node = requireNode(simlog,path);
area = ssAt(node.area_in.series,tg,'m^2');
pct = 100*(area-1e-8)/(5e-3-1e-8);
pct = min(100,max(0,pct));
end

function y = simSignalAt(simOut,candidates,tg,method)

y = nan(size(tg));

for i=1:numel(candidates)

    ts = [];

    name = candidates{i};

    try
        x = simOut.get(name);
        if isa(x,'timeseries')
            ts=x;
        elseif isa(x,'Simulink.SimulationData.Signal') && ...
                isa(x.Values,'timeseries')
            ts=x.Values;
        end
    catch
    end

    if isempty(ts)
        try
            ds = simOut.logsout;
            el = ds.get(name);
            if ~isempty(el) && isa(el.Values,'timeseries')
                ts=el.Values;
            end
        catch
        end
    end

    if isempty(ts)
        try
            x=evalin('base',name);
            if isa(x,'timeseries')
                ts=x;
            end
        catch
        end
    end

    if ~isempty(ts)
        t=double(ts.Time(:));
        v=double(ts.Data);

        if ~isvector(v)
            v=squeeze(v);
            if ~isvector(v)
                v=v(:,1);
            end
        end

        v=v(:);

        n=min(numel(t),numel(v));
        t=t(1:n); v=v(1:n);

        good=isfinite(t);
        t=t(good); v=v(good);

        [t,ia]=unique(t,'stable');
        v=v(ia);

        if isempty(t)
            continue;
        end

        if strcmpi(method,'previous')
            y=interp1(t,v,tg,'previous','extrap');
        else
            y=interp1(t,v,tg,'linear','extrap');
        end
        return;
    end
end
end

function [pass,minT,maxT,minP,maxP,badBlock] = ...
    criticalTLPropertyEnvelope(simlog,model)

phys=[model '/Subsystem'];

blocks={ ...
    [phys '/CIP_P_FlowSource2']; ...
    [phys '/CIP_V1_InletValve']; ...
    [phys '/CIP_RP_FlowSource']; ...
    [phys '/CIP_V3_ReturnValve']; ...
    [phys '/PSPipeFlow Resistance (TL)']; ...
    [phys '/PS_P1_FlowSource']; ...
    [phys '/PS_V2_ToTanksValve']; ...
    [phys '/V001_InletValve']; ...
    [phys '/Prod_RP_FlowSource']; ...
    [phys '/Prod_V2_ToFillingLine3']; ...
    [phys '/TK1'] ...
    };

minT=Inf; maxT=-Inf;
minP=Inf; maxP=-Inf;
pass=true;
badBlock="";

for i=1:numel(blocks)

    node=simscape.logging.findNode(simlog,blocks{i});

    if isempty(node)
        pass=false;
        if strlength(badBlock)==0, badBlock=string(blocks{i}); end
        continue;
    end

    ports={'A','B'};

    for j=1:2
        port=ports{j};

        try
            Tv=double(values(node.(port).T.series,'Units','K'));
            Tv=Tv(:);

            minT=min(minT,min(Tv));
            maxT=max(maxT,max(Tv));

            if any(~isfinite(Tv)) || any(Tv<273.16) || any(Tv>342.0)
                pass=false;
                if strlength(badBlock)==0, badBlock=string(blocks{i}); end
            end
        catch
            % Not every Simscape node exposes temperature on both ports.
        end

        try
            Pv=double(values(node.(port).p.series,'Units','MPa'));
            Pv=Pv(:);

            minP=min(minP,min(Pv));
            maxP=max(maxP,max(Pv));

            % Broad numerical sanity envelope, not plant design pressure.
            if any(~isfinite(Pv)) || any(Pv<=0.0) || any(Pv>5.0)
                pass=false;
                if strlength(badBlock)==0, badBlock=string(blocks{i}); end
            end
        catch
        end
    end
end

if isinf(minT),minT=NaN;end
if isinf(maxT),maxT=NaN;end
if isinf(minP),minP=NaN;end
if isinf(maxP),maxP=NaN;end
end

function y = normalizePressureMeasured(raw,trueGauge,tg,faultStart)

y = raw(:);

finiteRaw = y(isfinite(y));
if isempty(finiteRaw)
    return;
end

medAbs = median(abs(finiteRaw),'omitnan');

% Resolve common engineering-unit representations.
if medAbs < 5
    % Likely MPa.
    y = y*1e6;
elseif medAbs < 500
    % Likely kPa.
    y = y*1e3;
end

% Use an unaffected prefix to resolve absolute Pa versus gauge Pa.
prefixEnd = min(300,max(30,faultStart-30));
idx = tg<=prefixEnd & isfinite(y) & isfinite(trueGauge);

if any(idx)
    offset = median(y(idx)-trueGauge(idx),'omitnan');

    % Absolute-pressure logger differs from gauge by approximately 101325 Pa.
    if abs(offset-101325) < 25000
        y = y-101325;
    end
end
end

function M = emptyManifest()
M = table( ...
    strings(0,1),zeros(0,1),strings(0,1),zeros(0,1),zeros(0,1), ...
    zeros(0,1),zeros(0,1),zeros(0,1),zeros(0,1),zeros(0,1), ...
    false(0,1),false(0,1),zeros(0,1),zeros(0,1),strings(0,1), ...
    false(0,1),false(0,1),false(0,1), ...
    zeros(0,1),zeros(0,1),zeros(0,1),zeros(0,1),strings(0,1), ...
    strings(0,1),strings(0,1),strings(0,1), ...
    'VariableNames',{ ...
    'run_id','fault_code','fault_name','replicate','seed', ...
    'fault_severity','fault_start_s','fault_end_s', ...
    'initial_level_m','initial_temperature_K', ...
    'simulation_ok','quick_qa_pass','rows_exported', ...
    'fault_active_samples','modes_reached','mode7_present', ...
    'property_envelope_pass','measured_contract_pass', ...
    'critical_min_temperature_K','critical_max_temperature_K', ...
    'critical_min_pressure_MPa','critical_max_pressure_MPa', ...
    'first_bad_critical_block', ...
    'last_warning','error_text','csv_file'});
end

function row = manifestRow(runID,code,name,rep,seed,severity, ...
    faultStart,faultEnd,initLevel,initTemp,simOK,quickQAPass, ...
    rowsExported,faultActiveSamples,modesReachedText,mode7Present, ...
    propertyEnvelopePass,measuredContractPass, ...
    criticalMinT,criticalMaxT,criticalMinP,criticalMaxP,criticalBadBlock, ...
    warningText,errText,csvFile)

row = table( ...
    string(runID),code,string(name),rep,seed,severity,faultStart,faultEnd, ...
    initLevel,initTemp,logical(simOK),logical(quickQAPass),rowsExported, ...
    faultActiveSamples,string(modesReachedText),logical(mode7Present), ...
    logical(propertyEnvelopePass),logical(measuredContractPass), ...
    criticalMinT,criticalMaxT,criticalMinP,criticalMaxP, ...
    string(criticalBadBlock),string(warningText),string(errText), ...
    string(csvFile), ...
    'VariableNames',{ ...
    'run_id','fault_code','fault_name','replicate','seed', ...
    'fault_severity','fault_start_s','fault_end_s', ...
    'initial_level_m','initial_temperature_K', ...
    'simulation_ok','quick_qa_pass','rows_exported', ...
    'fault_active_samples','modes_reached','mode7_present', ...
    'property_envelope_pass','measured_contract_pass', ...
    'critical_min_temperature_K','critical_max_temperature_K', ...
    'critical_min_pressure_MPa','critical_max_pressure_MPa', ...
    'first_bad_critical_block', ...
    'last_warning','error_text','csv_file'});
end

function M = upsertManifest(M,row)
if isempty(M)
    M=row;
    return;
end

idx = string(M.run_id)==string(row.run_id);

if any(idx)
    M(idx,:) = row;
else
    M = [M;row];
end
end

function s = tfstr(x)
if x
    s='PASS';
else
    s='FAIL/REVIEW';
end
end
