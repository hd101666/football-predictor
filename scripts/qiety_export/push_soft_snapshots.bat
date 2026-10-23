@echo off
REM qiety pre-match odds -> GitHub push (twice daily)
REM Collection is done continuously by qqsj_v2_cycle_peak/offpeak; this task only exports+pushes.
setlocal EnableDelayedExpansion

set "PY=C:\Users\Lucky\AppData\Local\Programs\Python\Python311\python.exe"
set "QQSJDB=D:\cl\qqsj\data\sports_data.db"
set "REPO=D:\cl\fp_exports"
set "LOGDIR=D:\cl\qqsj_v2\out\logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

for /f "tokens=1-3 delims=/- " %%a in ("%DATE%") do set "D=%%a%%b%%c"
set "LOG=%LOGDIR%\soft_push_%D%.log"

echo [%DATE% %TIME%] ===== start ===== >> "%LOG%"

REM 1) token preflight: exit 2 = expired -> skip whole round
"%PY%" -X utf8 D:\cl\qqsj_v2\qiety_preflight.py --qqsj D:\cl\qqsj >> "%LOG%" 2>&1
if errorlevel 2 (
    echo [%DATE% %TIME%] token expired, skip push >> "%LOG%"
    exit /b 0
)

REM 2) export + push
"%PY%" -X utf8 D:\cl\qqsj_v2\export_soft_snapshots.py --db "%QQSJDB%" --repo "%REPO%" --hours 24 --push >> "%LOG%" 2>&1
set "RC=!ERRORLEVEL!"
echo [%DATE% %TIME%] done rc=!RC! >> "%LOG%"
exit /b !RC!
