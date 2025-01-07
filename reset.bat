@echo off
setlocal EnableDelayedExpansion

:: Check for admin privileges and self-elevate if needed
net session >nul 2>&1
if %errorLevel% == 0 (
    goto :run
) else (
    goto :getAdmin
)

:getAdmin
    echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\getadmin.vbs"
    echo UAC.ShellExecute "%~s0", "", "", "runas", 0 >> "%temp%\getadmin.vbs"
    "%temp%\getadmin.vbs"
    del "%temp%\getadmin.vbs"
    exit /B

:run
:: Generate new GUID
for /f %%i in ('powershell -Command "[guid]::NewGuid().ToString()"') do set NEW_GUID=%%i

:: Update registry with new GUID
reg add "HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Cryptography" /v MachineGuid /t REG_SZ /d "%NEW_GUID%" /f >nul 2>&1 

:: Close Cursor
taskkill /IM "cursor.exe" /F >nul 2>&1
exit /b 