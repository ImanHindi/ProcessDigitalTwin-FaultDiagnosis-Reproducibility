%% validate_sensor_faults_v4_6_3.m
% Focused scientific validation of the six v4.6.3 sensor-fault mechanisms.
%
% This test validates the MEASUREMENT layer only.
% It does NOT rerun or modify the accepted v4.6.2 physical Simscape model.
%
% PASS requirements for each code:
%   101 Temperature bias:
%       temperature measurement changes only in active interval.
%   102 Level bias:
%       level measurement changes only in active interval.
%   103 Production-flow scale:
%       flow measurement changes only in active interval.
%   104 Pressure drift:
%       pressure measurement changes only in active interval and drift grows.
%   105 RPM excess noise:
%       RPM measurement changes only in active interval.
%   106 Temperature dropout:
%       temperature is NaN during active interval and normal outside.
%
% Also verifies:
%   - exact FaultActive timing;
%   - unaffected measurement channels remain bitwise/numerically unchanged;
%   - no change outside the requested interval;
%   - deterministic reproduction for code 105.

clear; clc;

thisScript = mfilename('fullpath');
matlabDir = fileparts(thisScript);

addpath(matlabDir);

fprintf('============================================================\n');
fprintf('v4.6.3 FOCUSED SENSOR-FAULT VALIDATION\n');
fprintf('============================================================\n');

% Synthetic healthy measurement traces representative of the process scale.
t = (0:1:3600)';

T0 = 300 + 0.002*t;
L0 = 0.20 + 0.0002*min(t,600);
F0 = 10.0*ones(size(t));
P0 = 2500 + 0.3*t;       % gauge Pa
R0 = 23.2*ones(size(t));  % rpm

startS = 600;
endS   = 1800;
severity = 0.35;
seed = 463105;

codes = [101 102 103 104 105 106];
names = [ ...
    "Temperature sensor bias"; ...
    "Level sensor bias"; ...
    "Production flow sensor scale"; ...
    "Pressure sensor drift"; ...
    "RPM excess noise"; ...
    "Temperature sensor dropout"];

rows = cell(numel(codes),13);

for i=1:numel(codes)

    code=codes(i);

    [T,L,F,P,R,A] = ALK_apply_sensor_fault_v4_6_3( ...
        t,T0,L0,F0,P0,R0,code,severity,startS,endS,seed+i);

    expectedActive = (t>=startS)&(t<=endS);

    activeTimingPass = isequal(logical(A),expectedActive);

    outside = ~expectedActive;

    outsidePass = ...
        equalWithNaN(T(outside),T0(outside)) && ...
        equalWithNaN(L(outside),L0(outside)) && ...
        equalWithNaN(F(outside),F0(outside)) && ...
        equalWithNaN(P(outside),P0(outside)) && ...
        equalWithNaN(R(outside),R0(outside));

    % Channel-specific evidence and unaffected-channel checks.
    targetEffect = NaN;
    targetPass = false;
    unaffectedPass = false;
    deterministicPass = true;

    switch code

        case 101
            d=T-T0;
            targetEffect=median(d(expectedActive),'omitnan');
            targetPass=all(abs(d(expectedActive)-severity*3.0)<1e-12);

            unaffectedPass = ...
                equalWithNaN(L,L0) && equalWithNaN(F,F0) && ...
                equalWithNaN(P,P0) && equalWithNaN(R,R0);

        case 102
            d=L-L0;
            targetEffect=median(d(expectedActive),'omitnan');
            targetPass=all(abs(d(expectedActive)-severity*0.04)<1e-12);

            unaffectedPass = ...
                equalWithNaN(T,T0) && equalWithNaN(F,F0) && ...
                equalWithNaN(P,P0) && equalWithNaN(R,R0);

        case 103
            ratio=F(expectedActive)./F0(expectedActive);
            targetEffect=median(ratio,'omitnan');
            targetPass=all(abs(ratio-(1-severity))<1e-12);

            unaffectedPass = ...
                equalWithNaN(T,T0) && equalWithNaN(L,L0) && ...
                equalWithNaN(P,P0) && equalWithNaN(R,R0);

        case 104
            d=P-P0;
            da=d(expectedActive);
            targetEffect=da(end);
            targetPass= ...
                abs(da(1))<1e-12 && ...
                abs(da(end)-severity*1000)<1e-9 && ...
                all(diff(da)>=-1e-12);

            unaffectedPass = ...
                equalWithNaN(T,T0) && equalWithNaN(L,L0) && ...
                equalWithNaN(F,F0) && equalWithNaN(R,R0);

        case 105
            d=R-R0;
            da=d(expectedActive);
            targetEffect=std(da,'omitnan');

            targetPass=isfinite(targetEffect) && targetEffect>0.40;

            unaffectedPass = ...
                equalWithNaN(T,T0) && equalWithNaN(L,L0) && ...
                equalWithNaN(F,F0) && equalWithNaN(P,P0);

            [~,~,~,~,R2,A2] = ALK_apply_sensor_fault_v4_6_3( ...
                t,T0,L0,F0,P0,R0,code,severity,startS,endS,seed+i);

            deterministicPass = ...
                equalWithNaN(R,R2) && isequal(A,A2);

        case 106
            targetEffect=sum(isnan(T(expectedActive)));
            targetPass=all(isnan(T(expectedActive))) && ...
                all(isfinite(T(outside)));

            unaffectedPass = ...
                equalWithNaN(L,L0) && equalWithNaN(F,F0) && ...
                equalWithNaN(P,P0) && equalWithNaN(R,R0);
    end

    overall = activeTimingPass && outsidePass && ...
        targetPass && unaffectedPass && deterministicPass;

    rows(i,:) = { ...
        code,names(i),sum(A),sum(expectedActive), ...
        activeTimingPass,outsidePass,targetPass,unaffectedPass, ...
        deterministicPass,targetEffect, ...
        minFinite([T;L;F;P;R]),maxFinite([T;L;F;P;R]),overall};

end

R = cell2table(rows,'VariableNames',{ ...
    'fault_code','fault_name','active_samples','expected_active_samples', ...
    'active_timing_pass','outside_interval_unchanged_pass', ...
    'target_effect_pass','unaffected_channels_pass', ...
    'deterministic_pass','effect_metric', ...
    'minimum_finite_output','maximum_finite_output','overall_pass'});

disp(R);

allPass=all(R.overall_pass);

fprintf('\n============================================================\n');

if allPass
    fprintf('*** v4.6.3 SENSOR-FAULT LAYER VALIDATION PASSED ***\n');
    fprintf('Next run:\n');
    fprintf('  run(''matlab/rebuild_sensor_smoke12_v4_6_3.m'')\n');
else
    fprintf('*** v4.6.3 SENSOR-FAULT LAYER VALIDATION FAILED ***\n');
    fprintf('Do NOT rebuild the sensor Smoke12 dataset.\n');
end

fprintf('============================================================\n');

function tf = equalWithNaN(a,b)
tf = isequaln(a,b);
end

function v=minFinite(x)
x=x(isfinite(x));
if isempty(x),v=NaN;else,v=min(x);end
end

function v=maxFinite(x)
x=x(isfinite(x));
if isempty(x),v=NaN;else,v=max(x);end
end
