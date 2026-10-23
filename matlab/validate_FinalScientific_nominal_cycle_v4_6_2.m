%% validate_FinalScientific_nominal_cycle_v4_6_2.m
% Final Scientific v4.6.2 — 9000-s healthy nominal acceptance validation
% R2025b FIX: uses time(series) / values(series,'Units',unit).
%
% Run ONLY after validate_CIP_transitions_v4_6_2.m passes.
%
% Acceptance gates:
% - process reaches full sequence 1->2->3->4->5->6->0
% - Mode 7 absent
% - TK1 temperature 273.16–342 K
% - maximum level <= 1.60 m
% - nominal fill/product/CIP full-flow plateaus near 10 kg/s
% - CIP circulation drift <= 0.10 m
% - final drain <= 0.07 m (+ small numerical tolerance)
% - no product-discharge/CIP flow overlap
% - critical TL ports stay physically sane
% - agitator tracking error < 1 rpm when both command and measured
%   agitator signals are available

clear; clc;

%% ------------------------------------------------------------------------
% Paths / model
% -------------------------------------------------------------------------
thisScript = mfilename('fullpath');
matlabDir = fileparts(thisScript);
projectRoot = fileparts(matlabDir);

model = 'AlKaseeh_PhysicalTwin_PM_FinalScientific_v4_6_2';
modelFile = fullfile(projectRoot,'models',[model '.slx']);

if ~isfile(modelFile)
    error('v4.6.2 model not found:\n%s',modelFile);
end

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

%% ------------------------------------------------------------------------
% Healthy deterministic nominal setup
% -------------------------------------------------------------------------
set_param([model '/ALK_FaultCode'],'Value','0');
set_param([model '/ALK_FaultSeverity'],'Value','0');
set_param([model '/ALK_FaultStart'],'Value','0');
set_param([model '/ALK_FaultEnd'],'Value','9000');

set_param([model '/Subsystem/TK1'],'level','0.2');
set_param([model '/Subsystem/TK1'],'T_I','300');

set_param(model,'StopTime','9000');
set_param(model,'SimscapeLogType','all');
set_param(model,'SimscapeLogName','simlog_v462_nominal');
% IMPORTANT: retain complete physical history for the full 9000-s run.
% Simscape otherwise limits logging to the last N solver steps by default.
set_param(model,'SimscapeLogLimitData','off');
set_param(model,'SimscapeLogDecimation',1);

fprintf('Running Final Scientific v4.6.2 9000-s nominal validation...\n\n');

lastwarn('');
simOut = sim(model);
[lastWarnMsg,~] = lastwarn;

simlog = simscape.logging.getSimulationLog(model);
if isempty(simlog)
    error('No Simscape log was produced.');
end

%% ------------------------------------------------------------------------
% Mode
% -------------------------------------------------------------------------
modeTS = getSignalCandidates(simOut, ...
    {'process_mode','Mode','ALK_Mode','ProcessMode','mode'});

if isempty(modeTS)
    error(['Could not locate process-mode signal. ' ...
           'Expected process_mode / Mode / ALK_Mode / ProcessMode.']);
end

modeT = double(modeTS.Time(:));
modeV = round(double(modeTS.Data(:)));

modesReached = unique(modeV(isfinite(modeV)))';
requiredModes = [0 1 2 3 4 5 6];

allModesPass = all(ismember(requiredModes,modesReached));
mode7Pass = ~any(modeV == 7);

sequencePass = orderedModeSequencePass(modeV,[1 2 3 4 5 6 0]);

%% ------------------------------------------------------------------------
% Physical nodes
% -------------------------------------------------------------------------
phys = [model '/Subsystem'];

fillNode   = requireNode(simlog,[phys '/PS_P1_FlowSource']);
prodNode   = requireNode(simlog,[phys '/Prod_RP_FlowSource']);
cipSupNode = requireNode(simlog,[phys '/CIP_P_FlowSource2']);
cipRetNode = requireNode(simlog,[phys '/CIP_RP_FlowSource']);
tk1Node    = requireNode(simlog,[phys '/TK1']);

fillTS   = fillNode.M.series;
prodTS   = prodNode.M.series;
cipSupTS = cipSupNode.M.series;
cipRetTS = cipRetNode.M.series;
levelTS  = tk1Node.level.series;
tempTS   = tk1Node.T_out.series;

fillV = valuesIn(fillTS,'kg/s');
prodV = valuesIn(prodTS,'kg/s');
cipSupV = valuesIn(cipSupTS,'kg/s');
cipRetV = valuesIn(cipRetTS,'kg/s');
levelV = valuesIn(levelTS,'m');
tempV = valuesIn(tempTS,'K');

fillT = double(time(fillTS)); fillT = fillT(:);
prodT = double(time(prodTS)); prodT = prodT(:);
cipSupT = double(time(cipSupTS)); cipSupT = cipSupT(:);
cipRetT = double(time(cipRetTS)); cipRetT = cipRetT(:);
levelT = double(time(levelTS)); levelT = levelT(:);

fprintf('Simscape logging coverage:\n');
fprintf('  Fill source:    %.3f -> %.3f s (%d points)\n', ...
    fillT(1),fillT(end),numel(fillT));
fprintf('  Product source: %.3f -> %.3f s (%d points)\n', ...
    prodT(1),prodT(end),numel(prodT));
fprintf('  CIP supply:     %.3f -> %.3f s (%d points)\n', ...
    cipSupT(1),cipSupT(end),numel(cipSupT));
fprintf('  CIP return:     %.3f -> %.3f s (%d points)\n', ...
    cipRetT(1),cipRetT(end),numel(cipRetT));
fprintf('  TK1 level:      %.3f -> %.3f s (%d points)\n\n', ...
    levelT(1),levelT(end),numel(levelT));

fullHistoryPass = ...
    fillT(1) <= 1.0 && fillT(end) >= 8999.0 && ...
    prodT(1) <= 1.0 && prodT(end) >= 8999.0 && ...
    cipSupT(1) <= 1.0 && cipSupT(end) >= 8999.0 && ...
    cipRetT(1) <= 1.0 && cipRetT(end) >= 8999.0 && ...
    levelT(1) <= 1.0 && levelT(end) >= 8999.0;

if ~fullHistoryPass
    error(['Simscape full-history logging check failed. ' ...
           'Do not interpret the physical validation metrics.']);
end

%% ------------------------------------------------------------------------
% Full-flow plateau metrics
% -------------------------------------------------------------------------
fillMedian = medianOrNaN(abs(fillV(abs(fillV)>=9.0)));
prodMedian = medianOrNaN(abs(prodV(abs(prodV)>=9.0)));
cipSupMedian = medianOrNaN(abs(cipSupV(abs(cipSupV)>=9.0)));
cipRetMedian = medianOrNaN(abs(cipRetV(abs(cipRetV)>=9.0)));

fillPass = isfinite(fillMedian) && fillMedian >= 9.5;
productPass = isfinite(prodMedian) && prodMedian >= 9.5;
cipSupplyPass = isfinite(cipSupMedian) && cipSupMedian >= 9.5;
cipReturnPass = isfinite(cipRetMedian) && cipRetMedian >= 9.5;

%% ------------------------------------------------------------------------
% Tank level / temperature
% -------------------------------------------------------------------------
minimumLevel = min(levelV);
maximumLevel = max(levelV);

levelPass = all(isfinite(levelV)) && ...
            minimumLevel >= 0.0 && ...
            maximumLevel <= 1.60;

minimumTemperature = min(tempV);
maximumTemperature = max(tempV);

thermalPass = all(isfinite(tempV)) && ...
              minimumTemperature >= 273.16 && ...
              maximumTemperature <= 342.0;

modeAtLevel = interp1(modeT,modeV,levelT,'previous','extrap');
mode5 = modeAtLevel == 5;
mode6 = modeAtLevel == 6;

if any(mode5)
    cipDrift = max(levelV(mode5))-min(levelV(mode5));
else
    cipDrift = NaN;
end

if any(mode6)
    finalDrain = min(levelV(mode6));
else
    finalDrain = NaN;
end

cipBalancePass = isfinite(cipDrift) && cipDrift <= 0.10;
cipDrainPass = isfinite(finalDrain) && finalDrain <= 0.07 + 1e-3;

%% ------------------------------------------------------------------------
% Product / CIP overlap
% -------------------------------------------------------------------------
tCommon = unique([prodT; cipSupT; cipRetT]);

prodCommon = interp1(prodT,prodV,tCommon,'previous','extrap');
cipSupCommon = interp1(cipSupT,cipSupV,tCommon,'previous','extrap');
cipRetCommon = interp1(cipRetT,cipRetV,tCommon,'previous','extrap');

cipCommon = max(abs(cipSupCommon),abs(cipRetCommon));
overlapMask = (abs(prodCommon)>1e-3) & (cipCommon>1e-3);

if any(overlapMask)
    maxOverlap = max(min(abs(prodCommon(overlapMask)),cipCommon(overlapMask)));
else
    maxOverlap = 0.0;
end

overlapPass = maxOverlap < 1e-3;

%% ------------------------------------------------------------------------
% Critical Thermal Liquid envelope
% -------------------------------------------------------------------------
criticalBlocks = { ...
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

[propertyEnvelopePass,minCriticalT,maxCriticalT, ...
 minCriticalP,maxCriticalP,badPropertyBlock] = ...
    checkCriticalEnvelope(simlog,criticalBlocks);

lastWarningLooksLikeAssertion = ...
    contains(lower(lastWarnMsg),'assertion') || ...
    contains(lower(lastWarnMsg),'maximum valid pressure') || ...
    contains(lower(lastWarnMsg),'minimum valid temperature');

warningScreenPass = ~lastWarningLooksLikeAssertion;

%% ------------------------------------------------------------------------
% Agitator tracking
% -------------------------------------------------------------------------
cmdTS = getSignalCandidates(simOut, ...
    {'AgitatorRPM','Agitator_RPM_Command','AgitatorRPMCmd', ...
     'outv9_agitator_cmd'});

measTS = getSignalCandidates(simOut, ...
    {'M1_RPM','AgitatorRPM_Measured','Agitator_RPM', ...
     'MeasuredAgitatorRPM'});

agitatorSignalAvailable = ~isempty(cmdTS) && ~isempty(measTS);
agitatorTrackingError = NaN;

if agitatorSignalAvailable

    tc = double(cmdTS.Time(:));
    cv = double(cmdTS.Data(:));
    tm = double(measTS.Time(:));
    mv = double(measTS.Data(:));

    tAg = unique([tc;tm]);

    cAg = interp1(tc,cv,tAg,'previous','extrap');
    mAg = interp1(tm,mv,tAg,'linear','extrap');

    active = abs(cAg) >= 10.0;

    if any(active)
        agitatorTrackingError = median(abs(mAg(active)-cAg(active)),'omitnan');
    end
end

% Missing logging does not invalidate the physical cycle, but is reported.
if agitatorSignalAvailable && isfinite(agitatorTrackingError)
    agitatorTrackingPass = agitatorTrackingError < 1.0;
else
    agitatorTrackingPass = true;
end

%% ------------------------------------------------------------------------
% Overall
% -------------------------------------------------------------------------
overallPass = ...
    allModesPass && ...
    mode7Pass && ...
    sequencePass && ...
    fillPass && ...
    productPass && ...
    cipSupplyPass && ...
    cipReturnPass && ...
    levelPass && ...
    thermalPass && ...
    cipBalancePass && ...
    cipDrainPass && ...
    overlapPass && ...
    propertyEnvelopePass && ...
    warningScreenPass && ...
    agitatorTrackingPass;

R = table( ...
    overallPass, ...
    allModesPass, ...
    sequencePass, ...
    mode7Pass, ...
    fillPass, ...
    productPass, ...
    cipSupplyPass, ...
    cipReturnPass, ...
    levelPass, ...
    thermalPass, ...
    cipBalancePass, ...
    cipDrainPass, ...
    overlapPass, ...
    propertyEnvelopePass, ...
    warningScreenPass, ...
    agitatorSignalAvailable, ...
    agitatorTrackingPass, ...
    fillMedian, ...
    prodMedian, ...
    cipSupMedian, ...
    cipRetMedian, ...
    minimumLevel, ...
    maximumLevel, ...
    minimumTemperature, ...
    maximumTemperature, ...
    cipDrift, ...
    finalDrain, ...
    maxOverlap, ...
    agitatorTrackingError, ...
    minCriticalT, ...
    maxCriticalT, ...
    minCriticalP, ...
    maxCriticalP, ...
    string(badPropertyBlock), ...
    'VariableNames',{ ...
    'overall_pass', ...
    'modes_0_to_6_reached', ...
    'ordered_sequence_pass', ...
    'mode7_absent', ...
    'fill_flow_pass', ...
    'product_discharge_flow_pass', ...
    'cip_supply_flow_pass', ...
    'cip_return_flow_pass', ...
    'level_range_pass', ...
    'thermal_range_pass', ...
    'cip_balance_pass', ...
    'cip_final_drain_pass', ...
    'product_cip_overlap_pass', ...
    'property_envelope_pass', ...
    'assertion_warning_screen_pass', ...
    'agitator_signals_available', ...
    'agitator_tracking_pass', ...
    'fill_median_abs_flow_kg_s', ...
    'product_discharge_median_abs_flow_kg_s', ...
    'cip_supply_median_abs_flow_kg_s', ...
    'cip_return_median_abs_flow_kg_s', ...
    'minimum_level_m', ...
    'maximum_level_m', ...
    'minimum_temperature_K', ...
    'maximum_temperature_K', ...
    'cip_circulation_level_drift_m', ...
    'cip_final_drain_min_level_m', ...
    'maximum_product_cip_overlap_kg_s', ...
    'agitator_median_tracking_error_rpm', ...
    'minimum_critical_port_temperature_K', ...
    'maximum_critical_port_temperature_K', ...
    'minimum_critical_port_pressure_MPa', ...
    'maximum_critical_port_pressure_MPa', ...
    'first_bad_property_block'});

disp(R);

fprintf('\nModes reached: %s\n',mat2str(modesReached));
fprintf('Full-flow medians [fill / product / CIP supply / CIP return]:\n');
fprintf('  %.4f / %.4f / %.4f / %.4f kg/s\n', ...
    fillMedian,prodMedian,cipSupMedian,cipRetMedian);
fprintf('Level range: %.4f -> %.4f m\n',minimumLevel,maximumLevel);
fprintf('Temperature range: %.4f -> %.4f K\n', ...
    minimumTemperature,maximumTemperature);
fprintf('CIP circulation drift: %.4f m\n',cipDrift);
fprintf('CIP final drain: %.4f m\n',finalDrain);
fprintf('Critical TL pressure range: %.6f -> %.6f MPa\n', ...
    minCriticalP,maxCriticalP);
fprintf('Critical TL temperature range: %.4f -> %.4f K\n', ...
    minCriticalT,maxCriticalT);

if agitatorSignalAvailable
    fprintf('Agitator median tracking error: %.4f rpm\n', ...
        agitatorTrackingError);
else
    fprintf(['Agitator tracking signals were not found by the validator; ' ...
             'cycle acceptance is reported without that optional log check.\n']);
end

if strlength(string(badPropertyBlock)) > 0
    fprintf('First bad property-envelope block: %s\n',badPropertyBlock);
end

if overallPass
    fprintf('\n*** v4.6.2 FINAL NOMINAL CYCLE VALIDATION PASSED ***\n');
    fprintf('NEXT GATE: 38-run smoke campaign only.\n');
else
    fprintf('\n*** v4.6.2 FINAL NOMINAL CYCLE VALIDATION FAILED ***\n');
    fprintf('Do NOT run the campaign.\n');
end

%% ========================================================================
% Helpers
% ========================================================================
function node = requireNode(simlog,path)
node = simscape.logging.findNode(simlog,path);
if isempty(node)
    error('Required Simscape node not found:\n%s',path);
end
end

function v = valuesIn(seriesObj,unit)
v = double(values(seriesObj,'Units',unit));
v = v(:);
end

function m = medianOrNaN(v)
if isempty(v)
    m = NaN;
else
    m = median(v,'omitnan');
end
end

function pass = orderedModeSequencePass(modeV,expected)

% Collapse consecutive repetitions.
if isempty(modeV)
    pass = false;
    return;
end

v = modeV(:);
keep = [true; diff(v)~=0];
collapsed = v(keep);

% Find expected sequence as ordered subsequence.
pos = 1;
for i=1:numel(collapsed)
    if pos <= numel(expected) && collapsed(i)==expected(pos)
        pos = pos+1;
    end
end

pass = pos > numel(expected);
end

function ts = getSignalCandidates(simOut,candidates)
ts = [];
for i=1:numel(candidates)

    name = candidates{i};

    try
        candidate = simOut.get(name);
        if isa(candidate,'timeseries')
            ts = candidate;
            return;
        end
    catch
    end

    try
        logsout = simOut.logsout;
        el = logsout.get(name);
        if ~isempty(el) && isa(el.Values,'timeseries')
            ts = el.Values;
            return;
        end
    catch
    end

    try
        candidate = evalin('base',name);
        if isa(candidate,'timeseries')
            ts = candidate;
            return;
        end
    catch
    end
end
end

function [pass,minT,maxT,minP,maxP,badBlock] = ...
    checkCriticalEnvelope(simlog,blocks)

minT = Inf;
maxT = -Inf;
minP = Inf;
maxP = -Inf;
pass = true;
badBlock = '';

for i=1:numel(blocks)

    node = simscape.logging.findNode(simlog,blocks{i});

    if isempty(node)
        pass = false;
        if isempty(badBlock), badBlock = blocks{i}; end
        continue;
    end

    ports = {'A','B'};

    for j=1:2

        port = ports{j};

        try
            Tv = double(values(node.(port).T.series,'Units','K'));
            Tv = Tv(:);
            minT = min(minT,min(Tv));
            maxT = max(maxT,max(Tv));

            if any(~isfinite(Tv)) || any(Tv < 273.16) || any(Tv > 342.0)
                pass = false;
                if isempty(badBlock), badBlock = blocks{i}; end
            end
        catch
        end

        try
            Pv = double(values(node.(port).p.series,'Units','MPa'));
            Pv = Pv(:);
            minP = min(minP,min(Pv));
            maxP = max(maxP,max(Pv));

            % Broad numerical sanity envelope, not plant design pressure.
            if any(~isfinite(Pv)) || any(Pv <= 0.0) || any(Pv > 5.0)
                pass = false;
                if isempty(badBlock), badBlock = blocks{i}; end
            end
        catch
        end
    end
end

if isinf(minT), minT = NaN; end
if isinf(maxT), maxT = NaN; end
if isinf(minP), minP = NaN; end
if isinf(maxP), maxP = NaN; end
end
