param(
    [string]$PayloadZip = (Join-Path $PSScriptRoot '5AxisSlicer-win64-portable.zip'),
    [string]$AppName = '5AxisSlicer',
    [string]$Version = '0.0.0',
    [string]$Publisher = 'Tang Xufeng'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$installRoot = Join-Path $env:LocalAppData "Programs\$AppName"
$startMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\$AppName"
$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) "$AppName-install"
$desktopShortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) "$AppName.lnk"
$uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppName"

if (-not (Test-Path $PayloadZip)) {
    throw "Installer payload not found: $PayloadZip"
}

if (Test-Path $tempRoot) {
    Remove-Item $tempRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
Expand-Archive -Path $PayloadZip -DestinationPath $tempRoot -Force

if (Test-Path $installRoot) {
    Remove-Item $installRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
Copy-Item -Path (Join-Path $tempRoot '*') -Destination $installRoot -Recurse -Force

$mainExe = Join-Path $installRoot "$AppName.exe"
$cliExe = Join-Path $installRoot "$AppName-cli.exe"
$uninstallScript = Join-Path $installRoot 'uninstall.ps1'
$uninstallCmd = Join-Path $installRoot 'uninstall.cmd'

if (-not (Test-Path $mainExe)) {
    throw "Installed executable not found: $mainExe"
}

$uninstallBody = @"
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
`$appName = '$AppName'
`$installRoot = Split-Path -Parent `$MyInvocation.MyCommand.Path
`$startMenuDir = Join-Path `$env:APPDATA "Microsoft\Windows\Start Menu\Programs\$AppName"
`$desktopShortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) "$AppName.lnk"
`$uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppName"
if (Test-Path `$startMenuDir) {
    Remove-Item `$startMenuDir -Recurse -Force
}
if (Test-Path `$desktopShortcut) {
    Remove-Item `$desktopShortcut -Force
}
if (Test-Path `$uninstallKey) {
    Remove-Item `$uninstallKey -Recurse -Force
}
if (Test-Path `$installRoot) {
    Remove-Item `$installRoot -Recurse -Force
}
"@
$uninstallBody | Set-Content -Encoding UTF8 $uninstallScript

@"
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1"
"@ | Set-Content -Encoding ASCII $uninstallCmd

New-Item -ItemType Directory -Force -Path $startMenuDir | Out-Null
$wsh = New-Object -ComObject WScript.Shell

$mainShortcut = $wsh.CreateShortcut((Join-Path $startMenuDir "$AppName.lnk"))
$mainShortcut.TargetPath = $mainExe
$mainShortcut.WorkingDirectory = $installRoot
$mainShortcut.Save()

$desktop = $wsh.CreateShortcut($desktopShortcut)
$desktop.TargetPath = $mainExe
$desktop.WorkingDirectory = $installRoot
$desktop.Save()

if (Test-Path $cliExe) {
    $cliShortcut = $wsh.CreateShortcut((Join-Path $startMenuDir "$AppName CLI.lnk"))
    $cliShortcut.TargetPath = $cliExe
    $cliShortcut.WorkingDirectory = $installRoot
    $cliShortcut.Save()
}

New-Item -Path $uninstallKey -Force | Out-Null
New-ItemProperty -Path $uninstallKey -Name DisplayName -Value $AppName -PropertyType String -Force | Out-Null
New-ItemProperty -Path $uninstallKey -Name DisplayVersion -Value $Version -PropertyType String -Force | Out-Null
New-ItemProperty -Path $uninstallKey -Name Publisher -Value $Publisher -PropertyType String -Force | Out-Null
New-ItemProperty -Path $uninstallKey -Name InstallLocation -Value $installRoot -PropertyType String -Force | Out-Null
New-ItemProperty -Path $uninstallKey -Name DisplayIcon -Value $mainExe -PropertyType String -Force | Out-Null
New-ItemProperty -Path $uninstallKey -Name NoModify -Value 1 -PropertyType DWord -Force | Out-Null
New-ItemProperty -Path $uninstallKey -Name NoRepair -Value 1 -PropertyType DWord -Force | Out-Null
New-ItemProperty -Path $uninstallKey -Name UninstallString -Value "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$uninstallScript`"" -PropertyType String -Force | Out-Null

if (Test-Path $tempRoot) {
    Remove-Item $tempRoot -Recurse -Force
}

Write-Host "Installed $AppName $Version to $installRoot"
