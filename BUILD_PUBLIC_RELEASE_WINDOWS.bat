@echo off
setlocal
cd /d "%~dp0"
REM Source directories are expected beside this extracted repository folder.
REM The command creates a new standalone copy and never modifies original studies.
python scripts\prepare_local_release.py --physical-root "..\AlKaseeh_PM_DigitalTwin_Interactive_v10" --scientific-root "..\AlKaseeh_FinalScientific_v4_6_3_Final19_ML_Retrain_COMPLETE" --output "..\AlKaseeh_GitHub_Ready_v1_1_0" --zip
if errorlevel 1 (
 echo RELEASE NOT READY. Inspect the local import report beside the release candidate.
 exit /b 1
)
echo Release audit and source-completeness gate passed.
endlocal
