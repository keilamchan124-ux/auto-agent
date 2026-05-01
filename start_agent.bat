@echo off
title 🤖 Agent V7.2 Keep-Alive Server
color 0A

rem ==========================================
rem 🔧 Configuration Area
rem ==========================================
rem If you are using a virtual environment (venv), remove the 'rem' (comment) from the line below
rem call venv\Scripts\activate

:loop
echo.
echo ==========================================
echo [System] %date% %time% - Starting Agent...
echo ==========================================
python main.py

rem ==========================================
rem 🛡️ Status Check Area
rem ==========================================
rem %ERRORLEVEL% is the exit code returned by Python (0 means normal exit)
if %ERRORLEVEL% EQU 0 (
    echo.
    echo [System] Agent closed normally. Ending script.
    pause
    exit /b
)

rem If the code is not 0, it means an actual error/crash occurred
echo.
echo [Warning] Agent crashed abnormally, Error Code: %ERRORLEVEL% !
echo %date% %time% - Crash ErrorCode: %ERRORLEVEL% >> agent_crash.log
echo [System] Auto-restarting in 3 seconds... To stop completely, repeatedly press Ctrl+C !

timeout /t 3
goto loop