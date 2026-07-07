param(
    [string]$Python = "C:\Users\Tang Xufeng\.conda\envs\5AxisSlicer\python.exe",
    [string]$Model = "",
    [string]$GCode = "",
    [switch]$Demo,
    [int]$Port = 8765
)

$repo = Split-Path -Parent $PSScriptRoot
$argsList = @("$repo\run_app.py", "--port", "$Port")
if ($Demo) {
    $argsList += @("--demo")
}
if ($Model -ne "") {
    $argsList += @("--model", $Model)
}
if ($GCode -ne "") {
    $argsList += @("--gcode", $GCode)
}

& $Python @argsList
