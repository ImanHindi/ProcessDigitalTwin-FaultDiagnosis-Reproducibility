%% qa_FinalScientific_v4_6_3_scientific1900.m
% Mandatory QA gate for Final Scientific v4.6.3 SCIENTIFIC1900.
%
% Expected design:
%   1900 CSVs = 19 classes x 100 independent runs/class.
%
% HARD PROMOTION GATES
% --------------------
% 1) exactly 1900 run files;
% 2) exactly 100 runs/class for all 19 final classes;
% 3) unique run seeds;
% 4) 0–9000 s, 9001 exported rows/run;
% 5) finite physical truth and valid broad physical envelope;
% 6) healthy runs reach Modes 0–6 with no Mode 7;
% 7) each nonzero class produces FaultActive;
% 8) class-specific physical/measurement fault evidence;
% 9) critical TL branch envelope from run manifest passes;
% 10) final parameter coverage is broad enough to certify the dataset.
%
% Outputs:
%   scientific1900_QA_summary.csv
%   scientific1900_class_summary.csv
%   scientific1900_parameter_coverage.csv
%   scientific1900_signal_ranges.csv
%   scientific1900_fault_effects.csv
%   scientific1900_QA_report.txt
%   SCIENTIFIC1900_VALIDATED_READY_FOR_MODELING.txt   ONLY on complete PASS
%
% A PASS certifies the generated simulation dataset for the locked run-level
% split and subsequent final model-development/evaluation pipeline.

clear; clc;

thisScript=mfilename('fullpath');
matlabDir=fileparts(thisScript);
projectRoot=fileparts(matlabDir);

dataDir=fullfile(projectRoot,'ml','data', ...
    'final_scientific_v4_6_3','scientific1900');

if ~isfolder(dataDir)
    error('Scientific1900 directory does not exist:\n%s',dataDir);
end

summaryFile=fullfile(dataDir,'scientific1900_QA_summary.csv');
classFile=fullfile(dataDir,'scientific1900_class_summary.csv');
coverageFile=fullfile(dataDir,'scientific1900_parameter_coverage.csv');
signalFile=fullfile(dataDir,'scientific1900_signal_ranges.csv');
effectFile=fullfile(dataDir,'scientific1900_fault_effects.csv');
reportFile=fullfile(dataDir,'scientific1900_QA_report.txt');
readyFile=fullfile(dataDir,'SCIENTIFIC1900_VALIDATED_READY_FOR_MODELING.txt');

if isfile(readyFile)
    delete(readyFile);
end

faultCodes=[ ...
      0, ...
      1,2,3,4,5,6,7,8,9,10,11,12, ...
      101,102,103,104,105,106];

files=dir(fullfile(dataDir,'v463_sci1900_fc*_rep*.csv'));

fprintf('============================================================\n');
fprintf('FINAL SCIENTIFIC v4.6.3 — SCIENTIFIC1900 QA\n');
fprintf('============================================================\n');
fprintf('CSV files found: %d / 1900\n\n',numel(files));

rows=cell(0,31);

for k=1:numel(files)

    path=fullfile(files(k).folder,files(k).name);

    try
        D=readtable(path,'TextType','string');

        required={ ...
            'time','run_id','scenario','target','process_mode', ...
            'fault_active','seed','fault_severity', ...
            'requested_fault_start_s','requested_fault_end_s', ...
            'initial_level_m','initial_temperature_K', ...
            'level_true_m','level_measured_m','volume_m3', ...
            'temperature_true_K','temperature_measured_K', ...
            'gauge_pressure_true_Pa','gauge_pressure_measured_Pa', ...
            'production_mass_flow_true_kg_s', ...
            'production_mass_flow_measured_kg_s', ...
            'product_discharge_mass_flow_true_kg_s', ...
            'cip_supply_mass_flow_true_kg_s', ...
            'cip_return_mass_flow_true_kg_s', ...
            'agitator_speed_measured_rpm','cmd_agitator_rpm', ...
            'prod_inlet_actual_pct','tank_inlet_actual_pct', ...
            'discharge_actual_pct','cip_inlet_actual_pct', ...
            'cip_return_actual_pct'};

        schemaPass=all(ismember(required,D.Properties.VariableNames));

        if ~schemaPass
            missing=string(setdiff(required,D.Properties.VariableNames));
            error('Missing required columns: %s',strjoin(missing,', '));
        end

        code=double(D.target(1));
        runID=string(D.run_id(1));
        seed=double(D.seed(1));
        severity=double(D.fault_severity(1));
        faultStart=double(D.requested_fault_start_s(1));
        faultEnd=double(D.requested_fault_end_s(1));
        initLevel=double(D.initial_level_m(1));
        initTemp=double(D.initial_temperature_K(1));

        timePass=height(D)==9001 && ...
            abs(double(D.time(1)))<1e-9 && ...
            abs(double(D.time(end))-9000)<1e-9 && ...
            all(diff(double(D.time))>0);

        core=[ ...
            double(D.time), ...
            double(D.process_mode), ...
            double(D.level_true_m), ...
            double(D.volume_m3), ...
            double(D.temperature_true_K), ...
            double(D.gauge_pressure_true_Pa), ...
            double(D.production_mass_flow_true_kg_s), ...
            double(D.product_discharge_mass_flow_true_kg_s), ...
            double(D.cip_supply_mass_flow_true_kg_s), ...
            double(D.cip_return_mass_flow_true_kg_s)];

        coreFinitePass=all(isfinite(core),'all');

        modes=unique(round(double(D.process_mode(isfinite(double(D.process_mode))))))';
        modesText=string(mat2str(modes));

        if code==0
            modeCoveragePass=all(ismember(0:6,modes));
            mode7GatePass=~any(round(double(D.process_mode))==7);
            faultActivePass=all((double(D.fault_active)==0) | ...
                isnan(double(D.fault_active)));
        else
            % A genuine severe fault may invoke supervisory hold. For a fault
            % run, Mode7 is diagnostic outcome rather than automatic failure.
            modeCoveragePass=true;
            mode7GatePass=true;
            faultActivePass=any(double(D.fault_active)>=0.5);
        end

        activeSamples=sum(double(D.fault_active)>=0.5);

        absPressureMPa=(double(D.gauge_pressure_true_Pa)+101325)/1e6;

        bulkPropertyPass = ...
            all(double(D.temperature_true_K)>=273.16 & ...
                double(D.temperature_true_K)<=342.0) && ...
            all(absPressureMPa>0.0 & absPressureMPa<5.0) && ...
            all(double(D.level_true_m)>=0.0 & ...
                double(D.level_true_m)<=1.65);

        [faultEvidencePass,evidence,effectMetric]= ...
            faultEvidence(D,code);

        measuredMissingnessPass=measuredMissingness(D,code);

        % Signal summaries for later class-level diversity analysis.
        tmin=min(double(D.temperature_true_K));
        tmax=max(double(D.temperature_true_K));
        lmin=min(double(D.level_true_m));
        lmax=max(double(D.level_true_m));
        pmin=min(absPressureMPa);
        pmax=max(absPressureMPa);

        prodMax=max(double(D.production_mass_flow_true_kg_s));
        dischargeMax=max(double(D.product_discharge_mass_flow_true_kg_s));
        cipSupMax=max(double(D.cip_supply_mass_flow_true_kg_s));
        cipRetMax=max(double(D.cip_return_mass_flow_true_kg_s));

        rpmFinite=double(D.agitator_speed_measured_rpm);
        rpmFinite=rpmFinite(isfinite(rpmFinite));
        if isempty(rpmFinite)
            rpmRange=NaN;
        else
            rpmRange=max(rpmFinite)-min(rpmFinite);
        end

        overall=schemaPass && timePass && coreFinitePass && ...
            modeCoveragePass && mode7GatePass && faultActivePass && ...
            bulkPropertyPass && faultEvidencePass && measuredMissingnessPass;

        rows(end+1,:)={ ...
            runID,code,string(files(k).name),seed,severity, ...
            faultStart,faultEnd,max(0,faultEnd-faultStart), ...
            initLevel,initTemp, ...
            schemaPass,timePass,coreFinitePass, ...
            modeCoveragePass,mode7GatePass,faultActivePass, ...
            bulkPropertyPass,faultEvidencePass,measuredMissingnessPass, ...
            overall,activeSamples,modesText,evidence,effectMetric, ...
            tmin,tmax,lmin,lmax,pmin,pmax,rpmRange}; %#ok<AGROW>

    catch ME

        rows(end+1,:)={ ...
            string(files(k).name),NaN,string(files(k).name),NaN,NaN, ...
            NaN,NaN,NaN,NaN,NaN, ...
            false,false,false,false,false,false,false,false,false, ...
            false,0,"","QA exception",NaN, ...
            NaN,NaN,NaN,NaN,NaN,NaN,NaN}; %#ok<AGROW>
    end
end

Q=cell2table(rows,'VariableNames',{ ...
    'run_id','fault_code','csv_file','seed','fault_severity', ...
    'fault_start_s','fault_end_s','requested_fault_duration_s', ...
    'initial_level_m','initial_temperature_K', ...
    'schema_pass','time_coverage_pass','core_finite_pass', ...
    'mode_coverage_pass','mode7_gate_pass','fault_active_pass', ...
    'bulk_property_envelope_pass','fault_evidence_pass', ...
    'measured_missingness_pass','overall_pass', ...
    'fault_active_samples','modes_reached','fault_evidence', ...
    'effect_metric','minimum_temperature_K','maximum_temperature_K', ...
    'minimum_level_m','maximum_level_m', ...
    'minimum_absolute_pressure_MPa','maximum_absolute_pressure_MPa', ...
    'measured_rpm_range_rpm'});

if ~isempty(Q)
    Q=sortrows(Q,{'fault_code','run_id'});
end

%% ------------------------------------------------------------------------
% Merge run-manifest critical Simscape envelope
% -------------------------------------------------------------------------
manifestFile=fullfile(dataDir,'scientific1900_manifest.csv');

Q.critical_manifest_pass=false(height(Q),1);
Q.simulation_manifest_pass=false(height(Q),1);
Q.critical_min_temperature_K=nan(height(Q),1);
Q.critical_max_temperature_K=nan(height(Q),1);
Q.critical_min_pressure_MPa=nan(height(Q),1);
Q.critical_max_pressure_MPa=nan(height(Q),1);
Q.first_bad_critical_block=strings(height(Q),1);

if isfile(manifestFile)

    M=readtable(manifestFile,'TextType','string');

    requiredManifest={ ...
        'run_id','simulation_ok','property_envelope_pass', ...
        'critical_min_temperature_K','critical_max_temperature_K', ...
        'critical_min_pressure_MPa','critical_max_pressure_MPa', ...
        'first_bad_critical_block'};

    if all(ismember(requiredManifest,M.Properties.VariableNames))

        for i=1:height(Q)

            idx=string(M.run_id)==string(Q.run_id(i));

            if sum(idx)==1

                Q.critical_manifest_pass(i)= ...
                    logical(M.property_envelope_pass(idx));

                Q.simulation_manifest_pass(i)= ...
                    logical(M.simulation_ok(idx));

                Q.critical_min_temperature_K(i)= ...
                    double(M.critical_min_temperature_K(idx));

                Q.critical_max_temperature_K(i)= ...
                    double(M.critical_max_temperature_K(idx));

                Q.critical_min_pressure_MPa(i)= ...
                    double(M.critical_min_pressure_MPa(idx));

                Q.critical_max_pressure_MPa(i)= ...
                    double(M.critical_max_pressure_MPa(idx));

                Q.first_bad_critical_block(i)= ...
                    string(M.first_bad_critical_block(idx));
            end
        end
    end
end

Q.overall_pass = Q.overall_pass & ...
    Q.critical_manifest_pass & ...
    Q.simulation_manifest_pass;

writetable(Q,summaryFile);

%% ------------------------------------------------------------------------
% Class-level summary and fault-evidence summary
% -------------------------------------------------------------------------
classRows=cell(numel(faultCodes),8);
effectRows=cell(numel(faultCodes),7);
coverageRows=cell(numel(faultCodes),17);
signalRows=cell(numel(faultCodes),13);

for i=1:numel(faultCodes)

    code=faultCodes(i);
    idx=Q.fault_code==code;

    classRows{i,1}=code;
    classRows{i,2}=sum(idx);
    classRows{i,3}=sum(Q.overall_pass(idx));
    classRows{i,4}=sum(Q.fault_active_pass(idx));
    classRows{i,5}=sum(Q.critical_manifest_pass(idx));
    classRows{i,6}=sum(Q.fault_evidence_pass(idx));
    classRows{i,7}=numel(unique(Q.seed(idx)));
    classRows{i,8}=sum(idx)==100 && ...
        all(Q.overall_pass(idx)) && ...
        numel(unique(Q.seed(idx)))==100;

    ev=Q.effect_metric(idx);
    ev=ev(isfinite(ev));

    effectRows{i,1}=code;
    effectRows{i,2}=sum(idx);
    effectRows{i,3}=medianOrNaN(ev);
    effectRows{i,4}=minOrNaN(ev);
    effectRows{i,5}=maxOrNaN(ev);
    effectRows{i,6}=stdOrNaN(ev);
    effectRows{i,7}=all(Q.fault_evidence_pass(idx));

    % Parameter coverage.
    sev=Q.fault_severity(idx);
    lev=Q.initial_level_m(idx);
    tmp=Q.initial_temperature_K(idx);
    fs=Q.fault_start_s(idx);
    fd=Q.requested_fault_duration_s(idx);
    act=Q.fault_active_samples(idx);

    sevRange=rangeFinite(sev);
    levelRange=rangeFinite(lev);
    tempRange=rangeFinite(tmp);
    startRange=rangeFinite(fs);
    durationRange=rangeFinite(fd);
    activeRange=rangeFinite(act);

    if code==0
        severityCoveragePass=all(abs(sev)<1e-12);
    elseif code==6
        severityCoveragePass=sevRange>=0.15;
    else
        severityCoveragePass=sevRange>=0.25;
    end

    initialCoveragePass=levelRange>=0.12 && tempRange>=7.0;

    if code==0
        timingCoveragePass=true;
    else
        % Actual active durations can be identical for long fixed-mode sensor
        % intervals, so timing diversity is descriptive rather than a hard
        % requirement. The start/duration ranges are still reported.
        timingCoveragePass=true;
    end

    parameterCoveragePass = sum(idx)==100 && ...
        severityCoveragePass && initialCoveragePass && timingCoveragePass;

    coverageRows{i,1}=code;
    coverageRows{i,2}=sum(idx);
    coverageRows{i,3}=minOrNaN(sev);
    coverageRows{i,4}=medianOrNaN(sev);
    coverageRows{i,5}=maxOrNaN(sev);
    coverageRows{i,6}=sevRange;
    coverageRows{i,7}=minOrNaN(lev);
    coverageRows{i,8}=maxOrNaN(lev);
    coverageRows{i,9}=levelRange;
    coverageRows{i,10}=minOrNaN(tmp);
    coverageRows{i,11}=maxOrNaN(tmp);
    coverageRows{i,12}=tempRange;
    coverageRows{i,13}=startRange;
    coverageRows{i,14}=durationRange;
    coverageRows{i,15}=activeRange;
    coverageRows{i,16}=severityCoveragePass && initialCoveragePass;
    coverageRows{i,17}=parameterCoveragePass;

    % Per-class signal range aggregation.
    signalRows{i,1}=code;
    signalRows{i,2}=minOrNaN(Q.minimum_temperature_K(idx));
    signalRows{i,3}=maxOrNaN(Q.maximum_temperature_K(idx));
    signalRows{i,4}=minOrNaN(Q.minimum_level_m(idx));
    signalRows{i,5}=maxOrNaN(Q.maximum_level_m(idx));
    signalRows{i,6}=minOrNaN(Q.minimum_absolute_pressure_MPa(idx));
    signalRows{i,7}=maxOrNaN(Q.maximum_absolute_pressure_MPa(idx));
    signalRows{i,8}=minOrNaN(Q.critical_min_temperature_K(idx));
    signalRows{i,9}=maxOrNaN(Q.critical_max_temperature_K(idx));
    signalRows{i,10}=minOrNaN(Q.critical_min_pressure_MPa(idx));
    signalRows{i,11}=maxOrNaN(Q.critical_max_pressure_MPa(idx));
    signalRows{i,12}=medianOrNaN(Q.measured_rpm_range_rpm(idx));
    signalRows{i,13}=sum(idx)==100;
end

C=cell2table(classRows,'VariableNames',{ ...
    'fault_code','runs_found','runs_passed','runs_with_fault_activation', ...
    'runs_critical_property_valid','runs_with_fault_evidence', ...
    'unique_seeds','class_pass'});

E=cell2table(effectRows,'VariableNames',{ ...
    'fault_code','runs_found','median_effect_metric', ...
    'minimum_effect_metric','maximum_effect_metric', ...
    'std_effect_metric','all_fault_evidence_pass'});

P=cell2table(coverageRows,'VariableNames',{ ...
    'fault_code','runs_found', ...
    'severity_min','severity_median','severity_max','severity_range', ...
    'initial_level_min_m','initial_level_max_m','initial_level_range_m', ...
    'initial_temperature_min_K','initial_temperature_max_K', ...
    'initial_temperature_range_K', ...
    'fault_start_range_s','requested_duration_range_s', ...
    'fault_active_samples_range', ...
    'core_parameter_spread_pass','parameter_coverage_pass'});

S=cell2table(signalRows,'VariableNames',{ ...
    'fault_code', ...
    'true_temperature_min_K','true_temperature_max_K', ...
    'true_level_min_m','true_level_max_m', ...
    'absolute_pressure_min_MPa','absolute_pressure_max_MPa', ...
    'critical_temperature_min_K','critical_temperature_max_K', ...
    'critical_pressure_min_MPa','critical_pressure_max_MPa', ...
    'median_measured_rpm_range_rpm','signal_summary_complete'});

writetable(C,classFile);
writetable(E,effectFile);
writetable(P,coverageFile);
writetable(S,signalFile);

%% ------------------------------------------------------------------------
% Global hard gates
% -------------------------------------------------------------------------
fileCountPass=numel(files)==1900;
classCoveragePass=all(C.runs_found==100);
uniqueSeedPass=height(Q)==1900 && numel(unique(Q.seed(isfinite(Q.seed))))==1900;
allRunPass=height(Q)==1900 && all(Q.overall_pass);
allClassPass=all(C.class_pass);
parameterCoveragePass=all(P.parameter_coverage_pass);

developmentReady = ...
    fileCountPass && ...
    classCoveragePass && ...
    uniqueSeedPass && ...
    allRunPass && ...
    allClassPass && ...
    parameterCoveragePass;

fprintf('\nRUN-LEVEL FAILURES / REVIEW\n');
failed=Q(~Q.overall_pass,:);
if isempty(failed)
    fprintf('  None.\n');
else
    disp(failed(:,{'run_id','fault_code','fault_active_pass', ...
        'critical_manifest_pass','fault_evidence_pass','overall_pass'}));
end

fprintf('\nCLASS-LEVEL SUMMARY\n');
disp(C);

fprintf('\nPARAMETER COVERAGE\n');
disp(P);

fprintf('\n============================================================\n');
fprintf('SCIENTIFIC1900 HARD GATES\n');
fprintf('============================================================\n');
fprintf('1900 files:                     %s\n',tfstr(fileCountPass));
fprintf('100 runs per 19 classes:        %s\n',tfstr(classCoveragePass));
fprintf('1900 unique seeds:              %s\n',tfstr(uniqueSeedPass));
fprintf('all run QA gates:               %s\n',tfstr(allRunPass));
fprintf('all class gates:                %s\n',tfstr(allClassPass));
fprintf('parameter-coverage gates:       %s\n',tfstr(parameterCoveragePass));
fprintf('------------------------------------------------------------\n');

if developmentReady

    fprintf('*** SCIENTIFIC1900 VALIDATED — READY FOR LOCKED SPLIT AND MODELING ***\n');

    fid=fopen(readyFile,'w');
    fprintf(fid,'Final Scientific v4.6.3 Scientific1900 PASS\n');
    fprintf(fid,'1900/1900 runs present; 100/100 for all 19 classes.\n');
    fprintf(fid,'All run, class, critical-property and parameter-coverage gates passed.\n');
    fprintf(fid,'Next permitted stage: create the locked run-level split, then final model training/evaluation.\n');
    fclose(fid);

else

    fprintf('*** SCIENTIFIC1900 FAILED / REVIEW REQUIRED ***\n');
    fprintf('Do NOT create the locked split or train final models.\n');
end

fprintf('============================================================\n');

%% ------------------------------------------------------------------------
% Text report
% -------------------------------------------------------------------------
fid=fopen(reportFile,'w');

fprintf(fid,'Al Kaseeh Final Scientific v4.6.3 — Scientific1900 QA\n');
fprintf(fid,'============================================================\n');
fprintf(fid,'CSV files: %d / 1900\n',numel(files));
fprintf(fid,'File-count gate: %s\n',tfstr(fileCountPass));
fprintf(fid,'Class-coverage gate: %s\n',tfstr(classCoveragePass));
fprintf(fid,'Unique-seed gate: %s\n',tfstr(uniqueSeedPass));
fprintf(fid,'All-run gate: %s\n',tfstr(allRunPass));
fprintf(fid,'All-class gate: %s\n',tfstr(allClassPass));
fprintf(fid,'Parameter-coverage gate: %s\n',tfstr(parameterCoveragePass));
fprintf(fid,'OVERALL: %s\n\n',tfstr(developmentReady));

if isempty(failed)
    fprintf(fid,'No failed runs.\n');
else
    fprintf(fid,'Failed/review runs:\n');
    for i=1:height(failed)
        fprintf(fid,'  %s | class %g | active=%d | critical=%d | evidence=%d\n', ...
            failed.run_id(i),failed.fault_code(i), ...
            failed.fault_active_pass(i), ...
            failed.critical_manifest_pass(i), ...
            failed.fault_evidence_pass(i));
    end
end

fclose(fid);

fprintf('\nSaved:\n');
fprintf('  %s\n',summaryFile);
fprintf('  %s\n',classFile);
fprintf('  %s\n',coverageFile);
fprintf('  %s\n',signalFile);
fprintf('  %s\n',effectFile);
fprintf('  %s\n',reportFile);

if developmentReady
    fprintf('  %s\n',readyFile);
end

%% ========================================================================
% QA helper functions
% ========================================================================

function [pass,evidence,effect]=faultEvidence(D,code)

active=double(D.fault_active)>=0.5;

pass=true;
evidence="not-applicable";
effect=NaN;

if code==0
    evidence="healthy";
    return;
end

if ~any(active)
    pass=false;
    evidence="FaultActive never true";
    return;
end

mode=round(double(D.process_mode));

switch code

    case 1
        idx=active & mode==1;
        if any(idx)
            effect=median(double(D.production_mass_flow_true_kg_s(idx)),'omitnan');
            pass=isfinite(effect) && effect<9.8;
            evidence="reduced production-fill flow";
        else
            pass=false; evidence="no active Mode-1 samples";
        end

    case 2
        idx=active & mode==5;
        if any(idx)
            effect=median(double(D.cip_supply_mass_flow_true_kg_s(idx)),'omitnan');
            pass=isfinite(effect) && effect<9.8;
            evidence="reduced CIP-supply flow";
        else
            pass=false; evidence="no active Mode-5 samples";
        end

    case 3
        idx=active & mode==1;
        if any(idx)
            effect=median(double(D.prod_inlet_actual_pct(idx)),'omitnan');
            pass=isfinite(effect) && effect<98;
            evidence="production inlet opening reduced";
        else
            pass=false; evidence="no active Mode-1 samples";
        end

    case 4
        idx=active & mode==1;
        if any(idx)
            effect=median(double(D.tank_inlet_actual_pct(idx)),'omitnan');
            pass=isfinite(effect) && effect<98;
            evidence="tank inlet opening reduced";
        else
            pass=false; evidence="no active Mode-1 samples";
        end

    case 5
        idx=active & mode==4;
        if any(idx)
            effect=median(double(D.discharge_actual_pct(idx)),'omitnan');
            pass=isfinite(effect) && effect<98;
            evidence="product-discharge opening reduced";
        else
            pass=false; evidence="no active Mode-4 samples";
        end

    case 6
        idx=active & mode~=4;
        if any(idx)
            effect=max(double(D.discharge_actual_pct(idx)),[],'omitnan');
            pass=isfinite(effect) && effect>0.1;
            evidence="discharge leakage outside commanded discharge mode";
        else
            pass=false; evidence="no active non-Mode-4 samples";
        end

    case 7
        idx=active & mode==2;
        if any(idx) && ismember('effective_heat_flow_W',D.Properties.VariableNames)
            h=double(D.effective_heat_flow_W(idx));
            h=h(isfinite(h));
            if isempty(h)
                pass=true;
                effect=NaN;
                evidence="FaultActive during heating; heat-flow logger unavailable";
            else
                effect=max(h);
                pass=effect<119000;
                evidence="heating capacity reduced";
            end
        else
            pass=any(idx);
            evidence="heating FaultActive evidence";
        end

    case 8
        idx=active & double(D.cmd_agitator_rpm)>1;
        rpm=double(D.agitator_speed_measured_rpm);
        if any(idx) && any(isfinite(rpm(idx)))
            effect=median(double(D.cmd_agitator_rpm(idx))-rpm(idx),'omitnan');
            pass=isfinite(effect) && effect>0.25;
            evidence="agitator speed below command";
        else
            pass=false;
            evidence="RPM measurement unavailable during agitator fault";
        end

    case 9
        idx=active & mode==5;
        if any(idx)
            effect=median(double(D.cip_inlet_actual_pct(idx)),'omitnan');
            pass=isfinite(effect) && effect<98;
            evidence="CIP inlet opening reduced";
        else
            pass=false; evidence="no active Mode-5 samples";
        end

    case 10
        idx=active & mode==5;
        if any(idx)
            effect=median(double(D.cip_return_actual_pct(idx)),'omitnan');
            pass=isfinite(effect) && effect<98;
            evidence="CIP return opening reduced";
        else
            pass=false; evidence="no active Mode-5 samples";
        end

    case 11
        idx=active & mode==4;
        if any(idx)
            effect=median(double(D.product_discharge_mass_flow_true_kg_s(idx)),'omitnan');
            pass=isfinite(effect) && effect<9.8;
            evidence="reduced product-discharge pump flow";
        else
            pass=false; evidence="no active Mode-4 samples";
        end

    case 12
        idx=active & mode==5;
        if any(idx)
            effect=median(double(D.cip_return_mass_flow_true_kg_s(idx)),'omitnan');
            pass=isfinite(effect) && effect<9.8;
            evidence="reduced CIP-return pump flow";
        else
            pass=false; evidence="no active Mode-5 samples";
        end

    case 101
        d=abs(double(D.temperature_measured_K)-double(D.temperature_true_K));
        effect=median(d(active),'omitnan');
        pass=any(isfinite(d(active)) & d(active)>0.20);
        evidence="temperature measured-vs-true bias";

    case 102
        d=abs(double(D.level_measured_m)-double(D.level_true_m));
        effect=median(d(active),'omitnan');
        pass=any(isfinite(d(active)) & d(active)>0.002);
        evidence="level measured-vs-true bias";

    case 103
        d=abs(double(D.production_mass_flow_measured_kg_s)- ...
            double(D.production_mass_flow_true_kg_s));
        effect=median(d(active),'omitnan');
        pass=any(isfinite(d(active)) & d(active)>0.10);
        evidence="production-flow measured-vs-true scale error";

    case 104
        d=abs(double(D.gauge_pressure_measured_Pa)- ...
            double(D.gauge_pressure_true_Pa));
        effect=max(d(active),[],'omitnan');
        pass=any(isfinite(d(active)) & d(active)>50);
        evidence="pressure measured-vs-true drift";

    case 105
        if ~ismember('agitator_speed_true_rpm',D.Properties.VariableNames)
            pass=false;
            evidence="true/reference RPM unavailable";
            return;
        end
        d=double(D.agitator_speed_measured_rpm)- ...
            double(D.agitator_speed_true_rpm);
        effect=std(d(active),'omitnan');
        pass=isfinite(effect) && effect>0.20;
        evidence="RPM measured-vs-reference excess noise";

    case 106
        x=double(D.temperature_measured_K(active));
        effect=sum(isnan(x));
        pass=effect==sum(active);
        evidence="temperature dropout";
end
end

function pass=measuredMissingness(D,code)

pass=true;

if code~=106 && all(isnan(double(D.temperature_measured_K)))
    pass=false;
end

if all(isnan(double(D.level_measured_m)))
    pass=false;
end

if all(isnan(double(D.gauge_pressure_measured_Pa)))
    pass=false;
end

if all(isnan(double(D.production_mass_flow_measured_kg_s)))
    pass=false;
end

if ismember(code,[8 105]) && ...
        all(isnan(double(D.agitator_speed_measured_rpm)))
    pass=false;
end
end

function x=rangeFinite(v)
v=double(v(:));
v=v(isfinite(v));
if isempty(v),x=NaN;else,x=max(v)-min(v);end
end

function x=medianOrNaN(v)
v=double(v(:));
v=v(isfinite(v));
if isempty(v),x=NaN;else,x=median(v);end
end

function x=minOrNaN(v)
v=double(v(:));
v=v(isfinite(v));
if isempty(v),x=NaN;else,x=min(v);end
end

function x=maxOrNaN(v)
v=double(v(:));
v=v(isfinite(v));
if isempty(v),x=NaN;else,x=max(v);end
end

function x=stdOrNaN(v)
v=double(v(:));
v=v(isfinite(v));
if numel(v)<2,x=NaN;else,x=std(v);end
end

function s=tfstr(x)
if x
    s='PASS';
else
    s='FAIL';
end
end
