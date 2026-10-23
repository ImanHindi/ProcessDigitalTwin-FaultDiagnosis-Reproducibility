%% create_locked_split_v4_6_3_scientific1900.m
% FINAL grouped run-level split: 70 train / 15 validation / 15 test per class.
clear; clc;
thisScript=mfilename('fullpath');
matlabDir=fileparts(thisScript);
projectRoot=fileparts(matlabDir);
dataDir=fullfile(projectRoot,'ml','data','final_scientific_v4_6_3','scientific1900');
readyFile=fullfile(dataDir,'SCIENTIFIC1900_VALIDATED_READY_FOR_MODELING.txt');
qaFile=fullfile(dataDir,'scientific1900_QA_summary.csv');
if ~isfile(readyFile), error('Scientific1900 QA promotion file missing.'); end
if ~isfile(qaFile), error('Scientific1900 QA summary missing.'); end
Q=readtable(qaFile,'TextType','string');
if height(Q)~=1900 || ~all(Q.overall_pass), error('QA summary is not a complete 1900/1900 PASS.'); end
codes=[0,1,2,3,4,5,6,7,8,9,10,11,12,101,102,103,104,105,106];
splitSeed=4631900;
rows=cell(0,7); summaryRows=cell(0,8);
for i=1:numel(codes)
    code=codes(i); C=Q(Q.fault_code==code,:);
    if height(C)~=100, error('Class %d has %d runs instead of 100.',code,height(C)); end
    C=sortrows(C,'run_id');
    stream=RandStream('mt19937ar','Seed',splitSeed+i*1009);
    perm=randperm(stream,100); splitName=strings(100,1);
    splitName(perm(1:70))='train'; splitName(perm(71:85))='validation'; splitName(perm(86:100))='test';
    for j=1:100
        rows(end+1,:)={C.run_id(j),code,splitName(j),C.csv_file(j),C.seed(j),C.fault_severity(j),C.fault_active_samples(j)}; %#ok<AGROW>
    end
    sevTrain=C.fault_severity(splitName=='train'); sevVal=C.fault_severity(splitName=='validation'); sevTest=C.fault_severity(splitName=='test');
    summaryRows(end+1,:)={code,70,15,15,range(sevTrain),range(sevVal),range(sevTest),100}; %#ok<AGROW>
end
S=cell2table(rows,'VariableNames',{'run_id','fault_code','split','csv_file','seed','fault_severity','fault_active_samples'});
SS=cell2table(summaryRows,'VariableNames',{'fault_code','train_runs','validation_runs','test_runs','train_severity_range','validation_severity_range','test_severity_range','total_runs'});
if numel(unique(S.run_id))~=1900, error('Duplicate run_id detected.'); end
if sum(S.split=='train')~=1330 || sum(S.split=='validation')~=285 || sum(S.split=='test')~=285, error('Unexpected global split counts.'); end
for i=1:numel(codes)
    idx=S.fault_code==codes(i);
    if sum(idx & S.split=='train')~=70 || sum(idx & S.split=='validation')~=15 || sum(idx & S.split=='test')~=15, error('Class %d split counts invalid.',codes(i)); end
end
splitFile=fullfile(dataDir,'scientific1900_LOCKED_run_split.csv');
summaryFile=fullfile(dataDir,'scientific1900_LOCKED_split_summary.csv');
lockFile=fullfile(dataDir,'LOCKED_SPLIT_CREATED_DO_NOT_CHANGE.txt');
writetable(S,splitFile); writetable(SS,summaryFile);
fid=fopen(lockFile,'w');
fprintf(fid,'Scientific1900 locked run-level split\nSeed: %d\nPer class: 70 train / 15 validation / 15 test\nGlobal: 1330 train / 285 validation / 285 test\nDo not alter after model development begins.\n',splitSeed); fclose(fid);
fprintf('============================================================\n');
fprintf('LOCKED RUN-LEVEL SPLIT CREATED\n');
fprintf('Train: 1330 | Validation: 285 | Test: 285\n');
fprintf('Exactly 70/15/15 per each of 19 classes.\n');
fprintf('*** DO NOT CHANGE THIS SPLIT AFTER TRAINING BEGINS ***\n');
fprintf('============================================================\n');
