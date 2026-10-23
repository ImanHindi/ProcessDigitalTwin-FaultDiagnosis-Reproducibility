function [Prod_InletValveOut, Prod_ToTankValveOut, Prod_ToFillingValveOut, ...
          CIP_InletValveOut, CIP_ReturnValveOut, SteamValveOut, ...
          CIP_ReturnFlowCmdOut, Prod_FillFlowCmdOut, AgitatorRPMOut, ModeOut, ...
          CIP_SupplyFlowCmdOut, Prod_DischargeFlowCmdOut, ...
          FaultActive, FaultCodeOut, FaultSeverityOut] = ...
          Fault_Injector(Prod_InletValve, Prod_ToTankValve, Prod_ToFillingValve, ...
          CIP_InletValve, CIP_ReturnValve, SteamValve, ...
          CIP_ReturnFlowCmd, Prod_FillFlowCmd, AgitatorRPM, Mode, ...
          CIP_SupplyFlowCmd, Prod_DischargeFlowCmd, ...
          t, FaultCode, FaultSeverity, FaultStart, FaultEnd)
%#codegen
% Al Kaseeh fault injector - Final Scientific v4
%
% Physical fault codes:
%  0 Normal
%  1 Production fill-pump degradation
%  2 CIP supply-pump degradation
%  3 Production inlet-valve blockage
%  4 Tank inlet-valve blockage
%  5 Product discharge-valve blockage
%  6 Product discharge-valve leakage / stuck open
%  7 Heating / steam degradation
%  8 Agitator degradation
%  9 CIP inlet-valve blockage
% 10 CIP return-valve blockage
% 11 Product discharge-pump degradation
% 12 CIP return-pump degradation
%
% Sensor-fault codes 101..106 remain injected in the data-export layer.
%
% Important scientific change:
% FaultActive indicates an EFFECTIVE physical fault, not merely that the
% requested time interval is active. For degradations/blockages, the
% affected component must also be commanded/operating.

VALVE_CLOSE = 1.0e-8;
VALVE_OPEN  = 5.0e-3;

%% Default outputs = unmodified controller commands
Prod_InletValveOut      = Prod_InletValve;
Prod_ToTankValveOut     = Prod_ToTankValve;
Prod_ToFillingValveOut  = Prod_ToFillingValve;
CIP_InletValveOut       = CIP_InletValve;
CIP_ReturnValveOut      = CIP_ReturnValve;
SteamValveOut           = SteamValve;

CIP_ReturnFlowCmdOut     = CIP_ReturnFlowCmd;
Prod_FillFlowCmdOut      = Prod_FillFlowCmd;
CIP_SupplyFlowCmdOut     = CIP_SupplyFlowCmd;
Prod_DischargeFlowCmdOut = Prod_DischargeFlowCmd;

AgitatorRPMOut = AgitatorRPM;
ModeOut = Mode;

severity = min(max(FaultSeverity,0.0),1.0);
requested = (FaultCode > 0.0) && (t >= FaultStart) && (t <= FaultEnd);
effective = false;

if requested
    code = int32(FaultCode);

    switch code

        case int32(1)
            % Production fill pump degradation.
            if Prod_FillFlowCmd > 1.0e-6
                Prod_FillFlowCmdOut = Prod_FillFlowCmd*(1.0-severity);
                effective = true;
            end

        case int32(2)
            % CIP supply pump degradation.
            if CIP_SupplyFlowCmd > 1.0e-6
                CIP_SupplyFlowCmdOut = CIP_SupplyFlowCmd*(1.0-severity);
                effective = true;
            end

        case int32(3)
            % Production inlet valve blockage.
            if Prod_InletValve > (10.0*VALVE_CLOSE)
                Prod_InletValveOut = max(VALVE_CLOSE, ...
                    Prod_InletValve*(1.0-severity));
                effective = true;
            end

        case int32(4)
            % Tank inlet valve blockage.
            if Prod_ToTankValve > (10.0*VALVE_CLOSE)
                Prod_ToTankValveOut = max(VALVE_CLOSE, ...
                    Prod_ToTankValve*(1.0-severity));
                effective = true;
            end

        case int32(5)
            % Product discharge valve blockage.
            if Prod_ToFillingValve > (10.0*VALVE_CLOSE)
                Prod_ToFillingValveOut = max(VALVE_CLOSE, ...
                    Prod_ToFillingValve*(1.0-severity));
                effective = true;
            end

        case int32(6)
            % Product discharge valve leakage/stuck open.
            % Leakage can be physically effective even while the controller
            % requests the valve to be closed.
            forcedOpening = max(VALVE_CLOSE, severity*VALVE_OPEN);
            Prod_ToFillingValveOut = max(Prod_ToFillingValve, forcedOpening);
            effective = true;

        case int32(7)
            % Heating degradation.
            if SteamValve > 1.0e-6
                SteamValveOut = SteamValve*(1.0-severity);
                effective = true;
            end

        case int32(8)
            % Agitator degradation.
            if AgitatorRPM > 1.0e-6
                AgitatorRPMOut = AgitatorRPM*(1.0-severity);
                effective = true;
            end

        case int32(9)
            % CIP inlet valve blockage.
            if CIP_InletValve > (10.0*VALVE_CLOSE)
                CIP_InletValveOut = max(VALVE_CLOSE, ...
                    CIP_InletValve*(1.0-severity));
                effective = true;
            end

        case int32(10)
            % CIP return valve blockage.
            if CIP_ReturnValve > (10.0*VALVE_CLOSE)
                CIP_ReturnValveOut = max(VALVE_CLOSE, ...
                    CIP_ReturnValve*(1.0-severity));
                effective = true;
            end

        case int32(11)
            % Product discharge pump degradation.
            if Prod_DischargeFlowCmd > 1.0e-6
                Prod_DischargeFlowCmdOut = ...
                    Prod_DischargeFlowCmd*(1.0-severity);
                effective = true;
            end

        case int32(12)
            % CIP return pump degradation.
            if CIP_ReturnFlowCmd > 1.0e-6
                CIP_ReturnFlowCmdOut = CIP_ReturnFlowCmd*(1.0-severity);
                effective = true;
            end
    end
end

FaultActive = double(effective);
FaultCodeOut = FaultCode;
FaultSeverityOut = severity;
end
