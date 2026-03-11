param(
    [string]$PythonExe = "$env:USERPROFILE\.conda\envs\5AxisSlicer\python.exe",
    [switch]$SkipPyInstaller
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function New-PortableZip {
    param(
        [Parameter(Mandatory = $true)][string]$SourceDirectory,
        [Parameter(Mandatory = $true)][string]$DestinationZip
    )

    for ($attempt = 1; $attempt -le 4; $attempt++) {
        try {
            if (Test-Path $DestinationZip) {
                Remove-Item $DestinationZip -Force
            }
            Compress-Archive -Path (Join-Path $SourceDirectory '*') -DestinationPath $DestinationZip -Force
            return
        }
        catch {
            if ($attempt -eq 4) {
                throw
            }
            Start-Sleep -Seconds 3
        }
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir '..\..')).Path
$buildSupport = Join-Path $repoRoot 'packaging\build_support.py'
$specPath = Join-Path $repoRoot 'packaging\pyinstaller\5AxisSlicer.spec'
$distRoot = Join-Path $repoRoot 'dist'
$workRoot = Join-Path $repoRoot 'build\pyinstaller'
$windowsBuildRoot = Join-Path $repoRoot 'build\windows'
$installersDir = Join-Path $distRoot 'installers'
$appDist = Join-Path $distRoot '5AxisSlicer'
$installerScript = Join-Path $repoRoot 'packaging\windows\install.ps1'
$iexpressPath = Join-Path $env:WINDIR 'System32\iexpress.exe'
$iexpressTempRoot = Join-Path $env:TEMP '5AxisSlicer-IExpress'
$iexpressStage = Join-Path $iexpressTempRoot 'stage'
$tempExe = Join-Path $iexpressTempRoot '5AxisSlicer-setup.exe'
$sedPath = Join-Path $iexpressTempRoot '5AxisSlicer.sed'

if (-not (Test-Path $PythonExe)) {
    throw "Python executable not found: $PythonExe"
}
if (-not (Test-Path $iexpressPath)) {
    throw "IExpress not found: $iexpressPath"
}

$version = (& $PythonExe $buildSupport --version).Trim()
if (-not $version) {
    throw 'Could not determine application version.'
}

New-Item -ItemType Directory -Force -Path $windowsBuildRoot | Out-Null
New-Item -ItemType Directory -Force -Path $installersDir | Out-Null

if (-not $SkipPyInstaller) {
    & $PythonExe -m PyInstaller --version | Out-Null
    & $PythonExe -m PyInstaller --noconfirm --clean --distpath $distRoot --workpath $workRoot $specPath
}

if (-not (Test-Path $appDist)) {
    throw "PyInstaller output not found: $appDist"
}

$internalRoot = Join-Path $appDist '_internal'
$cairoSource = Join-Path $internalRoot 'cairo-2.dll'
$cairoAlias = Join-Path $internalRoot 'cairo.dll'
if ((Test-Path $cairoSource) -and -not (Test-Path $cairoAlias)) {
    Copy-Item $cairoSource $cairoAlias -Force
}
$gmshSource = Join-Path $internalRoot 'gmsh.dll'
$gmshAlias = Join-Path $internalRoot 'gmsh-4.11.dll'
if ((Test-Path $gmshSource) -and -not (Test-Path $gmshAlias)) {
    Copy-Item $gmshSource $gmshAlias -Force
}

$portableZip = Join-Path $windowsBuildRoot "5AxisSlicer-$version-win64-portable.zip"
New-PortableZip -SourceDirectory $appDist -DestinationZip $portableZip

if (Test-Path $iexpressTempRoot) {
    Remove-Item $iexpressTempRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $iexpressStage | Out-Null
Copy-Item $portableZip (Join-Path $iexpressStage '5AxisSlicer-win64-portable.zip') -Force
Copy-Item $installerScript (Join-Path $iexpressStage 'install.ps1') -Force

@"
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -PayloadZip "%~dp05AxisSlicer-win64-portable.zip" -Version "$version"
"@ | Set-Content -Encoding ASCII (Join-Path $iexpressStage 'install.cmd')

$outExe = Join-Path $installersDir "5AxisSlicer-$version-win64-setup.exe"
if (Test-Path $tempExe) {
    Remove-Item $tempExe -Force
}
if (Test-Path $outExe) {
    Remove-Item $outExe -Force
}

$targetName = $tempExe.Replace('/', '\\')
$sourceDir = $iexpressStage.Replace('/', '\\')
$sed = @"
[Version]
Class=IEXPRESS
SEDVersion=3
[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=1
HideExtractAnimation=1
UseLongFileName=1
InsideCompressed=1
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=
DisplayLicense=
FinishMessage=5AxisSlicer has been installed.
TargetName=$targetName
FriendlyName=5AxisSlicer Setup
AppLaunched=cmd.exe /c install.cmd
PostInstallCmd=<None>
AdminQuietInstCmd=
UserQuietInstCmd=
SourceFiles=SourceFiles
[SourceFiles]
SourceFiles0=$sourceDir
[SourceFiles0]
%FILE0%=
%FILE1%=
%FILE2%=
[Strings]
FILE0=5AxisSlicer-win64-portable.zip
FILE1=install.ps1
FILE2=install.cmd
"@
$sed | Set-Content -Encoding ASCII $sedPath

& $iexpressPath /N $sedPath | Out-Null

if (-not (Test-Path $tempExe)) {
    throw "IExpress did not generate the installer: $tempExe"
}

Move-Item $tempExe $outExe -Force
Write-Host "Windows installer created: $outExe"
