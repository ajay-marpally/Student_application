@echo off
REM ============================================================
REM Windows Assigned Access Setup Script for Student Exam App
REM Run as Administrator
REM ============================================================

set KIOSK_USER=ExamStudent
set KIOSK_PASSWORD=SecureExam2024!
set APP_PATH=C:\Program Files\StudentExam\student_client.exe

echo ============================================================
echo Student Exam Application - Kiosk Setup
echo ============================================================
echo.

REM Check for admin privileges
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: This script must be run as Administrator!
    echo Right-click and select "Run as administrator"
    pause
    exit /b 1
)

echo [1/5] Creating kiosk user account...
net user %KIOSK_USER% %KIOSK_PASSWORD% /add /passwordchg:no /expires:never >nul 2>&1
if %errorlevel% equ 0 (
    echo       User '%KIOSK_USER%' created successfully.
) else (
    echo       User '%KIOSK_USER%' already exists or error occurred.
)

echo.
echo [2/5] Disabling Task Manager for kiosk user...
reg add "HKEY_USERS\.DEFAULT\Software\Microsoft\Windows\CurrentVersion\Policies\System" ^
    /v DisableTaskMgr /t REG_DWORD /d 1 /f >nul 2>&1
echo       Task Manager disabled.

echo.
echo [3/5] Disabling Registry Editor...
reg add "HKEY_USERS\.DEFAULT\Software\Microsoft\Windows\CurrentVersion\Policies\System" ^
    /v DisableRegistryTools /t REG_DWORD /d 1 /f >nul 2>&1
echo       Registry Editor disabled.

echo.
echo [4/5] Creating shell launcher configuration...
echo       Note: Full Assigned Access requires manual configuration.
echo       Use Settings > Accounts > Other users > Set up a kiosk

echo.
echo [5/5] Setup Summary
echo ============================================================
echo.
echo Kiosk User:     %KIOSK_USER%
echo Password:       %KIOSK_PASSWORD%
echo Application:    %APP_PATH%
echo.
echo ============================================================
echo NEXT STEPS:
echo ============================================================
echo 1. Copy student_client.exe to: %APP_PATH%
echo 2. Open Settings > Accounts > Other users
echo 3. Click "Set up a kiosk"
echo 4. Select user: %KIOSK_USER%
echo 5. Browse to: %APP_PATH%
echo 6. Complete the wizard
echo.
echo Test by signing out and logging in as %KIOSK_USER%
echo ============================================================
echo.

pause
