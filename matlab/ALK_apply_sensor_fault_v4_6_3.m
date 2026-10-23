function [T_meas,L_meas,F_meas,P_meas,RPM_meas,FaultActive] = ...
    ALK_apply_sensor_fault_v4_6_3( ...
    t,T_base,L_base,F_base,P_base,RPM_base, ...
    faultCode,severity,faultStart,faultEnd,seed)
%#codegen
% Al Kaseeh Final Scientific v4.6.3
% Measurement-layer sensor-fault transformation.
%
% IMPORTANT SCIENTIFIC SCOPE
% --------------------------
% This function DOES NOT modify the physical plant state. It transforms only
% measurement channels, consistent with:
%
%     y_meas(t) = g_f(y_true(t)) + epsilon(t)
%
% The input *_base vectors are the already available baseline measurements
% (including nominal measurement noise when present).
%
% Smoke-test fault magnitudes are explicit and deterministic:
%
% 101 Temperature sensor bias:
%       + severity * 3.0 K
%
% 102 Level sensor bias:
%       + severity * 0.04 m
%
% 103 Production-flow sensor scale:
%       measured = base * (1 - severity)
%
% 104 Pressure sensor drift:
%       linear drift 0 -> severity * 1000 Pa over active interval
%
% 105 RPM excessive noise:
%       additional Gaussian noise std = severity * 2.0 rpm
%
% 106 Temperature sensor dropout:
%       NaN during active interval
%
% These are smoke/development magnitudes, not plant-calibrated sensor
% specifications. Final scientific campaign ranges should be locked only
% after author/plant review.
%
% Inputs may be vectors or scalars. Vector use is intended for CSV rebuild.

t = t(:);
T_base = T_base(:);
L_base = L_base(:);
F_base = F_base(:);
P_base = P_base(:);
RPM_base = RPM_base(:);

n = numel(t);

if numel(T_base)~=n || numel(L_base)~=n || numel(F_base)~=n || ...
        numel(P_base)~=n || numel(RPM_base)~=n
    error('All signal vectors must have the same length as t.');
end

severity = max(0.0,min(1.0,double(severity)));

T_meas = T_base;
L_meas = L_base;
F_meas = F_base;
P_meas = P_base;
RPM_meas = RPM_base;

isSensorCode = any(double(faultCode)==[101 102 103 104 105 106]);

FaultActive = false(n,1);

if ~isSensorCode
    return;
end

active = (t >= double(faultStart)) & (t <= double(faultEnd));
FaultActive(active) = true;

if ~any(active)
    return;
end

switch double(faultCode)

    case 101
        T_meas(active) = T_base(active) + severity*3.0;

    case 102
        L_meas(active) = L_base(active) + severity*0.04;

    case 103
        F_meas(active) = F_base(active) .* (1.0-severity);

    case 104
        denom = max(1e-9,double(faultEnd)-double(faultStart));
        progress = (t(active)-double(faultStart))/denom;
        progress = max(0,min(1,progress));

        P_meas(active) = P_base(active) + ...
            progress.*(severity*1000.0);

    case 105
        % Deterministic local stream; does not disturb caller/global RNG.
        stream = RandStream('mt19937ar','Seed',double(seed));
        extraNoise = severity*2.0 .* randn(stream,n,1);
        RPM_meas(active) = RPM_base(active) + extraNoise(active);

    case 106
        T_meas(active) = NaN;
end

end
