%% run_FinalScientific_v4_6_3_development190.m
% Al Kaseeh Final Scientific v4.6.3
% DEVELOPMENT GATE: 190 runs = 10 independent runs x 19 classes.
%
% PHYSICAL MODEL (FROZEN / ACCEPTED):
%   models/AlKaseeh_PhysicalTwin_PM_FinalScientific_v4_6_2.slx
%
% MEASUREMENT LAYER:
%   matlab/ALK_apply_sensor_fault_v4_6_3.m
%
% PURPOSE
% -------
% This is the required development campaign after Smoke38. It is NOT the
% final 1900-run publication campaign.
%
% Scientific design:
% - 19 final classes;
% - 10 independent realizations/class;
% - 9000 s/run;
% - 1-Hz CSV export;
% - deterministic unique run seeds;
% - stratified coverage of initial level, initial temperature and severity;
% - actuator faults are injected inside the accepted Simscape model;
% - sensor faults 101–106 use healthy physical simulation + validated v4.6.3
%   measurement transformation, so physical truth is not corrupted;
% - run-level critical Thermal Liquid property-envelope audit;
% - resumable campaign;
% - no automatic promotion to 1900 runs.
%
% NEXT:
%   run('matlab/qa_FinalScientific_v4_6_3_development190.m')
%
% MATLAB R2025b.

clear; clc;

%% ------------------------------------------------------------------------
% Project / model
% -------------------------------------------------------------------------
thisScript = mfilename('fullpath');
matlabDir = fileparts(thisScript);
projectRoot = fileparts(matlabDir);
addpath(matlabDir);

model = 'AlKaseeh_PhysicalTwin_PM_FinalScientific_v4_6_2';
modelFile = fullfile(projectRoot,'models',[model '.slx']);

if ~isfile(modelFile)
    error('Accepted physical model not found:\n%s',modelFile);
end

sensorLayerFile = fullfile(matlabDir,'ALK_apply_sensor_fault_v4_6_3.m');
if ~isfile(sensorLayerFile)
    error('v4.6.3 sensor layer not found:\n%s',sensorLayerFile);
end

outDir = fullfile(projectRoot,'ml','data', ...
    'final_scientific_v4_6_3','development190');

if ~isfolder(outDir)
    mkdir(outDir);
end

manifestFile = fullfile(outDir,'development190_manifest.csv');
modeWindowFile = fullfile(outDir,'baseline_mode_windows.csv');

%% ------------------------------------------------------------------------
% Build/logging configuration
% -------------------------------------------------------------------------
cacheDir='C:\AKBuild\cache';
codeDir ='C:\AKBuild\codegen';

if ~isfolder(cacheDir),mkdir(cacheDir);end
if ~isfolder(codeDir),mkdir(codeDir);end

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

% Full history retained, but decimated for campaign-memory efficiency.
set_param(model,'SimscapeLogType','all');
set_param(model,'SimscapeLogName','simlog_v463_dev190');
set_param(model,'SimscapeLogLimitData','off');
set_param(model,'SimscapeLogDecimation',20);

%% ------------------------------------------------------------------------
% Final 19-class taxonomy
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

nClasses=numel(faultCodes);
nRep=10;
expectedRuns=nClasses*nRep;

fprintf('============================================================\n');
fprintf('FINAL SCIENTIFIC v4.6.3 — DEVELOPMENT190\n');
fprintf('============================================================\n');
fprintf('Physical model: %s\n',model);
fprintf('Measurement layer: ALK_apply_sensor_fault_v4_6_3\n');
fprintf('Runs: %d classes x %d = %d\n',nClasses,nRep,expectedRuns);
fprintf('Stop time: 9000 s/run\n');
fprintf('Export: 1 Hz\n');
fprintf('Output: %s\n',outDir);
fprintf('============================================================\n\n');

%% ------------------------------------------------------------------------
% Resume support
% -------------------------------------------------------------------------
if isfile(manifestFile)
    manifest=readtable(manifestFile,'TextType','string');
else
    manifest=emptyManifest();
end

baselineCSV=fullfile(outDir,'v463_dev190_fc000_rep01.csv');

if isfile(modeWindowFile)
    modeWindows=readtable(modeWindowFile);
elseif isfile(baselineCSV)
    B=readtable(baselineCSV);
    modeWindows=inferModeWindows(B.time,B.process_mode);
    writetable(modeWindows,modeWindowFile);
else
    modeWindows=table();
end

runCounter=0;

%% ------------------------------------------------------------------------
% Campaign
% -------------------------------------------------------------------------
for c=1:nClasses

    code=faultCodes(c);
    name=faultNames{c};

    for rep=1:nRep

        runCounter=runCounter+1;

        runID=sprintf('v463_dev190_fc%03d_rep%02d',code,rep);
        csvFile=fullfile(outDir,[runID '.csv']);

        if isfile(csvFile)
            fprintf('[%03d/%03d] SKIP existing: %s\n', ...
                runCounter,expectedRuns,runID);

            if code==0 && rep==1 && isempty(modeWindows)
                B=readtable(csvFile);
                modeWindows=inferModeWindows(B.time,B.process_mode);
                writetable(modeWindows,modeWindowFile);
            end
            continue;
        end

        % Unique, deterministic run seed.
        seed=46300000 + c*1000 + rep;
        rng(seed,'twister');

        % Stratified development coverage. These are intentionally broader
        % than Smoke38 but remain within the already discussed v4.6.x range.
        initLevel=stratifiedSample(0.12,0.28,rep,nRep,seed+11);
        initTemp =stratifiedSample(293.15,303.15,rep,nRep,seed+23);
        severity=developmentSeverity(code,rep,nRep,seed+37);

        isSensorFault = code>=101;

        % For actuator/process faults, use broad mode-aware windows inferred
        % from the first healthy development run. FaultActive in the model
        % still limits activity to the affected component's operation.
        if code==0
            faultStart=0.0;
            faultEnd=0.0;
        elseif isSensorFault
            % Actual sensor window is selected AFTER the healthy physical
            % trajectory is available, using that run's process_mode.
            faultStart=0.0;
            faultEnd=0.0;
        else
            if isempty(modeWindows)
                error(['Baseline mode windows unavailable. ' ...
                    'Healthy rep01 must complete first.']);
            end

            [faultStart,faultEnd]=developmentFaultWindow( ...
                code,modeWindows,seed);
        end

        fprintf('\n[%03d/%03d] %s\n',runCounter,expectedRuns,runID);
        fprintf('  class:     %d — %s\n',code,name);
        fprintf('  severity:  %.4f\n',severity);
        fprintf('  init:      level %.4f m, temp %.3f K\n', ...
            initLevel,initTemp);

        if isSensorFault
            fprintf('  physical:  healthy realization; sensor fault post-applied\n');
        else
            fprintf('  fault:     %.1f -> %.1f s\n',faultStart,faultEnd);
        end

        % Sensor faults must not perturb the physical Simscape plant.
        if isSensorFault
            modelFaultCode=0;
            modelSeverity=0.0;
            modelFaultStart=0.0;
            modelFaultEnd=0.0;
        else
            modelFaultCode=code;
            modelSeverity=severity;
            modelFaultStart=faultStart;
            modelFaultEnd=faultEnd;
        end

        set_param([model '/ALK_FaultCode'], ...
            'Value',num2str(modelFaultCode,'%.15g'));
        set_param([model '/ALK_FaultSeverity'], ...
            'Value',num2str(modelSeverity,'%.15g'));
        set_param([model '/ALK_FaultStart'], ...
            'Value',num2str(modelFaultStart,'%.15g'));
        set_param([model '/ALK_FaultEnd'], ...
            'Value',num2str(modelFaultEnd,'%.15g'));

        set_param([model '/Subsystem/TK1'], ...
            'level',num2str(initLevel,'%.15g'));
        set_param([model '/Subsystem/TK1'], ...
            'T_I',num2str(initTemp,'%.15g'));

        simOK=false;
        quickQAPass=false;
        errText="";
        warningText="";
        rowsExported=0;
        faultActiveSamples=0;
        modesReachedText="";
        mode7Present=false;
        propertyEnvelopePass=false;
        measuredContractPass=false;

        criticalMinT=NaN;
        criticalMaxT=NaN;
        criticalMinP=NaN;
        criticalMaxP=NaN;
        criticalBadBlock="";

        try
            lastwarn('');

            simOut=sim(model,'ReturnWorkspaceOutputs','on');

            [wmsg,~]=lastwarn;
            warningText=string(wmsg);

            simlog=simscape.logging.getSimulationLog(model);

            if isempty(simlog)
                error('No Simscape log returned.');
            end

            D=buildExportTable( ...
                simOut,simlog,model,runID,code,name,rep,seed,severity, ...
                faultStart,faultEnd,initLevel,initTemp);

            % First healthy run defines broad actuator fault windows.
            if code==0 && rep==1
                modeWindows=inferModeWindows(D.time,D.process_mode);
                writetable(modeWindows,modeWindowFile);

                if ~all(ismember(0:6,modeWindows.mode))
                    error('Healthy baseline did not reach complete Modes 0–6.');
                end
            end

            % Apply v4.6.3 sensor fault to this run's actual healthy physical
            % realization and actual operating-mode window.
            if isSensorFault
                [faultStart,faultEnd]=sensorWindowFromActualMode( ...
                    code,D.time,D.process_mode,seed);

                D=applySensorFaultToDevelopmentRun( ...
                    D,code,severity,faultStart,faultEnd,seed);

                D.requested_fault_start_s(:)=faultStart;
                D.requested_fault_end_s(:)=faultEnd;

                fprintf('  sensor fault: %.1f -> %.1f s\n', ...
                    faultStart,faultEnd);
            end

            [quickQAPass,q]=quickRunQA(D,code,warningText);

            [criticalPass,criticalMinT,criticalMaxT, ...
                criticalMinP,criticalMaxP,criticalBadBlock]= ...
                criticalTLPropertyEnvelope(simlog,model);

            faultActiveSamples=q.fault_active_samples;
            modesReachedText=string(q.modes_reached);
            mode7Present=q.mode7_present;
            propertyEnvelopePass=q.property_envelope_pass && criticalPass;
            measuredContractPass=q.measured_contract_pass;
            quickQAPass=quickQAPass && criticalPass;

            rowsExported=height(D);
            writetable(D,csvFile);

            simOK=true;

            fprintf('  export:    %d rows\n',rowsExported);
            fprintf('  modes:     %s\n',modesReachedText);
            fprintf('  active:    %d samples\n',faultActiveSamples);
            fprintf('  critical:  T %.2f..%.2f K | P %.4f..%.4f MPa\n', ...
                criticalMinT,criticalMaxT,criticalMinP,criticalMaxP);
            fprintf('  quick QA:  %s\n',tfstr(quickQAPass));

        catch ME

            errText=string(getReport(ME,'basic','hyperlinks','off'));
            fprintf(2,'  *** RUN FAILED ***\n%s\n',errText);

            % Healthy baseline is required for all actuator scheduling.
            if code==0 && rep==1
                row=manifestRow(runID,code,name,rep,seed,severity, ...
                    faultStart,faultEnd,initLevel,initTemp, ...
                    simOK,quickQAPass,rowsExported,faultActiveSamples, ...
                    modesReachedText,mode7Present,propertyEnvelopePass, ...
                    measuredContractPass,criticalMinT,criticalMaxT, ...
                    criticalMinP,criticalMaxP,criticalBadBlock, ...
                    warningText,errText,csvFile);

                manifest=upsertManifest(manifest,row);
                writetable(manifest,manifestFile);
                rethrow(ME);
            end
        end

        row=manifestRow(runID,code,name,rep,seed,severity, ...
            faultStart,faultEnd,initLevel,initTemp, ...
            simOK,quickQAPass,rowsExported,faultActiveSamples, ...
            modesReachedText,mode7Present,propertyEnvelopePass, ...
            measuredContractPass,criticalMinT,criticalMaxT, ...
            criticalMinP,criticalMaxP,criticalBadBlock, ...
            warningText,errText,csvFile);

        manifest=upsertManifest(manifest,row);
        writetable(manifest,manifestFile);

        clear simOut simlog D
        drawnow;
    end
end

fprintf('\n============================================================\n');
fprintf('DEVELOPMENT190 EXECUTION COMPLETE\n');
fprintf('============================================================\n');
fprintf('Manifest:\n  %s\n',manifestFile);
fprintf('\nMANDATORY NEXT GATE:\n');
fprintf('  run(''matlab/qa_FinalScientific_v4_6_3_development190.m'')\n');
fprintf('============================================================\n');

%% ========================================================================
% Development-specific helpers
% ========================================================================

function x=stratifiedSample(lo,hi,rep,nRep,seed)

stream=RandStream('mt19937ar','Seed',double(seed));

binWidth=(hi-lo)/nRep;
left=lo+(rep-1)*binWidth;
right=left+binWidth;

x=left+(right-left)*rand(stream,1,1);

% Keep last-bin roundoff inside the specified range.
x=max(lo,min(hi,x));
end

function severity=developmentSeverity(code,rep,nRep,seed)

if code==0
    severity=0.0;
    return;
end

if code==6
    lo=0.10; hi=0.35;
elseif code>=101
    lo=0.20; hi=0.60;
else
    lo=0.20; hi=0.60;
end

severity=stratifiedSample(lo,hi,rep,nRep,seed);
end

function [t1,t2]=developmentFaultWindow(code,W,seed)

m1=modeBounds(W,1);
m2=modeBounds(W,2);
m3=modeBounds(W,3);
m4=modeBounds(W,4);
m5=modeBounds(W,5);
m6=modeBounds(W,6);

stream=RandStream('mt19937ar','Seed',double(seed+991));
jitter=40*(2*rand(stream,1,1)-1); % ±40 s

switch code

    case {1,3,4}
        % Fill path: broad enough for initial-level variation.
        t1=max(0,m1(1));
        t2=min(9000,m1(2)+220+jitter);

    case {7,8}
        % Heating/mixing: broad enough for initial-temperature and severity
        % induced timing changes while still avoiding the entire cycle.
        t1=max(0,m2(1)+60+jitter);
        t2=min(9000,m2(2)+700+jitter);

    case 6
        % Leakage starts while discharge should still be closed and remains
        % through the discharge transition.
        t1=max(0,m3(1)-200+jitter);
        t2=min(9000,m4(2)+180+jitter);

    case {5,11}
        % Product-discharge path.
        t1=max(0,m4(1)-350+jitter);
        t2=min(9000,m4(2)+400+jitter);

    case {2,9,10,12}
        % Full CIP circulation + transition envelope.
        t1=max(0,m5(1)-450+jitter);
        t2=min(9000,m6(2)+350+jitter);

    otherwise
        error('No actuator development window for code %d.',code);
end

if ~(isfinite(t1)&&isfinite(t2)&&t2>t1)
    error('Invalid development fault window for code %d.',code);
end
end

function [t1,t2]=sensorWindowFromActualMode(code,t,mode,seed)

if code==103
    targetMode=1;
else
    targetMode=2;
end

t=double(t(:));
mode=round(double(mode(:)));

idx=mode==targetMode;

if ~any(idx)
    error('Sensor class %d: required process Mode %d absent.', ...
        code,targetMode);
end

tt=t(idx);
a=min(tt);
b=max(tt);
duration=b-a;

if duration<20
    error('Sensor class %d: operating window too short.',code);
end

stream=RandStream('mt19937ar','Seed',double(seed+1703));

if targetMode==1
    % Filling can be short. Use most of the available mode.
    fracStart=0.05 + 0.10*rand(stream,1,1);
    fracEnd  =0.85 + 0.10*rand(stream,1,1);
else
    % Heating/mixing is long. Randomized central interval provides varied
    % onset and duration while guaranteeing operational relevance.
    fracStart=0.12 + 0.20*rand(stream,1,1);
    fracEnd  =0.62 + 0.20*rand(stream,1,1);
end

t1=a+fracStart*duration;
t2=a+fracEnd*duration;

t1=max(a,min(b-1,t1));
t2=max(t1+1,min(b,t2));
end

function D=applySensorFaultToDevelopmentRun( ...
    D,code,severity,faultStart,faultEnd,seed)

t=double(D.time);

Tbase=double(D.temperature_measured_K);
Lbase=double(D.level_measured_m);
Fbase=double(D.production_mass_flow_measured_kg_s);
Pbase=double(D.gauge_pressure_measured_Pa);
Rbase=double(D.agitator_speed_measured_rpm);

% A missing baseline measurement logger is resolved from physical truth
% BEFORE the validated measurement corruption is applied.
if all(isnan(Tbase))
    Tbase=double(D.temperature_true_K);
end
if all(isnan(Lbase))
    Lbase=double(D.level_true_m);
end
if all(isnan(Fbase))
    Fbase=double(D.production_mass_flow_true_kg_s);
end
if all(isnan(Pbase))
    Pbase=double(D.gauge_pressure_true_Pa);
end

% RPM-noise evaluation requires a reference. If the physical model does not
% expose an explicit true RPM signal, the healthy pre-corruption measured RPM
% trace is retained as the reference for class 105.
if all(isnan(Rbase))
    if code==105
        error('Class 105 cannot run: measured RPM trace is unavailable.');
    else
        Rbase=zeros(size(t));
    end
end

if code==105 && all(isnan(D.agitator_speed_true_rpm))
    D.agitator_speed_true_rpm=Rbase;
end

[Tm,Lm,Fm,Pm,Rm,A]=ALK_apply_sensor_fault_v4_6_3( ...
    t,Tbase,Lbase,Fbase,Pbase,Rbase, ...
    code,severity,faultStart,faultEnd,seed);

D.temperature_measured_K=Tm;
D.level_measured_m=Lm;
D.production_mass_flow_measured_kg_s=Fm;
D.gauge_pressure_measured_Pa=Pm;
D.agitator_speed_measured_rpm=Rm;

D.fault_active=double(A);

D.fault_code(:)=0;
D.sensor_fault_code(:)=0;
D.sensor_fault_code(A)=code;
end

function b=modeBounds(W,modeID)
idx=W.mode==modeID;
if ~any(idx)
    error('Baseline did not contain required Mode %d.',modeID);
end
b=[min(W.start_s(idx)),max(W.end_s(idx))];
end

function W=inferModeWindows(t,m)
t=double(t(:));
m=round(double(m(:)));

good=isfinite(t)&isfinite(m);
t=t(good);
m=m(good);

if isempty(t)
    error('Cannot infer mode windows from empty signal.');
end

change=[true;diff(m)~=0];
starts=find(change);
ends=[starts(2:end)-1;numel(m)];

mode=m(starts);
start_s=t(starts);
end_s=t(ends);

W=table(mode,start_s,end_s);
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
