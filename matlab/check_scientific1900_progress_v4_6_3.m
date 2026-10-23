%% check_scientific1900_progress_v4_6_3.m
clear; clc;
thisScript=mfilename('fullpath');
matlabDir=fileparts(thisScript);
projectRoot=fileparts(matlabDir);
dataDir=fullfile(projectRoot,'ml','data','final_scientific_v4_6_3','scientific1900');
codes=[0,1,2,3,4,5,6,7,8,9,10,11,12,101,102,103,104,105,106];
counts=zeros(numel(codes),1);
for i=1:numel(codes)
    pat=sprintf('v463_sci1900_fc%03d_rep*.csv',codes(i));
    counts(i)=numel(dir(fullfile(dataDir,pat)));
end
T=table(codes(:),counts,'VariableNames',{'fault_code','runs_complete'});
disp(T);
fprintf('\nTotal: %d / 1900 (%.1f%%)\n',sum(counts),100*sum(counts)/1900);
fprintf('Remaining: %d\n',1900-sum(counts));
