# Windows Kiosk Mode Setup Guide

## Overview

This guide explains how to configure Windows Assigned Access (Kiosk Mode) for the Student Exam Application. This provides the highest level of lockdown by replacing the Windows shell.

## Prerequisites

- Windows 10/11 Pro, Enterprise, or Education
- Administrator access to the exam computer
- Student Exam Application installed

## Option 1: Assigned Access Wizard (GUI)

### Step 1: Create a Dedicated User Account

1. Open **Settings** > **Accounts** > **Other users**
2. Click **Add someone else to this PC**
3. Select **I don't have this person's sign-in information**
4. Select **Add a user without a Microsoft account**
5. Create account:
   - Username: `ExamStudent`
   - Password: Set a secure password
6. Click **Next**

### Step 2: Configure Assigned Access

1. Open **Settings** > **Accounts** > **Other users**
2. Click **Set up a kiosk**
3. Click **Get started**
4. Select the `ExamStudent` account
5. Choose **Use another app**
6. Browse to `student_client.exe`
7. Complete the wizard

### Step 3: Test the Configuration

1. Sign out of the current user
2. Sign in as `ExamStudent`
3. The exam application should launch automatically
4. Verify Alt+Tab, Windows key are disabled
5. Sign out (Ctrl+Alt+Del > Sign out)

## Option 2: PowerShell Script (Automated)

Save this as `setup_kiosk.ps1` and run as Administrator:

```powershell
# Setup script for Windows Assigned Access
# Run as Administrator

$ErrorActionPreference = "Stop"

# Configuration
$KioskUser = "ExamStudent"
$KioskPassword = "SecureExamPass123!"  # Change this!
$AppPath = "C:\Program Files\StudentExam\student_client.exe"

Write-Host "Setting up Windows Kiosk Mode for Student Exam" -ForegroundColor Green

# Step 1: Create local user account
Write-Host "Creating kiosk user account..."
try {
    $SecurePassword = ConvertTo-SecureString $KioskPassword -AsPlainText -Force
    New-LocalUser -Name $KioskUser -Password $SecurePassword -PasswordNeverExpires -UserMayNotChangePassword
    Write-Host "User '$KioskUser' created successfully" -ForegroundColor Green
} catch {
    if ($_.Exception.Message -like "*already exists*") {
        Write-Host "User '$KioskUser' already exists, continuing..." -ForegroundColor Yellow
    } else {
        throw $_
    }
}

# Step 2: Configure Assigned Access via WMI
Write-Host "Configuring Assigned Access..."

$AUMID = (Get-StartApps | Where-Object {$_.AppID -like "*student_client*"}).AppId
if (-not $AUMID) {
    Write-Host "Note: Using shell launcher configuration instead of AUMID" -ForegroundColor Yellow
}

# Step 3: Configure Shell Launcher (alternative for Win32 apps)
$ShellConfig = @"
<?xml version="1.0" encoding="utf-8"?>
<ShellLauncherConfiguration>
  <Profile Id="{ExamProfile-GUID}">
    <Shell Shell="$AppPath" />
  </Profile>
  <Configs>
    <Config>
      <Account Name="$KioskUser" />
      <Profile Id="{ExamProfile-GUID}" />
    </Config>
  </Configs>
</ShellLauncherConfiguration>
"@

# Save configuration
$ConfigPath = "$env:TEMP\shelllauncher.xml"
$ShellConfig | Out-File -FilePath $ConfigPath -Encoding UTF8

Write-Host "Kiosk configuration created at: $ConfigPath" -ForegroundColor Green
Write-Host ""
Write-Host "IMPORTANT: Manual steps required:" -ForegroundColor Yellow
Write-Host "1. Open Group Policy Editor (gpedit.msc)" -ForegroundColor Yellow
Write-Host "2. Navigate to: Computer Configuration > Administrative Templates > System > Logon" -ForegroundColor Yellow
Write-Host "3. Configure 'Assigned Access' settings" -ForegroundColor Yellow
Write-Host ""
Write-Host "Or use Settings > Accounts > Other users > Set up a kiosk" -ForegroundColor Yellow
```

## Option 3: Group Policy (Enterprise)

For enterprise deployments:

1. Open **Group Policy Management Console** (gpmc.msc)
2. Create a new GPO for exam computers
3. Navigate to: **Computer Configuration** > **Policies** > **Administrative Templates** > **System** > **Logon**
4. Configure shell launcher policies
5. Link GPO to exam computer OU

## Additional Hardening

### Disable Task Manager

```powershell
# Run as Administrator
$RegPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Policies\System"
New-Item -Path $RegPath -Force
Set-ItemProperty -Path $RegPath -Name "DisableTaskMgr" -Value 1 -Type DWORD
```

### Disable Registry Editor

```powershell
$RegPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Policies\System"
Set-ItemProperty -Path $RegPath -Name "DisableRegistryTools" -Value 1 -Type DWORD
```

### Block USB Devices

```powershell
# Disable USB storage (not recommended if students need USB for login)
$RegPath = "HKLM:\SYSTEM\CurrentControlSet\Services\USBSTOR"
Set-ItemProperty -Path $RegPath -Name "Start" -Value 4 -Type DWORD
```

## Reverting Kiosk Mode

To revert to normal Windows:

1. Sign in as Administrator (Ctrl+Alt+Del, then Other User)
2. Open **Settings** > **Accounts** > **Other users**
3. Remove the kiosk configuration
4. Delete the `ExamStudent` account

Or via PowerShell:

```powershell
# Remove kiosk user
Remove-LocalUser -Name "ExamStudent"

# Re-enable Task Manager
Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Policies\System" -Name "DisableTaskMgr"
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| App doesn't launch | Verify path to exe is correct |
| Kiosk exits to desktop | Check app exit codes, ensure stable |
| Can't escape kiosk | Use Ctrl+Alt+Del > Switch User |
| Audio/Video not working | Check device permissions |

## Security Notes

1. Keep Windows and the exam app updated
2. Use a dedicated exam computer, not shared
3. Physically secure the exam room
4. Monitor network traffic if possible
5. Have a backup plan for technical failures
