%% preflight_FinalScientific_v4_6_3_scientific1900.m
clear; clc;
thisScript=mfilename('fullpath');
matlabDir=fileparts(thisScript);
projectRoot=fileparts(matlabDir);
modelFile=fullfile(projectRoot,'models','AlKaseeh_PhysicalTwin_PM_FinalScientific_v4_6_2.slx');
sensorFile=fullfile(matlabDir,'ALK_apply_sensor_fault_v4_6_3.m');
devReady=fullfile(projectRoot,'ml','data','final_scientific_v4_6_3','development190','DEVELOPMENT190_READY_FOR_1900.txt');
outDir=fullfile(projectRoot,'ml','data','final_scientific_v4_6_3','scientific1900');
fprintf('============================================================\n');
fprintf('SCIENTIFIC1900 PREFLIGHT\n');
fprintf('============================================================\n');
fprintf('Accepted v4.6.2 model:       %s\n',tf(isfile(modelFile)));
fprintf('Validated v4.6.3 sensor:     %s\n',tf(isfile(sensorFile)));
fprintf('Development190 promotion:    %s\n',tf(isfile(devReady)));
if isfolder(outDir), n=numel(dir(fullfile(outDir,'v463_sci1900_fc*_rep*.csv'))); else, n=0; end
fprintf('Existing Scientific1900 runs: %d / 1900\n',n);
allPass=isfile(modelFile)&&isfile(sensorFile)&&isfile(devReady);
if allPass
    fprintf('\n*** PREFLIGHT PASSED ***\n');
    fprintf('You may run the Scientific1900 campaign.\n');
else
    fprintf('\n*** PREFLIGHT FAILED ***\n');
    fprintf('Do NOT start Scientific1900.\n');
end
fprintf('============================================================\n');
function s=tf(x)
if x,s='PASS';else,s='FAIL';end
end
