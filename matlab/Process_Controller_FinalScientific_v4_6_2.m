function [Prod_InletValve, Prod_ToTankValve, Prod_ToFillingValve, ...
          CIP_InletValve, CIP_ReturnValve, SteamValve, ...
          CIP_ReturnFlowCmd, Prod_FillFlowCmd, AgitatorRPM, Mode, ...
          CIP_SupplyFlowCmd, Prod_DischargeFlowCmd] = ...
          Process_Controller(t, TK1_Level, TK1_Temp)
%#codegen
% Final Scientific v4.6.2
% Confirmed fix: Prod_ToTankValve is the SHARED tank inlet used by CIP.
% It must stay OPEN in Mode 5 and during Mode 6 supply ramp-down.

persistent state entryTime lastTime steamLatched
persistent productLowSince cipDrainLowSince cipPermitted

if isempty(state), state=uint8(1); end
if isempty(entryTime), entryTime=0.0; end
if isempty(lastTime), lastTime=-1.0; end
if isempty(steamLatched), steamLatched=true; end
if isempty(productLowSince), productLowSince=-1.0; end
if isempty(cipDrainLowSince), cipDrainLowSince=-1.0; end
if isempty(cipPermitted), cipPermitted=false; end

if t < lastTime
    state=uint8(1);
    entryTime=t;
    steamLatched=true;
    productLowSince=-1.0;
    cipDrainLowSince=-1.0;
    cipPermitted=false;
end
lastTime=t;

VALVE_OPEN  = 5.0e-3;
VALVE_CLOSE = 1.0e-8;

L_FILL_TARGET = 1.45;
L_PRODUCT_TARGET = 0.20;
L_CIP_PERMIT = 0.23;
L_CIP_DRAIN_STOP = 0.07;
L_DRY_PROTECT = 0.04;
L_CIP_HIGH = 1.55;

T_SET = 338.15;
T_LOW = 336.15;
T_HIGH = 340.15;
T_HARD_HIGH = 342.00;

RPM_SET = 23.2;

MIN_MIX_TIME = 300.0;
HOLD_TIME = 600.0;
CIP_CIRC_TIME = 900.0;

FILL_TIMEOUT = 1800.0;
HEAT_TIMEOUT = 6000.0;
DISCHARGE_TIMEOUT = 1800.0;
CIP_DRAIN_TIMEOUT = 900.0;

FILL_VALVE_RELEASE = 1.0;
PROD_DISCHARGE_VALVE_LEAD = 5.0;
PROD_DISCHARGE_RAMP = 5.0;
PRODUCT_LOW_CONFIRM_TIME = 10.0;

CIP_VALVE_LEAD = 5.0;
CIP_PUMP_RAMP = 10.0;
CIP_SUPPLY_RAMPDOWN = 10.0;
CIP_DRAIN_CONFIRM_TIME = 10.0;

% Defaults
Prod_InletValve = VALVE_CLOSE;
Prod_ToTankValve = VALVE_CLOSE;
Prod_ToFillingValve = VALVE_CLOSE;
CIP_InletValve = VALVE_CLOSE;
CIP_ReturnValve = VALVE_CLOSE;
SteamValve = 0.0;

CIP_ReturnFlowCmd = 0.0;
Prod_FillFlowCmd = 0.0;
CIP_SupplyFlowCmd = 0.0;
Prod_DischargeFlowCmd = 0.0;

AgitatorRPM = 0.0;
Mode = 0.0;

elapsed = t-entryTime;

switch state

    case uint8(1)   % Filling
        Mode = 1.0;
        Prod_InletValve = VALVE_OPEN;
        Prod_ToTankValve = VALVE_OPEN;
        Prod_FillFlowCmd = 1.0;

        if TK1_Level >= L_FILL_TARGET
            state=uint8(2);
            entryTime=t;
            steamLatched=true;
        elseif elapsed >= FILL_TIMEOUT
            state=uint8(7);
            entryTime=t;
        end

    case uint8(2)   % Heating + mixing
        Mode = 2.0;
        AgitatorRPM = RPM_SET;

        if elapsed < FILL_VALVE_RELEASE
            Prod_InletValve = VALVE_OPEN;
            Prod_ToTankValve = VALVE_OPEN;
        end

        if TK1_Temp <= T_LOW
            steamLatched=true;
        elseif TK1_Temp >= T_HIGH
            steamLatched=false;
        end

        if steamLatched
            SteamValve=1.0;
        end

        if (TK1_Temp >= T_SET) && (elapsed >= MIN_MIX_TIME)
            state=uint8(3);
            entryTime=t;
        elseif elapsed >= HEAT_TIMEOUT
            state=uint8(7);
            entryTime=t;
        end

    case uint8(3)   % Holding
        Mode = 3.0;
        AgitatorRPM = RPM_SET;

        if TK1_Temp <= T_LOW
            steamLatched=true;
        elseif TK1_Temp >= T_HIGH
            steamLatched=false;
        end

        if steamLatched
            SteamValve=1.0;
        end

        if elapsed >= HOLD_TIME
            state=uint8(4);
            entryTime=t;
            productLowSince=-1.0;
            cipPermitted=false;
        end

    case uint8(4)   % Product discharge
        Mode = 4.0;
        AgitatorRPM = 0.0;
        Prod_ToFillingValve = VALVE_OPEN;

        if elapsed >= PROD_DISCHARGE_VALVE_LEAD
            r=(elapsed-PROD_DISCHARGE_VALVE_LEAD)/PROD_DISCHARGE_RAMP;
            if r < 0.0
                r=0.0;
            elseif r > 1.0
                r=1.0;
            end
            Prod_DischargeFlowCmd=r;
        end

        if TK1_Level <= L_CIP_PERMIT
            Prod_DischargeFlowCmd=0.0;
            if productLowSince < 0.0
                productLowSince=t;
            end
        else
            productLowSince=-1.0;
        end

        if (productLowSince >= 0.0) && ...
                ((t-productLowSince) >= PRODUCT_LOW_CONFIRM_TIME)
            cipPermitted=true;
            state=uint8(5);
            entryTime=t;
            cipDrainLowSince=-1.0;
        elseif elapsed >= DISCHARGE_TIMEOUT
            cipPermitted=false;
            state=uint8(7);
            entryTime=t;
        end

    case uint8(5)   % CIP circulation
        Mode = 5.0;
        AgitatorRPM = 0.0;

        if cipPermitted

            % Isolate production SOURCE.
            Prod_InletValve = VALVE_CLOSE;
            Prod_FillFlowCmd = 0.0;
            Prod_ToFillingValve = VALVE_CLOSE;
            Prod_DischargeFlowCmd = 0.0;

            % v4.6.2 FIX:
            % This is the shared tank inlet and must be OPEN for CIP.
            Prod_ToTankValve = VALVE_OPEN;

            CIP_InletValve = VALVE_OPEN;
            CIP_ReturnValve = VALVE_OPEN;

            if elapsed >= CIP_VALVE_LEAD
                r=(elapsed-CIP_VALVE_LEAD)/CIP_PUMP_RAMP;
                if r < 0.0
                    r=0.0;
                elseif r > 1.0
                    r=1.0;
                end
                CIP_SupplyFlowCmd=r;
                CIP_ReturnFlowCmd=r;
            end

            if TK1_Level >= L_CIP_HIGH
                CIP_SupplyFlowCmd=0.0;
            end

            if TK1_Level <= L_DRY_PROTECT
                CIP_ReturnFlowCmd=0.0;
            end

            if elapsed >= (CIP_VALVE_LEAD + CIP_PUMP_RAMP + CIP_CIRC_TIME)
                state=uint8(6);
                entryTime=t;
                cipDrainLowSince=-1.0;
            end

        else
            state=uint8(7);
            entryTime=t;
        end

    case uint8(6)   % CIP final drain
        Mode = 6.0;
        AgitatorRPM = 0.0;

        if cipPermitted

            % Production source remains isolated.
            Prod_InletValve = VALVE_CLOSE;
            Prod_FillFlowCmd = 0.0;
            Prod_ToFillingValve = VALVE_CLOSE;
            Prod_DischargeFlowCmd = 0.0;

            CIP_ReturnValve = VALVE_OPEN;
            CIP_ReturnFlowCmd = 1.0;

            % v4.6.2 FIX:
            % Keep shared tank inlet open until CIP supply is fully zero.
            if elapsed < CIP_SUPPLY_RAMPDOWN
                Prod_ToTankValve = VALVE_OPEN;
                CIP_InletValve = VALVE_OPEN;

                r=1.0-(elapsed/CIP_SUPPLY_RAMPDOWN);
                if r < 0.0
                    r=0.0;
                elseif r > 1.0
                    r=1.0;
                end
                CIP_SupplyFlowCmd=r;
            else
                CIP_SupplyFlowCmd=0.0;
                CIP_InletValve=VALVE_CLOSE;
                Prod_ToTankValve=VALVE_CLOSE;
            end

            if TK1_Level <= L_CIP_DRAIN_STOP
                CIP_ReturnFlowCmd=0.0;
                if cipDrainLowSince < 0.0
                    cipDrainLowSince=t;
                end
            else
                cipDrainLowSince=-1.0;
            end

            if (cipDrainLowSince >= 0.0) && ...
                    ((t-cipDrainLowSince) >= CIP_DRAIN_CONFIRM_TIME)
                state=uint8(0);
                entryTime=t;
                cipPermitted=false;
            elseif elapsed >= CIP_DRAIN_TIMEOUT
                state=uint8(7);
                entryTime=t;
                cipPermitted=false;
            end

        else
            state=uint8(7);
            entryTime=t;
        end

    case uint8(7)   % Process hold
        Mode = 7.0;
        cipPermitted=false;
        productLowSince=-1.0;
        cipDrainLowSince=-1.0;

    otherwise       % Complete / idle
        Mode = 0.0;
        cipPermitted=false;
end

% Independent safeguards
if TK1_Level <= L_PRODUCT_TARGET
    Prod_DischargeFlowCmd=0.0;
end

if TK1_Temp >= T_HARD_HIGH
    SteamValve=0.0;
end

if TK1_Level <= L_DRY_PROTECT
    AgitatorRPM=0.0;
    SteamValve=0.0;
end

% v4.6.2 corrected CIP interlock:
% isolate production source and filling-line discharge,
% but DO NOT force the shared tank-inlet valve closed.
if (CIP_SupplyFlowCmd > 0.0) || (CIP_ReturnFlowCmd > 0.0)
    Prod_InletValve = VALVE_CLOSE;
    Prod_ToFillingValve = VALVE_CLOSE;
    Prod_FillFlowCmd = 0.0;
    Prod_DischargeFlowCmd = 0.0;
end

if ~cipPermitted
    CIP_InletValve=VALVE_CLOSE;
    CIP_ReturnValve=VALVE_CLOSE;
    CIP_SupplyFlowCmd=0.0;
    CIP_ReturnFlowCmd=0.0;
end

end
