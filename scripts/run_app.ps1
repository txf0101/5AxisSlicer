param(
    [string]$Python = "C:\Users\Tang Xufeng\.conda\envs\5AxisSlicer\python.exe",
    [string]$Model = "",
    [int]$Port = 8765
)

$repo = Split-Path -Parent $PSScriptRoot
$argsList = @("$repo\run_app.py", "--port", "$Port")
if ($Model -ne "") {
    $argsList += @("--model", $Model)
}

& $Python @argsList
