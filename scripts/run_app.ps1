param(
    [string]$Python = "python",
    [string]$Model = "",
    [string]$GCode = "",
    [string]$BindHost = "127.0.0.1",
    [switch]$Demo,
    [switch]$Results,
    [switch]$AllowRemoteAutomation,
    [int]$Port = 8765
)

$repo = Split-Path -Parent $PSScriptRoot
$arguments = @((Join-Path $repo "run_app.py"), "--host", $BindHost, "--port", $Port)
if ($Demo) { $arguments += "--demo" }
if ($Results) { $arguments += "--results" }
if ($AllowRemoteAutomation) { $arguments += "--allow-remote-automation" }
if ($Model) { $arguments += @("--model", $Model) }
if ($GCode) { $arguments += @("--gcode", $GCode) }

& $Python @arguments
exit $LASTEXITCODE
