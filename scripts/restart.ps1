# Dev helper: stop the bridge-enabled Orange started earlier, start a fresh one,
# wait until the bridge answers. Only touches the PID recorded by the bridge.
param([switch]$Debug)
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$disc = "$env:LOCALAPPDATA\mcp_orange\bridge.json"
if (Test-Path $disc) {
    $old = (Get-Content $disc | ConvertFrom-Json).pid
    Stop-Process -Id $old -Force -ErrorAction SilentlyContinue
    Start-Sleep 2
    Remove-Item $disc -ErrorAction SilentlyContinue
}
if ($Debug) { $env:ORANGE_MCP_DEBUG = "1" } else { Remove-Item Env:ORANGE_MCP_DEBUG -ErrorAction SilentlyContinue }
Start-Process -FilePath powershell -WindowStyle Hidden `
    -ArgumentList '-NoProfile', '-File', "$root\run_orange.ps1" `
    -RedirectStandardOutput "$root\orange.out.log" -RedirectStandardError "$root\orange.err.log"
for ($i = 0; $i -lt 90 -and -not (Test-Path $disc); $i++) { Start-Sleep 1 }
Start-Sleep 2
& python.exe -I "$root\relay\bridge_client.py" 2>$null
if (Test-Path $disc) { "bridge up: " + (Get-Content $disc) } else { "bridge NOT up"; exit 1 }
