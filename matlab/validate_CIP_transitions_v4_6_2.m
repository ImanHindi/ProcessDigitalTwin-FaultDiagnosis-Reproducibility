%% validate_CIP_transitions_v4_6_2.m
% Final Scientific v4.6.2 — Full CIP thermal/hydraulic validation
% R2025b FIX: uses time(series) / values(series,'Units',unit).
%
% Model:
%   AlKaseeh_PhysicalTwin_PM_FinalScientific_v4_6_2.slx
%
% Purpose:
%   Validate the corrected shared CIP inlet route over the complete batch:
%   - process reaches Modes 4,5,6 and completes to Mode 0
%   - Mode 7 is absent
%   - product discharge flow is established
%   - CIP supply and return flows are established and balanced
%   - CIP circulation tank-level drift is small
%   - final CIP drain reaches <= 0.07 m
%   - no product-discharge/CIP hydraulic overlap
%   - TK1 bulk temperature remains within 273.16–342 K
%   - critical TL ports remain in a broad physically sane pressure/
%     temperature envelope, preventing the v4.6.1 blocked-route defect
%
% This validator DOES NOT modify model physics or controller logic.

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
set_param([model '/ALK_FaultEnd'],'Value','7200');

set_param([model '/Subsystem/TK1'],'level','0.2');
set_param([model '/Subsystem/TK1'],'T_I','300');

set_param(model,'StopTime','7200');
set_param(model,'SimscapeLogType','all');
set_param(model,'SimscapeLogName','simlog_v462_CIP');
% IMPORTANT: retain complete physical history for the full 7200-s run.
% Simscape otherwise limits logging to the last N solver steps by default.
set_param(model,'SimscapeLogLimitData','off');
set_param(model,'SimscapeLogDecimation',1);

fprintf('Running Final Scientific v4.6.2 full CIP validation...\n\n');

lastwarn('');
simOut = sim(model);
[lastWarnMsg,~] = lastwarn;

simlog = simscape.logging.getSimulationLog(model);
if isempty(simlog)
    error('No Simscape log was produced.');
end

%% ------------------------------------------------------------------------
% Retrieve process mode
% -------------------------------------------------------------------------
modeTS = getSignalCandidates(simOut, ...
    {'process_mode','Mode','ALK_Mode','ProcessMode','mode'});

if isempty(modeTS)
    error(['Could not locate the logged process-mode signal. ' ...
           'Expected one of: process_mode, Mode, ALK_Mode, ProcessMode.']);
end

modeT = double(modeTS.Time(:));
modeV = round(double(modeTS.Data(:)));

modesReached = unique(modeV(isfinite(modeV)))';
requiredModes = [0 4 5 6];

modesPass = all(ismember(requiredModes,modesReached));
mode7Pass = ~any(modeV == 7);

%% ------------------------------------------------------------------------
% Retrieve physical nodes
% -------------------------------------------------------------------------
phys = [model '/Subsystem'];

fillNode = requireNode(simlog,[phys '/PS_P1_FlowSource']);
prodNode = requireNode(simlog,[phys '/Prod_RP_FlowSource']);
cipSupNode = requireNode(simlog,[phys '/CIP_P_FlowSource2']);
cipRetNode = requireNode(simlog,[phys '/CIP_RP_FlowSource']);
tk1Node = requireNode(simlog,[phys '/TK1']);

prodFlowTS = prodNode.M.series;
cipSupTS   = cipSupNode.M.series;
cipRetTS   = cipRetNode.M.series;
levelTS    = tk1Node.level.series;
tempTS     = tk1Node.T_out.series;

prodFlow = valuesIn(prodFlowTS,'kg/s');
cipSup   = valuesIn(cipSupTS,'kg/s');
cipRet   = valuesIn(cipRetTS,'kg/s');
levelV   = valuesIn(levelTS,'m');
tempV    = valuesIn(tempTS,'K');

prodT = double(time(prodFlowTS)); prodT = prodT(:);
cipSupT = double(time(cipSupTS)); cipSupT = cipSupT(:);
cipRetT = double(time(cipRetTS)); cipRetT = cipRetT(:);
levelT = double(time(levelTS)); levelT = levelT(:);
tempT = double(time(tempTS)); tempT = tempT(:);

fprintf('Simscape logging coverage:\n');
fprintf('  Product source: %.3f -> %.3f s (%d points)\n', ...
    prodT(1),prodT(end),numel(prodT));
fprintf('  CIP supply:     %.3f -> %.3f s (%d points)\n', ...
    cipSupT(1),cipSupT(end),numel(cipSupT));
fprintf('  CIP return:     %.3f -> %.3f s (%d points)\n', ...
    cipRetT(1),cipRetT(end),numel(cipRetT));
fprintf('  TK1 level:      %.3f -> %.3f s (%d points)\n\n', ...
    levelT(1),levelT(end),numel(levelT));

fullHistoryPass = ...
    prodT(1) <= 1.0 && prodT(end) >= 7199.0 && ...
    cipSupT(1) <= 1.0 && cipSupT(end) >= 7199.0 && ...
    cipRetT(1) <= 1.0 && cipRetT(end) >= 7199.0 && ...
    levelT(1) <= 1.0 && levelT(end) >= 7199.0;

if ~fullHistoryPass
    error(['Simscape full-history logging check failed. ' ...
           'Do not interpret the physical validation metrics.']);
end

%% ------------------------------------------------------------------------
% Flow performance
% Established-flow medians use samples >= 90% nominal to avoid counting ramps.
% -------------------------------------------------------------------------
prodEstablished = abs(prodFlow) >= 9.0;
cipSupEstablished = abs(cipSup) >= 9.0;
cipRetEstablished = abs(cipRet) >= 9.0;

prodMedian = medianOrNaN(abs(prodFlow(prodEstablished)));
cipSupMedian = medianOrNaN(abs(cipSup(cipSupEstablished)));
cipRetMedian = medianOrNaN(abs(cipRet(cipRetEstablished)));

productFlowPass = isfinite(prodMedian) && prodMedian >= 9.5;
cipSupplyFlowPass = isfinite(cipSupMedian) && cipSupMedian >= 9.5;
cipReturnFlowPass = isfinite(cipRetMedian) && cipRetMedian >= 9.5;

%% ------------------------------------------------------------------------
% Mode-aligned TK1 level metrics
% -------------------------------------------------------------------------
modeAtLevel = interp1(modeT,modeV,levelT,'previous','extrap');

mode5 = modeAtLevel == 5;
mode6 = modeAtLevel == 6;

if any(mode5)
    cipCirculationLevelDrift = max(levelV(mode5)) - min(levelV(mode5));
else
    cipCirculationLevelDrift = NaN;
end

if any(mode6)
    cipDrainMinLevel = min(levelV(mode6));
else
    cipDrainMinLevel = NaN;
end

cipBalancePass = isfinite(cipCirculationLevelDrift) && ...
                 cipCirculationLevelDrift <= 0.10;

cipDrainPass = isfinite(cipDrainMinLevel) && ...
               cipDrainMinLevel <= 0.07 + 1e-3;

%% ------------------------------------------------------------------------
% Product-vs-CIP overlap using physical imposed-flow commands
% -------------------------------------------------------------------------
tCommon = unique([prodT; cipSupT; cipRetT]);

prodCommon = interp1(prodT,prodFlow,tCommon,'previous','extrap');
cipSupCommon = interp1(cipSupT,cipSup,tCommon,'previous','extrap');
cipRetCommon = interp1(cipRetT,cipRet,tCommon,'previous','extrap');

cipCommon = max(abs(cipSupCommon),abs(cipRetCommon));

overlapMask = (abs(prodCommon) > 1e-3) & (cipCommon > 1e-3);

if any(overlapMask)
    maximumOverlap = max(min(abs(prodCommon(overlapMask)),cipCommon(overlapMask)));
else
    maximumOverlap = 0.0;
end

commandOverlapPass = maximumOverlap < 1e-3;

%% ------------------------------------------------------------------------
% TK1 bulk thermal range
% -------------------------------------------------------------------------
minimumTankTemperature = min(tempV);
peakTankTemperature = max(tempV);

thermalRangePass = ...
    all(isfinite(tempV)) && ...
    minimumTankTemperature >= 273.16 && ...
    peakTankTemperature <= 342.0;

%% ------------------------------------------------------------------------
% Critical Thermal Liquid property-envelope sanity check
%
% This is intentionally broad. It is not a plant pressure acceptance limit.
% It exists to reject impossible numerical states such as the v4.6.1
% 1.3e7 MPa / negative-hundreds-of-thousands-K blocked-route state.
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

[propertyEnvelopePass, minCriticalT, maxCriticalT, ...
 minCriticalP, maxCriticalP, badPropertyBlock] = ...
    checkCriticalEnvelope(simlog,criticalBlocks);

% Secondary indication from MATLAB warning stack.
lastWarningLooksLikeAssertion = ...
    contains(lower(lastWarnMsg),'assertion') || ...
    contains(lower(lastWarnMsg),'maximum valid pressure') || ...
    contains(lower(lastWarnMsg),'minimum valid temperature');

warningScreenPass = ~lastWarningLooksLikeAssertion;

%% ------------------------------------------------------------------------
% Overall
% -------------------------------------------------------------------------
overallPass = ...
    modesPass && ...
    mode7Pass && ...
    productFlowPass && ...
    cipSupplyFlowPass && ...
    cipReturnFlowPass && ...
    cipBalancePass && ...
    cipDrainPass && ...
    commandOverlapPass && ...
    thermalRangePass && ...
    propertyEnvelopePass && ...
    warningScreenPass;

R = table( ...
    overallPass, ...
    modesPass, ...
    mode7Pass, ...
    productFlowPass, ...
    cipSupplyFlowPass, ...
    cipReturnFlowPass, ...
    cipBalancePass, ...
    cipDrainPass, ...
    commandOverlapPass, ...
    thermalRangePass, ...
    propertyEnvelopePass, ...
    warningScreenPass, ...
    prodMedian, ...
    cipSupMedian, ...
    cipRetMedian, ...
    cipCirculationLevelDrift, ...
    cipDrainMinLevel, ...
    maximumOverlap, ...
    minimumTankTemperature, ...
    peakTankTemperature, ...
    minCriticalT, ...
    maxCriticalT, ...
    minCriticalP, ...
    maxCriticalP, ...
    string(badPropertyBlock), ...
    'VariableNames',{ ...
    'overall_pass', ...
    'modes_0_4_5_6_reached', ...
    'mode7_absent', ...
    'product_flow_pass', ...
    'cip_supply_flow_pass', ...
    'cip_return_flow_pass', ...
    'cip_balance_pass', ...
    'cip_drain_pass', ...
    'command_overlap_pass', ...
    'thermal_range_pass', ...
    'property_envelope_pass', ...
    'assertion_warning_screen_pass', ...
    'product_discharge_median_abs_flow_kg_s', ...
    'cip_supply_median_abs_flow_kg_s', ...
    'cip_return_median_abs_flow_kg_s', ...
    'cip_circulation_level_drift_m', ...
    'cip_drain_min_level_m', ...
    'maximum_product_vs_cip_flow_overlap_kg_s', ...
    'minimum_tank_temperature_K', ...
    'peak_tank_temperature_K', ...
    'minimum_critical_port_temperature_K', ...
    'maximum_critical_port_temperature_K', ...
    'minimum_critical_port_pressure_MPa', ...
    'maximum_critical_port_pressure_MPa', ...
    'first_bad_property_block'});

disp(R);

fprintf('\nModes reached: %s\n',mat2str(modesReached));
fprintf('Product discharge median: %.4f kg/s\n',prodMedian);
fprintf('CIP supply/return median: %.4f / %.4f kg/s\n', ...
    cipSupMedian,cipRetMedian);
fprintf('CIP circulation level drift: %.4f m\n', ...
    cipCirculationLevelDrift);
fprintf('CIP final drain: %.4f m\n',cipDrainMinLevel);
fprintf('TK1 temperature range: %.4f -> %.4f K\n', ...
    minimumTankTemperature,peakTankTemperature);
fprintf('Critical TL temperature range: %.4f -> %.4f K\n', ...
    minCriticalT,maxCriticalT);
fprintf('Critical TL pressure range: %.6f -> %.6f MPa\n', ...
    minCriticalP,maxCriticalP);

if strlength(string(badPropertyBlock)) > 0
    fprintf('First bad property-envelope block: %s\n',badPropertyBlock);
end

if overallPass
    fprintf('\n*** v4.6.2 CIP THERMAL/HYDRAULIC VALIDATION PASSED ***\n');
    fprintf('Next run:\n');
    fprintf('  run(''matlab/validate_FinalScientific_nominal_cycle_v4_6_2.m'')\n');
else
    fprintf('\n*** v4.6.2 CIP THERMAL/HYDRAULIC VALIDATION FAILED ***\n');
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
        if ~isempty(el)
            if isa(el.Values,'timeseries')
                ts = el.Values;
                return;
            end
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
            % Some nodes may not expose both ports/temperature.
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
