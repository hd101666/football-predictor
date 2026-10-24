@echo off
REM Auto-probe 500.com and resume missing company odds when unblocked.
REM Probe sends exactly 1 request. If still challenged, exits immediately (no retry).
setlocal EnableDelayedExpansion

set "PY=C:\Users\Lucky\AppData\Local\Programs\Python\Python311\python.exe"
set "BASE=D:\cl\qqsj_v2"
set "LOGDIR=%BASE%\out\logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

for /f "tokens=1-3 delims=/- " %%a in ("%DATE%") do set "D=%%a%%b%%c"
set "LOG=%LOGDIR%\probe500_%D%.log"

echo [%DATE% %TIME%] ===== probe ===== >> "%LOG%"

"%PY%" -X utf8 "%BASE%\resume_500_company.py" --probe >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [%DATE% %TIME%] still blocked, exit >> "%LOG%"
    exit /b 0
)

echo [%DATE% %TIME%] IP OK -> start resume >> "%LOG%"
"%PY%" -X utf8 "%BASE%\resume_500_company.py" --run --sleep-min 8 --sleep-max 12 >> "%LOG%" 2>&1
echo [%DATE% %TIME%] resume done rc=!ERRORLEVEL! >> "%LOG%"
exit /b 0
