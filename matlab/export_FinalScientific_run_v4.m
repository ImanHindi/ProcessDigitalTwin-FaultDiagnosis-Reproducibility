function tbl = export_FinalScientific_run_v4(simOut,meta)
% Create a 1-second canonical CSV table from one Final Scientific v4 run.
%
% Required meta fields:
% run_id, scenario, target_fault_code, initial_level_m, initial_temp_K,
% prod_fill_nominal_kg_s, prod_discharge_nominal_kg_s,
% cip_supply_nominal_kg_s, cip_return_nominal_kg_s,
% heat_capacity_W, requested_fault_start_s, requested_fault_end_s,
% requested_fault_severity, noise_seed

t = (0:1:7200)';

% Physical/process signals.
TK1_Level = signal(simOut,'TK1_Level',t,'linear');
TK1_Volume = signal(simOut,'TK1_Volume',t,'linear');
TK1_Temp = signal(simOut,'TK1_Temp',t,'linear');
TK1_pressure = signal(simOut,'TK1_pressure',t,'linear');
M1_RPM = signal(simOut,'M1_RPM',t,'linear');
M1_Angle = signal(simOut,'M1_Angle',t,'linear');

ProdFlowMeas = signal(simOut,'MassFlowRateProd',t,'linear');
CIPSupplyMeas = signal(simOut,'MassFlowRateCIP',t,'linear');
CIPReturnMeas = signal(simOut,'MassFlowRateCIPDischarge',t,'linear');
ProdDischargeMeas = signal(simOut,'MassFlowRateProdDischarge',t,'linear');

ProdFlowTrue = optionalSignal(simOut,'MassFlowRateProdTrue',t,ProdFlowMeas);
CIPSupplyTrue = optionalSignal(simOut,'MassFlowRateCIPTrue',t,CIPSupplyMeas);
CIPReturnTrue = optionalSignal(simOut,'MassFlowRateCIPDischargeTrue',t,CIPReturnMeas);
ProdDischargeTrue = optionalSignal(simOut,'MassFlowRateProdDischargeTrue',t,ProdDischargeMeas);

mode = round(signal(simOut,'process_mode',t,'previous'));

% Effective commands after actuator faults.
cmd_prod_inlet = signal(simOut,'cmd_prod_inlet',t,'previous');
cmd_prod_to_tank = signal(simOut,'cmd_prod_to_tank',t,'previous');
cmd_prod_to_filling = signal(simOut,'cmd_prod_to_filling',t,'previous');
cmd_cip_inlet = signal(simOut,'cmd_cip_inlet',t,'previous');
cmd_cip_return = signal(simOut,'cmd_cip_return',t,'previous');
cmd_steam = signal(simOut,'cmd_steam',t,'previous');
cmd_cip_return_flow = signal(simOut,'cmd_cip_return_flow',t,'previous');
cmd_prod_fill_flow = signal(simOut,'cmd_prod_fill_flow',t,'previous');
cmd_cip_supply_flow = signal(simOut,'cmd_cip_supply_flow',t,'previous');
cmd_prod_discharge_flow = signal(simOut,'cmd_prod_discharge_flow',t,'previous');
cmd_agitator_rpm = signal(simOut,'cmd_agitator_rpm',t,'previous');

fault_active_physical = signal(simOut,'fault_active',t,'previous') > 0.5;
fault_code_physical = round(signal(simOut,'fault_code',t,'previous'));
fault_severity = signal(simOut,'fault_severity',t,'previous');

% Base measured sensors. The Simulink model already contains measurement
% noise on its sensor channels. Sensor-fault classes below are applied only
% to measured values; true physical channels remain untouched.
temperature_measured_K = TK1_Temp;
level_measured_m = TK1_Level;
pressure_measured_Pa = TK1_pressure;
prod_fill_measured_kg_s = ProdFlowMeas;
prod_discharge_measured_kg_s = ProdDischargeMeas;
cip_supply_measured_kg_s = CIPSupplyMeas;
cip_return_measured_kg_s = CIPReturnMeas;
rpm_measured = M1_RPM;

fault_active = fault_active_physical;
fault_code = fault_code_physical;

% Sensor-fault classes 101..106.
code = meta.target_fault_code;
if code >= 101
    sensorActive = (t >= meta.requested_fault_start_s) & ...
                   (t <= meta.requested_fault_end_s);
    fault_active = sensorActive;
    fault_code(:) = code;
    fault_severity(:) = meta.requested_fault_severity;

    rng(meta.noise_seed,'twister');
    sev = meta.requested_fault_severity;

    switch code
        case 101
            % Temperature bias: signed 1.5..5 K equivalent.
            sgn = 1;
            if rand < 0.5, sgn = -1; end
            bias = sgn*(1.5 + 3.5*sev);
            temperature_measured_K(sensorActive) = ...
                temperature_measured_K(sensorActive) + bias;

        case 102
            % Level bias: signed 0.02..0.10 m.
            sgn = 1;
            if rand < 0.5, sgn = -1; end
            bias = sgn*(0.02 + 0.08*sev);
            level_measured_m(sensorActive) = ...
                level_measured_m(sensorActive) + bias;

        case 103
            % Production fill-flow scale error.
            sgn = 1;
            if rand < 0.5, sgn = -1; end
            scale = 1.0 + sgn*(0.10 + 0.30*sev);
            prod_fill_measured_kg_s(sensorActive) = ...
                prod_fill_measured_kg_s(sensorActive)*scale;

        case 104
            % Pressure drift, up to several kPa over the active interval.
            idx = find(sensorActive);
            if ~isempty(idx)
                driftMax = (500 + 3000*sev);
                drift = linspace(0,driftMax,numel(idx))';
                pressure_measured_Pa(idx) = ...
                    pressure_measured_Pa(idx) + drift;
            end

        case 105
            % Excess RPM measurement noise.
            idx = find(sensorActive);
            if ~isempty(idx)
                sigma = 0.5 + 4.5*sev;
                rpm_measured(idx) = rpm_measured(idx) + ...
                    sigma*randn(numel(idx),1);
            end

        case 106
            % Temperature-sensor dropout is represented as missing data,
            % not a physically impossible 0 K reading.
            temperature_measured_K(sensorActive) = NaN;
    end
end

% Derived diagnostics.
temperature_rate_K_s = [0; diff(TK1_Temp)];
level_rate_m_s = [0; diff(TK1_Level)];
temperature_error_K = 338.15 - temperature_measured_K;
agitator_speed_error_rpm = cmd_agitator_rpm - rpm_measured;

n = numel(t);

tbl = table();
tbl.time = t;
tbl.run_id = repmat(string(meta.run_id),n,1);
tbl.scenario = repmat(string(meta.scenario),n,1);
tbl.process_mode = mode;

tbl.temperature_true_K = TK1_Temp;
tbl.temperature_measured_K = temperature_measured_K;
tbl.level_true_m = TK1_Level;
tbl.level_measured_m = level_measured_m;
tbl.volume_m3 = TK1_Volume;
tbl.gauge_pressure_true_Pa = TK1_pressure;
tbl.gauge_pressure_measured_Pa = pressure_measured_Pa;

tbl.production_fill_mass_flow_true_kg_s = ProdFlowTrue;
tbl.production_fill_mass_flow_measured_kg_s = prod_fill_measured_kg_s;
tbl.production_discharge_mass_flow_true_kg_s = ProdDischargeTrue;
tbl.production_discharge_mass_flow_measured_kg_s = prod_discharge_measured_kg_s;
tbl.cip_supply_mass_flow_true_kg_s = CIPSupplyTrue;
tbl.cip_supply_mass_flow_measured_kg_s = cip_supply_measured_kg_s;
tbl.cip_return_mass_flow_true_kg_s = CIPReturnTrue;
tbl.cip_return_mass_flow_measured_kg_s = cip_return_measured_kg_s;

tbl.agitator_speed_true_rpm = M1_RPM;
tbl.agitator_speed_measured_rpm = rpm_measured;
tbl.agitator_angle_rad = M1_Angle;

tbl.temperature_rate_K_s = temperature_rate_K_s;
tbl.level_rate_m_s = level_rate_m_s;
tbl.temperature_error_K = temperature_error_K;
tbl.agitator_speed_error_rpm = agitator_speed_error_rpm;

tbl.cmd_prod_inlet_area_m2 = cmd_prod_inlet;
tbl.cmd_prod_to_tank_area_m2 = cmd_prod_to_tank;
tbl.cmd_prod_to_filling_area_m2 = cmd_prod_to_filling;
tbl.cmd_cip_inlet_area_m2 = cmd_cip_inlet;
tbl.cmd_cip_return_area_m2 = cmd_cip_return;
tbl.cmd_steam = cmd_steam;

tbl.cmd_prod_fill_pump = cmd_prod_fill_flow;
tbl.cmd_prod_discharge_pump = cmd_prod_discharge_flow;
tbl.cmd_cip_supply_pump = cmd_cip_supply_flow;
tbl.cmd_cip_return_pump = cmd_cip_return_flow;
tbl.cmd_agitator_rpm = cmd_agitator_rpm;

tbl.fault_active = double(fault_active);
tbl.fault_code = fault_code;
tbl.fault_severity = fault_severity;
tbl.target_fault_code = repmat(code,n,1);

tbl.initial_level_m = repmat(meta.initial_level_m,n,1);
tbl.initial_temp_K = repmat(meta.initial_temp_K,n,1);
tbl.prod_fill_nominal_kg_s = repmat(meta.prod_fill_nominal_kg_s,n,1);
tbl.prod_discharge_nominal_kg_s = repmat(meta.prod_discharge_nominal_kg_s,n,1);
tbl.cip_supply_nominal_kg_s = repmat(meta.cip_supply_nominal_kg_s,n,1);
tbl.cip_return_nominal_kg_s = repmat(meta.cip_return_nominal_kg_s,n,1);
tbl.heat_capacity_W = repmat(meta.heat_capacity_W,n,1);
tbl.requested_fault_start_s = repmat(meta.requested_fault_start_s,n,1);
tbl.requested_fault_end_s = repmat(meta.requested_fault_end_s,n,1);
tbl.noise_seed = repmat(meta.noise_seed,n,1);

end

function y = signal(out,name,t,method)
    ts = fetch(out,name);
    x = double(ts.Time(:));
    v = double(ts.Data(:));
    [x,ia] = unique(x,'stable');
    v = v(ia);
    if strcmp(method,'previous')
        y = interp1(x,v,t,'previous','extrap');
    else
        y = interp1(x,v,t,'linear','extrap');
    end
end

function y = optionalSignal(out,name,t,fallback)
    try
        y = signal(out,name,t,'linear');
    catch
        y = fallback;
    end
end

function ts = fetch(out,name)
    try
        ts = out.get(name);
        if isempty(ts), error('empty'); end
    catch
        ts = evalin('base',name);
    end
end
