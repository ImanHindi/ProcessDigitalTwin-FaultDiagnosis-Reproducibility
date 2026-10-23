%% qa_FinalScientific_v4_6_2_smoke38.m
% Mandatory QA gate for the Final Scientific v4.6.2 38-run smoke campaign.
%
% HARD PASS requires:
% - exactly 38 run CSV files;
% - exactly 2 runs for each of the 19 final fault classes;
% - each run covers 0–9000 s at 1-Hz export;
% - all core physical-truth channels are finite;
% - healthy runs cover Modes 0–6 and contain no Mode 7;
% - every nonzero fault has FaultActive samples;
% - each run stays inside the broad physical/numerical envelope;
% - target sensor faults produce measurable measured-vs-true separation;
% - agitator degradation/noise has the required RPM logging evidence.
%
% Outputs:
%   smoke38_QA_summary.csv
%   smoke38_class_summary.csv
%   smoke38_QA_report.txt
%   SMOKE38_READY_FOR_190.txt     only when every hard gate passes
%
% A PASS means the campaign engine/fault taxonomy is ready for the next
% 190-run development gate. It is not final dataset certification.

clear; clc;

thisScript = mfilename('fullpath');
matlabDir = fileparts(thisScript);
projectRoot = fileparts(matlabDir);

dataDir = fullfile(projectRoot,'ml','data', ...
    'final_scientific_v4_6_2','smoke38');

if ~isfolder(dataDir)
    error('Smoke directory does not exist:\n%s',dataDir);
end

summaryFile = fullfile(dataDir,'smoke38_QA_summary.csv');
classFile   = fullfile(dataDir,'smoke38_class_summary.csv');
reportFile  = fullfile(dataDir,'smoke38_QA_report.txt');
readyFile   = fullfile(dataDir,'SMOKE38_READY_FOR_190.txt');

if isfile(readyFile)
    delete(readyFile);
end

faultCodes = [ ...
      0, ...
      1,2,3,4,5,6,7,8,9,10,11,12, ...
      101,102,103,104,105,106];

files = dir(fullfile(dataDir,'v462_smoke_fc*_rep*.csv'));

fprintf('============================================================\n');
fprintf('FINAL SCIENTIFIC v4.6.2 — SMOKE38 QA\n');
fprintf('============================================================\n');
fprintf('CSV files found: %d / 38\n\n',numel(files));

rows = cell(0,24);

for k=1:numel(files)

    path = fullfile(files(k).folder,files(k).name);

    try
        D = readtable(path,'TextType','string');

        required = { ...
            'time','run_id','scenario','target','process_mode', ...
            'fault_active','level_true_m','volume_m3', ...
            'temperature_true_K','gauge_pressure_true_Pa', ...
            'production_mass_flow_true_kg_s', ...
            'product_discharge_mass_flow_true_kg_s', ...
            'cip_supply_mass_flow_true_kg_s', ...
            'cip_return_mass_flow_true_kg_s', ...
            'level_measured_m','temperature_measured_K', ...
            'gauge_pressure_measured_Pa', ...
            'production_mass_flow_measured_kg_s', ...
            'agitator_speed_measured_rpm','cmd_agitator_rpm'};

        schemaPass = all(ismember(required,D.Properties.VariableNames));

        if ~schemaPass
            missing = string(setdiff(required,D.Properties.VariableNames));
            error('Missing required columns: %s',strjoin(missing,', '));
        end

        code = double(D.target(1));
        runID = string(D.run_id(1));

        timePass = height(D)==9001 && ...
            abs(D.time(1))<1e-9 && ...
            abs(D.time(end)-9000)<1e-9 && ...
            all(diff(D.time)>0);

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

        coreFinitePass = all(isfinite(core),'all');

        modes = unique(round(D.process_mode(isfinite(D.process_mode))))';
        modesText = string(mat2str(modes));

        if code==0
            modeCoveragePass = all(ismember(0:6,modes));
            mode7Pass = ~any(round(D.process_mode)==7);
        else
            % Faults may legitimately cause supervisory hold. The smoke hard
            % gate is activation of the intended fault, not completion of all
            % later modes.
            modeCoveragePass = true;
            mode7Pass = true;
        end

        if code==0
            faultActivePass = all((D.fault_active==0) | isnan(D.fault_active));
        else
            faultActivePass = any(D.fault_active>=0.5);
        end

        activeSamples = sum(D.fault_active>=0.5);

        absPressureMPa = (D.gauge_pressure_true_Pa+101325)/1e6;

        propertyPass = ...
            all(D.temperature_true_K>=273.16 & D.temperature_true_K<=342.0) && ...
            all(absPressureMPa>0 & absPressureMPa<5.0) && ...
            all(D.level_true_m>=0 & D.level_true_m<=1.65);

        [measuredPass,evidence,effectValue] = ...
            faultEvidence(D,code);

        noUnexpectedNaNPass = measuredMissingnessPass(D,code);

        overall = ...
            schemaPass && ...
            timePass && ...
            coreFinitePass && ...
            modeCoveragePass && ...
            mode7Pass && ...
            faultActivePass && ...
            propertyPass && ...
            measuredPass && ...
            noUnexpectedNaNPass;

        rows(end+1,:) = { ...
            runID,code,string(files(k).name), ...
            schemaPass,timePass,coreFinitePass, ...
            modeCoveragePass,mode7Pass,faultActivePass, ...
            propertyPass,measuredPass,noUnexpectedNaNPass, ...
            overall,activeSamples,modesText,evidence,effectValue, ...
            min(D.level_true_m),max(D.level_true_m), ...
            min(D.temperature_true_K),max(D.temperature_true_K), ...
            min(absPressureMPa),max(absPressureMPa), ...
            ""}; %#ok<AGROW>

    catch ME

        rows(end+1,:) = { ...
            string(files(k).name),NaN,string(files(k).name), ...
            false,false,false,false,false,false,false,false,false, ...
            false,0,"","QA exception",NaN, ...
            NaN,NaN,NaN,NaN,NaN,NaN,string(ME.message)}; %#ok<AGROW>
    end
end

Q = cell2table(rows,'VariableNames',{ ...
    'run_id','fault_code','csv_file', ...
    'schema_pass','time_coverage_pass','core_finite_pass', ...
    'mode_coverage_pass','mode7_gate_pass','fault_active_pass', ...
    'property_envelope_pass','fault_evidence_pass', ...
    'measured_missingness_pass','overall_pass', ...
    'fault_active_samples','modes_reached','fault_evidence', ...
    'effect_metric','minimum_level_m','maximum_level_m', ...
    'minimum_temperature_K','maximum_temperature_K', ...
    'minimum_absolute_pressure_MPa','maximum_absolute_pressure_MPa', ...
    'qa_error'});

if ~isempty(Q)
    Q = sortrows(Q,{'fault_code','run_id'});
end

% -------------------------------------------------------------------------
% Merge runner-side critical Simscape branch audit.
%
% The CSV-level QA can validate TK1 bulk truth, but the historical v4.6.1
% defect demonstrated that an upstream TL branch can become nonphysical
% while TK1 remains apparently normal. Therefore the final smoke gate also
% requires the per-run critical-port audit recorded in the manifest.
% -------------------------------------------------------------------------
manifestFile = fullfile(dataDir,'smoke38_manifest.csv');

Q.critical_manifest_pass = false(height(Q),1);
Q.simulation_manifest_pass = false(height(Q),1);
Q.critical_min_temperature_K = nan(height(Q),1);
Q.critical_max_temperature_K = nan(height(Q),1);
Q.critical_min_pressure_MPa = nan(height(Q),1);
Q.critical_max_pressure_MPa = nan(height(Q),1);
Q.first_bad_critical_block = strings(height(Q),1);

if isfile(manifestFile)

    M = readtable(manifestFile,'TextType','string');

    requiredManifest = { ...
        'run_id','simulation_ok','property_envelope_pass', ...
        'critical_min_temperature_K','critical_max_temperature_K', ...
        'critical_min_pressure_MPa','critical_max_pressure_MPa', ...
        'first_bad_critical_block'};

    if all(ismember(requiredManifest,M.Properties.VariableNames))

        for i=1:height(Q)

            idx = string(M.run_id)==string(Q.run_id(i));

            if sum(idx)==1

                Q.critical_manifest_pass(i) = logical(M.property_envelope_pass(idx));
                Q.simulation_manifest_pass(i) = logical(M.simulation_ok(idx));

                Q.critical_min_temperature_K(i) = ...
                    double(M.critical_min_temperature_K(idx));
                Q.critical_max_temperature_K(i) = ...
                    double(M.critical_max_temperature_K(idx));
                Q.critical_min_pressure_MPa(i) = ...
                    double(M.critical_min_pressure_MPa(idx));
                Q.critical_max_pressure_MPa(i) = ...
                    double(M.critical_max_pressure_MPa(idx));

                Q.first_bad_critical_block(i) = ...
                    string(M.first_bad_critical_block(idx));
            end
        end
    end
end

Q.property_envelope_pass = ...
    Q.property_envelope_pass & Q.critical_manifest_pass;

Q.overall_pass = ...
    Q.overall_pass & ...
    Q.critical_manifest_pass & ...
    Q.simulation_manifest_pass;

writetable(Q,summaryFile);

%% ------------------------------------------------------------------------
% Class-level coverage
% -------------------------------------------------------------------------
classRows = cell(numel(faultCodes),7);

for i=1:numel(faultCodes)

    code = faultCodes(i);
    idx = Q.fault_code==code;

    classRows{i,1}=code;
    classRows{i,2}=sum(idx);
    classRows{i,3}=sum(Q.overall_pass(idx));
    classRows{i,4}=sum(Q.fault_active_pass(idx));
    classRows{i,5}=sum(Q.property_envelope_pass(idx));
    classRows{i,6}=sum(Q.fault_evidence_pass(idx));
    classRows{i,7}=sum(idx)==2 && ...
        all(Q.overall_pass(idx)) && ...
        all(Q.fault_active_pass(idx)) && ...
        all(Q.property_envelope_pass(idx)) && ...
        all(Q.fault_evidence_pass(idx));
end

C = cell2table(classRows,'VariableNames',{ ...
    'fault_code','runs_found','runs_passed', ...
    'runs_with_fault_activation','runs_property_valid', ...
    'runs_with_fault_evidence','class_pass'});

writetable(C,classFile);

%% ------------------------------------------------------------------------
% Hard gate
% -------------------------------------------------------------------------
fileCountPass = numel(files)==38;
classCoveragePass = all(C.runs_found==2);
allRunPass = height(Q)==38 && all(Q.overall_pass);
allClassPass = all(C.class_pass);

smokeReady = fileCountPass && classCoveragePass && allRunPass && allClassPass;

fprintf('\nRUN-LEVEL SUMMARY\n');
disp(Q(:,{'run_id','fault_code','fault_active_samples', ...
    'property_envelope_pass','fault_evidence_pass','overall_pass'}));

fprintf('\nCLASS-LEVEL SUMMARY\n');
disp(C);

fprintf('\n============================================================\n');
fprintf('SMOKE38 HARD GATES\n');
fprintf('============================================================\n');
fprintf('38 files:                 %s\n',tfstr(fileCountPass));
fprintf('2 runs per class:         %s\n',tfstr(classCoveragePass));
fprintf('all run QA gates:         %s\n',tfstr(allRunPass));
fprintf('all 19 class gates:       %s\n',tfstr(allClassPass));
fprintf('------------------------------------------------------------\n');

if smokeReady
    fprintf('*** SMOKE38 READY FOR 190-RUN DEVELOPMENT GATE ***\n');

    fid=fopen(readyFile,'w');
    fprintf(fid,'Final Scientific v4.6.2 Smoke38 PASS\n');
    fprintf(fid,'38/38 runs present; 2/2 per 19 classes; all hard QA gates passed.\n');
    fprintf(fid,'Next permitted gate: 190-run development campaign (10/class).\n');
    fclose(fid);
else
    fprintf('*** SMOKE38 FAILED / REVIEW REQUIRED ***\n');
    fprintf('Do NOT run the 190- or 1900-run campaigns.\n');
end

fprintf('============================================================\n');

%% ------------------------------------------------------------------------
% Text report
% -------------------------------------------------------------------------
fid=fopen(reportFile,'w');

fprintf(fid,'Al Kaseeh Final Scientific v4.6.2 — Smoke38 QA\n');
fprintf(fid,'============================================================\n');
fprintf(fid,'CSV files: %d / 38\n',numel(files));
fprintf(fid,'File-count gate: %s\n',tfstr(fileCountPass));
fprintf(fid,'Class-coverage gate: %s\n',tfstr(classCoveragePass));
fprintf(fid,'All-run gate: %s\n',tfstr(allRunPass));
fprintf(fid,'All-class gate: %s\n',tfstr(allClassPass));
fprintf(fid,'OVERALL: %s\n\n',tfstr(smokeReady));

failed = Q(~Q.overall_pass,:);

if isempty(failed)
    fprintf(fid,'No failed runs.\n');
else
    fprintf(fid,'Failed/review runs:\n');
    for i=1:height(failed)
        fprintf(fid,'  %s | class %g | active=%d | property=%d | evidence=%d | %s\n', ...
            failed.run_id(i),failed.fault_code(i), ...
            failed.fault_active_pass(i), ...
            failed.property_envelope_pass(i), ...
            failed.fault_evidence_pass(i), ...
            failed.qa_error(i));
    end
end

fclose(fid);

fprintf('\nSaved:\n');
fprintf('  %s\n',summaryFile);
fprintf('  %s\n',classFile);
fprintf('  %s\n',reportFile);

if smokeReady
    fprintf('  %s\n',readyFile);
end

%% ========================================================================
% Helpers
% ========================================================================

function [pass,evidence,effect] = faultEvidence(D,code)

active = D.fault_active>=0.5;

pass = true;
evidence = "not-applicable";
effect = NaN;

if code==0
    evidence="healthy";
    pass=true;
    return;
end

if ~any(active)
    pass=false;
    evidence="FaultActive never true";
    return;
end

switch code

    case 1
        idx=active & D.process_mode==1;
        if any(idx)
            effect=median(D.production_mass_flow_true_kg_s(idx),'omitnan');
            pass=isfinite(effect) && effect<9.8;
            evidence="reduced production-fill flow";
        else
            pass=false; evidence="no active Mode-1 samples";
        end

    case 2
        idx=active & D.process_mode==5;
        if any(idx)
            effect=median(D.cip_supply_mass_flow_true_kg_s(idx),'omitnan');
            pass=isfinite(effect) && effect<9.8;
            evidence="reduced CIP-supply flow";
        else
            pass=false; evidence="no active Mode-5 samples";
        end

    case 3
        idx=active & D.process_mode==1;
        if any(idx)
            effect=median(D.prod_inlet_actual_pct(idx),'omitnan');
            pass=isfinite(effect) && effect<98;
            evidence="production inlet opening reduced";
        else
            pass=false; evidence="no active Mode-1 samples";
        end

    case 4
        idx=active & D.process_mode==1;
        if any(idx)
            effect=median(D.tank_inlet_actual_pct(idx),'omitnan');
            pass=isfinite(effect) && effect<98;
            evidence="tank inlet opening reduced";
        else
            pass=false; evidence="no active Mode-1 samples";
        end

    case 5
        idx=active & D.process_mode==4;
        if any(idx)
            effect=median(D.discharge_actual_pct(idx),'omitnan');
            pass=isfinite(effect) && effect<98;
            evidence="product discharge opening reduced";
        else
            pass=false; evidence="no active Mode-4 samples";
        end

    case 6
        idx=active & D.process_mode~=4;
        if any(idx)
            effect=max(D.discharge_actual_pct(idx),[],'omitnan');
            pass=isfinite(effect) && effect>0.1;
            evidence="discharge leakage while command route should be closed";
        else
            pass=false; evidence="no active non-Mode-4 samples";
        end

    case 7
        % The model's FaultActive semantics are the hard activation proof.
        % Effective heat flow is used when exported.
        idx=active & D.process_mode==2;
        if any(idx) && any(isfinite(D.effective_heat_flow_W(idx)))
            effect=max(D.effective_heat_flow_W(idx),[],'omitnan');
            pass=isfinite(effect) && effect<119000;
            evidence="heating capacity reduced";
        else
            pass=any(idx);
            evidence="FaultActive during heating; heat-flow logger unavailable";
        end

    case 8
        idx=active & D.cmd_agitator_rpm>1;
        if any(idx) && any(isfinite(D.agitator_speed_measured_rpm(idx)))
            effect=median(D.cmd_agitator_rpm(idx)- ...
                D.agitator_speed_measured_rpm(idx),'omitnan');
            pass=isfinite(effect) && effect>0.25;
            evidence="agitator measured speed below command";
        else
            pass=false;
            evidence="RPM measurement unavailable during active agitator fault";
        end

    case 9
        idx=active & D.process_mode==5;
        if any(idx)
            effect=median(D.cip_inlet_actual_pct(idx),'omitnan');
            pass=isfinite(effect) && effect<98;
            evidence="CIP inlet opening reduced";
        else
            pass=false; evidence="no active Mode-5 samples";
        end

    case 10
        idx=active & D.process_mode==5;
        if any(idx)
            effect=median(D.cip_return_actual_pct(idx),'omitnan');
            pass=isfinite(effect) && effect<98;
            evidence="CIP return opening reduced";
        else
            pass=false; evidence="no active Mode-5 samples";
        end

    case 11
        idx=active & D.process_mode==4;
        if any(idx)
            effect=median(D.product_discharge_mass_flow_true_kg_s(idx),'omitnan');
            pass=isfinite(effect) && effect<9.8;
            evidence="reduced product-discharge pump flow";
        else
            pass=false; evidence="no active Mode-4 samples";
        end

    case 12
        idx=active & D.process_mode==5;
        if any(idx)
            effect=median(D.cip_return_mass_flow_true_kg_s(idx),'omitnan');
            pass=isfinite(effect) && effect<9.8;
            evidence="reduced CIP-return pump flow";
        else
            pass=false; evidence="no active Mode-5 samples";
        end

    case 101
        diffv=abs(D.temperature_measured_K-D.temperature_true_K);
        effect=median(diffv(active),'omitnan');
        pass=any(isfinite(diffv(active)) & diffv(active)>1e-6);
        evidence="temperature measured-vs-true bias";

    case 102
        diffv=abs(D.level_measured_m-D.level_true_m);
        effect=median(diffv(active),'omitnan');
        pass=any(isfinite(diffv(active)) & diffv(active)>1e-8);
        evidence="level measured-vs-true bias";

    case 103
        diffv=abs(D.production_mass_flow_measured_kg_s- ...
            D.production_mass_flow_true_kg_s);
        effect=median(diffv(active),'omitnan');
        pass=any(isfinite(diffv(active)) & diffv(active)>1e-6);
        evidence="production-flow measured-vs-true scaling error";

    case 104
        diffv=abs(D.gauge_pressure_measured_Pa-D.gauge_pressure_true_Pa);
        effect=median(diffv(active),'omitnan');
        pass=any(isfinite(diffv(active)) & diffv(active)>1e-3);
        evidence="pressure measured-vs-true drift";

    case 105
        if all(isnan(D.agitator_speed_true_rpm)) || ...
                all(isnan(D.agitator_speed_measured_rpm))
            pass=false;
            evidence="true/measured RPM pair unavailable";
        else
            diffv=abs(D.agitator_speed_measured_rpm- ...
                D.agitator_speed_true_rpm);
            effect=std(diffv(active),'omitnan');
            pass=any(isfinite(diffv(active)) & diffv(active)>1e-6);
            evidence="RPM measured-vs-true excess noise";
        end

    case 106
        diffv=abs(D.temperature_measured_K-D.temperature_true_K);
        drop=isnan(D.temperature_measured_K(active));
        effect=sum(drop);
        pass=any(drop) || any(isfinite(diffv(active)) & diffv(active)>1e-6);
        evidence="temperature dropout/deviation";
end
end

function pass = measuredMissingnessPass(D,code)

pass = true;

% Core measured channels must exist except where NaN is itself the injected
% dropout behavior for class 106.
if code~=106 && all(isnan(D.temperature_measured_K))
    pass=false;
end

if all(isnan(D.level_measured_m))
    pass=false;
end

if all(isnan(D.gauge_pressure_measured_Pa))
    pass=false;
end

if all(isnan(D.production_mass_flow_measured_kg_s))
    pass=false;
end

% RPM is mandatory for the two RPM-specific classes.
if ismember(code,[8 105]) && all(isnan(D.agitator_speed_measured_rpm))
    pass=false;
end
end

function s = tfstr(x)
if x
    s='PASS';
else
    s='FAIL';
end
end
